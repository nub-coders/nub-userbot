import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

# Make the repo root importable (config.py, tools.py live there).
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


@pytest.fixture
def mock_client():
    client = MagicMock()
    client.me = MagicMock(id=12345)
    client.send_message = AsyncMock()
    return client


@pytest.fixture
def mock_message():
    """A message with async reply/edit and no reply target by default."""
    msg = MagicMock()
    msg.reply = AsyncMock()
    msg.edit = AsyncMock()
    msg.edit_text = AsyncMock()
    msg.delete = AsyncMock()
    msg.reply_to_message = None
    msg.text = ""
    return msg
