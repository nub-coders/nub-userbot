"""Tests for the external plugin loader: it must register decorated handlers
from a dropped-in file and skip broken files without aborting."""
from plugin_loader import load_extra_plugins


class _FakeClient:
    def __init__(self):
        self.added = []

    def add_handler(self, handler, group):
        self.added.append((handler, group))


_GOOD = """
from pyrogram.handlers import MessageHandler

async def _cb(client, message):
    pass

def my_command():
    pass

# Mirror what @Client.on_message stashes on the function.
my_command.handlers = [(MessageHandler(_cb), 0)]
"""

_BROKEN = "raise RuntimeError('boom at import')\n"


def test_loads_good_skips_broken(tmp_path):
    (tmp_path / "goodplugin.py").write_text(_GOOD)
    (tmp_path / "broken.py").write_text(_BROKEN)
    (tmp_path / "_private.py").write_text(_GOOD)  # underscore-prefixed: ignored

    client = _FakeClient()
    loaded = load_extra_plugins(client, str(tmp_path))

    assert loaded == ["goodplugin"]          # broken skipped, _private ignored
    assert len(client.added) == 1            # one handler registered
    assert client.added[0][1] == 0           # correct group


def test_missing_dir_is_noop(tmp_path):
    assert load_extra_plugins(_FakeClient(), str(tmp_path / "does-not-exist")) == []
