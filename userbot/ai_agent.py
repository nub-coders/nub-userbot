"""Agentic AI assistant backed by an Anthropic-compatible AI gateway.

``.ask`` runs a tool-use loop: the model can search the web, read files, and
search the codebase before answering, and it remembers the conversation per
chat.
"""
import asyncio
import logging

from pyrogram import Client, filters
from pyrogram.types import Message

import ai_backend
from ai_backend import split_message
from config import (
    HARDCODED_PREFIXES,
    AGENT_ALLOW_MODERATION,
    AGENT_ALLOW_SHELL,
    AGENT_ALLOW_TELEGRAM_API,
    AGENT_MODEL,
    AGENT_VISION_MODEL,
)
from tools import retry, edit_or_reply, styled_error
from userbot.ai_telegram_tools import build_tool_schemas, build_telegram_tools

logger = logging.getLogger("userbot.ai_agent")

# Seconds a single .ask run may take before we give up on it. `agent_answer` runs
# on a worker thread, which nothing can interrupt from outside, so the timeout is
# enforced by a CancelToken the loop checks rather than by abandoning the thread.
ASK_TIMEOUT = 300


@retry()
async def _edit_or_reply_retrying(message: Message, text: str):
    """`edit_or_reply` with FloodWait retries.

    Safe to replay because it is one edit with no other side effects. `ask_handler`
    itself must never be wrapped in `@retry()` -- see the note there.
    """
    return await edit_or_reply(message, text)


@retry()
async def _reply_retrying(message: Message, text: str):
    """`message.reply` with FloodWait retries, for answer chunks after the first."""
    return await message.reply(text, quote=True)


def _abandon(task: asyncio.Task):
    """Stop asyncio complaining about the exception of a run we gave up on."""
    def _drain(finished: asyncio.Task):
        if not finished.cancelled():
            finished.exception()

    task.add_done_callback(_drain)


def _resolve_query(message: Message) -> str:
    """Build the prompt from the command args and any replied-to message.

    Replied text goes through `ai_backend.fence_untrusted`, whose nonce-tagged
    fence the quoted text cannot close -- so it stays data rather than becoming
    instructions addressed to the model.
    """
    args = _command_args(message)

    replied = message.reply_to_message
    if replied:
        quoted = replied.text or replied.caption or ""
        if quoted:
            question = args or "Respond to the quoted message."
            return (
                f"{ai_backend.fence_untrusted(quoted)}\n\n"
                f"Operator's request: {question}"
            )

    return args


def _command_args(message: Message) -> str:
    """The text the user typed after the command, empty if they typed none.

    Falls back to the caption: `filters.command` matches captions too, so
    `.ask what is this` sent as a photo caption reaches this handler.
    """
    text = message.text or message.caption or ""
    if len(text.split(maxsplit=1)) > 1:
        return text.split(maxsplit=1)[1].strip()
    return ""


# Longest echoed question. `.ask` overwrites the user's own message, so the
# question is repeated above the answer -- but a wall of quoted text would
# crowd out the answer itself.
_MAX_ECHO = 300

# Pyrogram's markdown has no backslash escape, so an unbalanced delimiter in
# the question (`.ask what does ** mean`) swallows text and leaks formatting
# into the answer below it. A zero-width space between the characters breaks
# every multi-char delimiter (`**`, `__`, `--`, `~~`, `||`) while staying
# invisible; `](` is broken the same way so a question can't become a link.
_ZWSP = "​"
_MD_CHARS = "*_-~|"


def _defuse_md(text: str) -> str:
    """Break markdown delimiters so a question renders as the user typed it."""
    # Backticks are dropped rather than defused: markdown mode has no way to
    # display a literal one, so leaving it in would only open a stray code span.
    text = text.replace("`", "")
    for ch in _MD_CHARS:
        text = text.replace(ch, ch + _ZWSP)
    return text.replace("](", "]" + _ZWSP + "(")


def _format_answer(message: Message, answer: str, model: str = "") -> str:
    """Put the question back above the answer, quoted, and name the model.

    `.ask` edits the user's own message in place, so without this the question
    disappears and the reply reads as an answer to nothing.
    """
    asked = _command_args(message)
    if not asked and message.reply_to_message:
        asked = "(about the replied-to message)"

    parts = []
    if asked:
        if len(asked) > _MAX_ECHO:
            asked = asked[:_MAX_ECHO].rstrip() + "…"
        # Collapse newlines: a blockquote line break would split the quote, and
        # the header reads better as one line anyway.
        asked = " ".join(asked.split())
        parts.append(f"> ❓ {_defuse_md(asked)}")
    parts.append(answer)
    if model:
        parts.append(f"🤖 `{model}`")
    return "\n\n".join(parts)


