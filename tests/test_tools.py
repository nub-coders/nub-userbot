"""Tests for tools.py pure-logic helpers: _SessionCache TTL and the retry()
decorator's FloodWait recovery."""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pyrogram.errors import FloodWait

from tools import _SessionCache, retry, delete_if_self, parse_help_entry


class _FakeMsg:
    def __init__(self, is_self):
        self.from_user = type("U", (), {"is_self": is_self})()
        self.deleted = False

    async def delete(self):
        self.deleted = True


@pytest.mark.asyncio
async def test_delete_if_self_only_deletes_own_message():
    own = _FakeMsg(is_self=True)
    other = _FakeMsg(is_self=False)
    await delete_if_self(own)
    await delete_if_self(other)
    assert own.deleted is True
    assert other.deleted is False


def test_session_cache_hit_and_miss():
    cache = _SessionCache(ttl=30)
    assert cache.get(1) is None
    cache.set(1, {"a": 1})
    assert cache.get(1) == {"a": 1}


def test_session_cache_ttl_expiry():
    cache = _SessionCache(ttl=30)
    now = [1000.0]
    with patch("tools.time.time", side_effect=lambda: now[0]):
        cache.set(1, {"a": 1})            # stored at t=1000
        assert cache.get(1) == {"a": 1}   # within TTL
        now[0] = 1031.0
        assert cache.get(1) is None       # 31s > 30s TTL


def test_session_cache_invalidate_one_and_all():
    cache = _SessionCache(ttl=30)
    cache.set(1, "x")
    cache.set(2, "y")
    cache.invalidate(1)
    assert cache.get(1) is None
    assert cache.get(2) == "y"
    cache.invalidate()
    assert cache.get(2) is None


@pytest.mark.asyncio
async def test_retry_recovers_from_floodwait():
    calls = {"n": 0}

    @retry(max_retries=3, initial_delay=0)
    async def flaky():
        calls["n"] += 1
        if calls["n"] < 3:
            raise FloodWait(value=1)
        return "ok"

    with patch("asyncio.sleep", new=AsyncMock()):
        result = await flaky()

    assert result == "ok"
    assert calls["n"] == 3


@pytest.mark.asyncio
async def test_retry_reraises_unexpected_exception_immediately():
    calls = {"n": 0}

    @retry(max_retries=3, initial_delay=0)
    async def boom():
        calls["n"] += 1
        raise ValueError("nope")

    with patch("asyncio.sleep", new=AsyncMock()):
        with pytest.raises(ValueError):
            await boom()

    # ValueError isn't in the retry set, so it should fire exactly once.
    assert calls["n"] == 1


def test_parse_help_entry():
    raw = "**Play Audio** - Play audio in voice chat.\n\n**Usage:** `[prefix]play <query>`\n**Example:** `[prefix]play music`"
    desc, usage, example, note, warning, flags = parse_help_entry(raw)
    assert desc == "Play audio in voice chat."
    assert usage == "`[prefix]play <query>`"
    assert example == "`[prefix]play music`"


def test_commands_and_categories_registries():
    from tools import commands, categories
    assert len(commands) > 0
    assert len(categories) > 0
    assert "ℹ️ INFO" in categories
    assert "play" in commands


def test_commands_keyboard():
    from bot.botcmds import _commands_keyboard
    from tools import categories

    keyboard = _commands_keyboard()
    assert keyboard is not None
    assert len(keyboard.inline_keyboard) > 0

    # Test empty categories fallback
    old_cats = dict(categories)
    categories.clear()
    try:
        assert _commands_keyboard() is None
    finally:
        categories.update(old_cats)


def test_bot_proxy_falls_back_to_userbot_when_no_bot_registered():
    """apps["app"] absent -> _BotProxy uses the userbot client, so every
    `bot.send_message(...)` site keeps working without a BOT_TOKEN."""
    from config import apps, clients
    from tools import bot

    userbot = MagicMock(me=MagicMock(id=999, username="owner"))
    apps.pop("app", None)
    clients[999] = userbot
    try:
        assert bot.me.username == "owner"
        assert bot.send_message is userbot.send_message
    finally:
        clients.pop(999, None)


def test_bot_proxy_raises_when_no_client_at_all():
    from config import apps, clients
    from tools import bot

    apps.pop("app", None)
    saved = dict(clients)
    clients.clear()
    try:
        with pytest.raises(RuntimeError):
            bot.send_message
    finally:
        clients.update(saved)


def test_main_registers_bot_in_apps_only_after_successful_start():
    """Regression: a client parked in apps["app"] before start() defeats the
    _BotProxy userbot fallback and raises ConnectionError instead."""
    import inspect
    import main

    src = inspect.getsource(main.main)
    assert src.count('apps["app"] = app') == 1
    assert src.index("await app.start()") < src.index('apps["app"] = app')
