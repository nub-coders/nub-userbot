"""Pyrogram runs only the first matching handler per group, so wordseek's
catch-all listeners must not share group 0 with the command handlers — that is
what made `.wordseek` / `.gameinfo` silently do nothing in group chats."""
from userbot import wordseek_auto as ws


def _group(fn):
    return fn.handlers[0][1]


def test_listeners_are_not_in_the_command_group():
    command_group = _group(ws.wordseek_info)
    assert command_group == _group(ws.show_game_info)
    assert _group(ws.auto_play_handler) != command_group
    assert _group(ws.manual_guess) != command_group


def test_listeners_do_not_shadow_each_other():
    assert _group(ws.auto_play_handler) != _group(ws.manual_guess)