@Client.on_message(filters.me & filters.command(["ask", "ai"], prefixes=HARDCODED_PREFIXES))
async def ask_handler(client: Client, message: Message):
    """Answer a question with the agentic tool-use loop.

    Deliberately **not** wrapped in `@retry()`. A retry here replays the whole
    agentic run, and `build_telegram_tools` hands each replay a fresh action
    budget -- so one FloodWait on a status edit could turn the 10-action cap into
    40 real moderation actions. Retries belong on the individual message edits
    (`_edit_or_reply_retrying`, `_reply_retrying`), which are idempotent.
    """
    if not ai_backend.is_configured():
        await _edit_or_reply_retrying(
            message,
            styled_error("`AI_API_KEY` and `AI_BASE_URL` must both be set in your `.env` to use `.ai` / `.ask`."),
        )
        return

    query = _resolve_query(message)
    if not query:
        await _edit_or_reply_retrying(
            message,
            styled_error("Provide a question or reply to a message.\n\n**Usage:** `.ai <question>` or `.ask <question>`"),
        )
        return

    status_msg = await _edit_or_reply_retrying(
        message, _format_answer(message, "🧠 **AI is thinking...**")
    )

    # agent_answer runs in a worker thread, so status updates have to be
    # bounced back onto the event loop rather than awaited directly.
    loop = asyncio.get_running_loop()
    last_status = {"text": "", "pending": None}
    # Filled in by agent_answer with the model that actually served the run --
    # fallback rotation means it isn't always the configured one.
    meta = {}
    # How the worker thread finds out we stopped waiting for it.
    cancel = ai_backend.CancelToken()

    def status_callback(text: str):
        if text == last_status["text"]:
            return
        last_status["text"] = text
        pending = last_status["pending"]
        if pending and not pending.done():
            return  # an edit is still in flight; skip this one rather than queue
        last_status["pending"] = asyncio.run_coroutine_threadsafe(
            _safe_edit(status_msg, _format_answer(message, text)), loop
        )

    task = asyncio.create_task(
        asyncio.to_thread(
            ai_backend.agent_answer,
            query,
            ai_backend.build_tools()
            + build_tool_schemas(
                allow_moderation=AGENT_ALLOW_MODERATION,
                allow_api=AGENT_ALLOW_TELEGRAM_API,
            ),
            ai_backend.build_tool_impls(
                extra_tools=build_telegram_tools(
                    client, message, loop,
                    allow_moderation=AGENT_ALLOW_MODERATION,
                    allow_api=AGENT_ALLOW_TELEGRAM_API,
                )
            ),
            status_callback,
            message.chat.id,
            meta=meta,
            cancel=cancel,
        )
    )
    try:
        # Shielded because cancelling a task that wraps a thread does not stop the
        # thread, it only stops anyone watching it. The token is what actually
        # ends the work; the shield keeps the task observable so `_abandon` can
        # collect its outcome instead of asyncio warning about it.
        answer = await asyncio.wait_for(asyncio.shield(task), timeout=ASK_TIMEOUT)
    except asyncio.TimeoutError:
        # Cancelled before the edit rather than in the `finally`: the edit is a
        # network round trip, and every second of it is another second the
        # abandoned run could spend calling tools.
        cancel.cancel()
        await _safe_edit(
            status_msg,
            _format_answer(message, styled_error(f"Request timed out after {ASK_TIMEOUT}s.")),
        )
        return
    except ai_backend.AgentError as e:
        await _safe_edit(
            status_msg,
            _format_answer(message, styled_error(f"AI service error: {ai_backend.scrub(str(e))}")),
        )
        return
    except Exception as e:
        # Arbitrary exceptions can quote the upstream URL, so scrub here too.
        logger.exception("Agent run failed")
        await _safe_edit(status_msg, _format_answer(message, styled_error(ai_backend.scrub(str(e)))))
        return
    finally:
        # Unconditional: on the success path both calls are no-ops, and on every
        # failure path a thread that is somehow still running would otherwise keep
        # invoking tools after the user was already shown an error.
        cancel.cancel()
        _abandon(task)

    chunks = split_message(
        _format_answer(message, answer or "[no response]", meta.get("model", ""))
    )
    await _safe_edit(status_msg, chunks[0])
    for chunk in chunks[1:]:
        await _reply_retrying(status_msg, chunk)


async def _safe_edit(message: Message, text: str):
    """Edit a message, tolerating MessageNotModified and similar edit errors."""
    try:
        await message.edit_text(text)
    except Exception as e:
        logger.debug("Status edit failed: %s", e)


@Client.on_message(filters.me & filters.command(["askclear", "askreset", "aiclear", "aireset"], prefixes=HARDCODED_PREFIXES))
@retry()
async def ask_clear_handler(client: Client, message: Message):
    """Forget the agent's conversation memory for this chat."""
    if ai_backend.clear_chat_history(message.chat.id):
        await edit_or_reply(message, "🧹 **Chat memory cleared.** Starting fresh.")
    else:
        await edit_or_reply(message, "🧹 **Chat memory is already empty.**")


@Client.on_message(filters.me & filters.command(["askmodel", "aimodel"], prefixes=HARDCODED_PREFIXES))
@retry()
async def ask_model_handler(client: Client, message: Message):
    """Show the active model and which tools are armed."""
    if not ai_backend.is_configured():
        await edit_or_reply(
            message,
            styled_error("`AI_API_KEY` and `AI_BASE_URL` must both be set in your `.env` to use `.ai` / `.ask`."),
        )
        return

    shell_state = "Enabled ⚠️" if AGENT_ALLOW_SHELL else "Disabled 🔒"
    moderation_state = "Enabled ⚠️" if AGENT_ALLOW_MODERATION else "Disabled 🔒"
    api_state = "Enabled ⚠️" if AGENT_ALLOW_TELEGRAM_API else "Disabled 🔒"

    config_block = (
        f"<b>🤖 Active AI Configuration</b>\n\n"
        f"<blockquote>\n"
        f"<b>• Model:</b> <code>{AGENT_MODEL}</code>\n"
        f"<b>• Vision Model:</b> <code>{AGENT_VISION_MODEL}</code>\n"
        f"<b>• Shell Tool:</b> {shell_state}\n"
        f"<b>• Moderation:</b> {moderation_state}\n"
        f"<b>• Telegram API:</b> {api_state}\n"
        f"</blockquote>"
    )

    await edit_or_reply(message, config_block)


