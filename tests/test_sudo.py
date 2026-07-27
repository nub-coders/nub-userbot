"""Tests for userbot.sudo resolvers — the permission-model logic that decides
who a command targets. Pure once the Pyrogram message is mocked."""
from unittest.mock import MagicMock

import pytest

from userbot.sudo import resolve_target_id, _target_detail


def test_target_detail_with_full_name():
    user = MagicMock(first_name="Ada", last_name="Lovelace")
    assert _target_detail(42, user) == ["User: Ada Lovelace", "ID: `42`"]


def test_target_detail_first_name_only():
    user = MagicMock(first_name="Ada", last_name=None)
    assert _target_detail(42, user) == ["User: Ada", "ID: `42`"]


def test_target_detail_no_user_object():
    assert _target_detail(42, None) == ["User ID: `42`"]


@pytest.mark.asyncio
async def test_resolve_from_reply(mock_message):
    replied = MagicMock()
    replied.from_user = MagicMock(id=999)
    mock_message.reply_to_message = replied

    uid, user = await resolve_target_id(mock_message)
    assert uid == 999
    assert user is replied.from_user
    mock_message.reply.assert_not_called()


@pytest.mark.asyncio
async def test_resolve_reply_not_from_user(mock_message):
    replied = MagicMock()
    replied.from_user = None
    mock_message.reply_to_message = replied

    assert await resolve_target_id(mock_message) is None
    mock_message.reply.assert_awaited_once()


@pytest.mark.asyncio
async def test_resolve_from_valid_id_arg(mock_message):
    mock_message.text = ".addsudo 555"
    uid, user = await resolve_target_id(mock_message)
    assert uid == 555
    assert user is None


@pytest.mark.asyncio
async def test_resolve_from_invalid_id_arg(mock_message):
    mock_message.text = ".addsudo notanumber"
    assert await resolve_target_id(mock_message) is None
    mock_message.reply.assert_awaited_once()


@pytest.mark.asyncio
async def test_resolve_no_reply_no_arg(mock_message):
    mock_message.text = ".addsudo"
    assert await resolve_target_id(mock_message) is None
    mock_message.reply.assert_awaited_once()
