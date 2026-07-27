"""Tests for tools.py pure-logic helpers: _SessionCache TTL and the retry()
decorator's FloodWait recovery."""
from unittest.mock import AsyncMock, patch

import pytest
from pyrogram.errors import FloodWait

from tools import _SessionCache, retry


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
