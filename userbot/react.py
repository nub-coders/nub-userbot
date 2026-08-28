from pyrogram import Client, filters
from pyrogram.types import Message, MessageEntity
from pyrogram.enums import MessageEntityType
from pyrogram.parser.utils import add_surrogates, remove_surrogates
import asyncio
from config import *
from tools import *
from utils.message import Msg

async def _mentioned_me(_, client, message: Message):
    me = client.me
    if not me:
        return False

    # A caption's entities live in caption_entities, so a mention in a photo or
    # video caption was invisible to this filter.
    text = message.text or message.caption or ""
    entities = message.entities or message.caption_entities or []
    if not text or not entities:
        return False

    # Entity offsets count UTF-16 code units, which is what Telegram measures in,
    # while Python slices by code point. One emoji earlier in the message shifted
    # every following offset by one, so "👋 @me" sliced the wrong characters and the
    # mention was missed. add_surrogates puts the text into the same units as the
    # offsets -- the same thing kurigram's own unparser does before indexing.
    surrogated = add_surrogates(text)
    my_username = (me.username or "").lower()

    for entity in entities:
        if entity.type == MessageEntityType.MENTION:
            if not my_username:
                continue
            mentioned_user = remove_surrogates(
                surrogated[entity.offset:entity.offset + entity.length]
            )
            # Usernames are case-insensitive on Telegram: someone typing
            # "@NubBot" is mentioning "nubbot", and the exact comparison here
            # used to reject it.
            if mentioned_user.lower() == f"@{my_username}":
                return True
        elif entity.type == MessageEntityType.TEXT_MENTION:
            if entity.user and entity.user.id == me.id:
                return True
    return False

mentioned_me = filters.create(_mentioned_me)

react_emojis = ['👍', '♥️', '🔥', '🎉']

# Anyone who can post can mention the account, and each mention used to cost a
# get_me(), a session lookup, an uncached get_chat() and a send_reaction with
# nothing in between. Repeated mentions therefore turned into unthrottled API
# traffic, and the FloodWait that follows was swallowed by the bare `except`
# below, so the account carried on hammering instead of backing off. Reactions
# are decoration: one per chat per cooldown is plenty.
_REACT_COOLDOWN = 10
_last_react = {}


def _react_allowed(chat_id, now=None):
    """True when this chat is outside its cooldown; records the attempt."""
    now = now if now is not None else time.time()
    if now - _last_react.get(chat_id, 0) < _REACT_COOLDOWN:
        return False
    # Keyed by a value strangers choose, so drop stale entries rather than let the
    # map grow for every chat the account is ever mentioned in.
    if len(_last_react) > 512:
        for stale in [c for c, t in _last_react.items() if now - t > _REACT_COOLDOWN * 10]:
            _last_react.pop(stale, None)
    _last_react[chat_id] = now
    return True


@Client.on_message(mentioned_me & ~filters.bot & ~filters.me, group=1)
async def auto_react_handler(client: Client, message: Message):
    try:
        if not _react_allowed(message.chat.id):
            return

        # `client.me` is already cached on the client; get_me() was a round trip
        # per mention.
        user = client.me
        user_data = user_sessions.find_one({"user_id": user.id})
        if not user_data:
            return

        rc = user_data.get('react_control')
        if not isinstance(rc, int) or not (1 <= rc <= len(react_emojis)):
            return

        selected = react_emojis[rc - 1]

        chat = await client.get_chat(message.chat.id)
        cr = getattr(chat, "available_reactions", None)

        # Case 1: reactions disabled
        if cr is None:
            logger.debug(f"[REACTION] Disabled in chat {message.chat.id} for user {user.id}")
            return

        # Prepare usable emojis list
        if getattr(cr, "reactions", None):
            # Subset of allowed
            available = [r.emoji for r in cr.reactions if getattr(r, "emoji", None)]
        elif getattr(cr, "all_are_enabled", False):
            # All default emojis allowed, use your set
            available = react_emojis.copy()
        else:
            logger.debug(f"[REACTION] No usable reactions in chat {message.chat.id} for user {user.id}")
            return

        if not available:
            logger.debug(f"[REACTION] Empty available list in chat {message.chat.id} for user {user.id}")
            return

        # Determine which emoji to send
        emoji_to_send = selected if selected in available else available[0]

        await client.send_reaction(chat_id=message.chat.id,
                                   message_id=message.id,
                                   emoji=emoji_to_send)

    except FloodWait as e:
        # Hold this chat off for as long as Telegram asked, instead of retrying on
        # the next mention and deepening the limit.
        _last_react[message.chat.id] = time.time() + getattr(e, "value", 0)
        logger.warning(
            "[REACTION] FloodWait %ss in chat %s; pausing reactions there",
            getattr(e, "value", "?"), message.chat.id,
        )
    except Exception as e:
        logger.error(f"[REACTION] Auto-react error for user {client.me.id}: {e}")

# Reaction control commands with dynamic prefix
@Client.on_message(filters.command("react", prefixes=HARDCODED_PREFIXES) & filters.me)
async def react_control_command(client, message):
    """Control auto-reaction settings"""
    # Extract arguments using command args (filters.command automatically handles this)
    args = message.command[1:] if len(message.command) > 1 else []
    
    if not args:
        help_text = Msg.card(
            "Reaction Controls",
            [
                "[prefix]react on - enable reactions",
                "[prefix]react off - disable reactions",
                "[prefix]react 1-4 - choose a reaction",
                "[prefix]react status - show current state",
            ],
            emoji=Msg.EMOJI_INFO,
            footer=f"1={Msg.EMOJI_THUMBS_UP}  2={Msg.EMOJI_HEART}  3={Msg.EMOJI_FIRE}  4={Msg.EMOJI_PARTY}",
        )
        await message.edit(help_text)
        return
    
    command = args[0].lower()
    user_id = client.me.id
    
    if command == "on":
        user_sessions.update_one(
            {"user_id": user_id},
            {"$set": {"react_control": 1}},
            upsert=True
        )
        await message.edit(Msg.card("Reactions Enabled", [f"Default reaction: {Msg.EMOJI_THUMBS_UP}"], emoji=Msg.EMOJI_SUCCESS, footer="[prefix]react <1-4> to change"))
        
    elif command == "off":
        user_sessions.update_one(
            {"user_id": user_id},
            {"$unset": {"react_control": ""}},
            upsert=True
        )
        await message.edit(Msg.card("Reactions Disabled", ["Auto-reactions turned off"], emoji=Msg.EMOJI_WARNING, footer="[prefix]react on to re-enable"))
        
    elif command == "status":
        user_data = user_sessions.find_one({"user_id": user_id})
        if user_data and "react_control" in user_data:
            rc = user_data["react_control"]
            if isinstance(rc, int) and 1 <= rc <= len(react_emojis):
                selected = react_emojis[rc - 1]
                await message.edit(Msg.card("Reaction Status", ["Status: Enabled", f"Emoji: {selected}"], emoji=Msg.EMOJI_INFO))
            else:
                await message.edit(Msg.card("Reaction Status", ["Status: Disabled"], emoji=Msg.EMOJI_INFO))
        else:
            await message.edit(Msg.card("Reaction Status", ["Status: Disabled"], emoji=Msg.EMOJI_INFO))
            
    elif command.isdigit():
        try:
            reaction_num = int(command)
            if 1 <= reaction_num <= len(react_emojis):
                user_sessions.update_one(
                    {"user_id": user_id},
                    {"$set": {"react_control": reaction_num}},
                    upsert=True
                )
                selected = react_emojis[reaction_num - 1]
                await message.edit(Msg.card("Reaction Updated", [f"New reaction: {selected}"], emoji=Msg.EMOJI_SUCCESS))
            else:
                await message.edit(Msg.card("Invalid Number", [f"Use 1 to {len(react_emojis)}"], emoji=Msg.EMOJI_ERROR))
        except ValueError:
            await message.edit(Msg.card("Invalid Command", ["Use [prefix]react help for usage"], emoji=Msg.EMOJI_ERROR))
    else:
        await message.edit(Msg.card("Invalid Command", ["Use [prefix]react help for usage"], emoji=Msg.EMOJI_ERROR))

@Client.on_message(filters.command("reactlist", prefixes=HARDCODED_PREFIXES) & filters.me)
async def react_list_command(client, message):
    """List available reactions"""
    lines = []
    for i, emo in enumerate(react_emojis, 1):
        lines.append(f"<b>{i}.</b> {emo} — <code>.react {i}</code>")
    text = (
        f"<b>✨ Available Auto-Reactions</b>\n\n"
        f"<blockquote>\n" + "\n".join(lines) + f"\n</blockquote>\n\n"
        f"💡 <i>Use <code>.react &lt;number&gt;</code> to activate your chosen emoji.</i>"
    )
    await message.edit(text, parse_mode=enums.ParseMode.HTML)


