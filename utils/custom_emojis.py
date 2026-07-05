"""Custom emoji registry backed by data/custom_emoji_ids.json.

The dump file contains document ids for custom emoji sticker packs.
This module lets the bot render Telegram custom emoji tags from those ids
while preserving a plain Unicode fallback when a match is unavailable.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Dict, List, Optional

_DATA_PATH = Path(__file__).resolve().parent.parent / 'data' / 'custom_emoji_ids.json'


@lru_cache(maxsize=1)
def _load_registry() -> Dict[str, List[int]]:
    registry: Dict[str, List[int]] = {}
    if not _DATA_PATH.exists():
        return registry

    try:
        payload = json.loads(_DATA_PATH.read_text(encoding='utf-8'))
    except Exception:
        return registry

    for pack in payload:
        for item in pack.get('items', []):
            emoji = item.get('emoji')
            document_id = item.get('document_id')
            if not emoji or document_id is None:
                continue
            registry.setdefault(emoji, []).append(int(document_id))

    return registry


def available_emojis() -> List[str]:
    return sorted(_load_registry().keys())


def document_ids_for(emoji: str) -> List[int]:
    return list(_load_registry().get(emoji, []))


def pick_document_id(emoji: str, index: int = 0) -> Optional[int]:
    ids = document_ids_for(emoji)
    if not ids:
        return None
    return ids[index % len(ids)]


def render(emoji: str, fallback: Optional[str] = None, index: int = 0) -> str:
    """Render a Telegram custom emoji tag.

    Args:
        emoji: The visible emoji to show inside the tag and to use for lookup.
        fallback: Plain-text fallback if the emoji is unavailable.
        index: Which matching document id to use when multiple IDs exist.
    """
    document_id = pick_document_id(emoji, index=index)
    visible = fallback if fallback is not None else emoji
    if document_id is None:
        return visible
    return f'<emoji id="{document_id}">{visible}</emoji>'


# Common semantic picks used by the message helper.
ERROR = render('❌')
WARNING = render('⚠️')
SUCCESS = render('✅')
INFO = render('ℹ️')
LOADING = render('⏳')
PIN = render('📌')
ROCKET = render('🚀')
GEAR = render('⚙️')
FIRE = render('🔥')
SPARK = render('✨')
MUSIC = render('🎵')
MIC = render('🎤')
SHIELD = render('🛡️')
LOCK = render('🔒')
CROWN = render('👑')
DRAGON = render('🐉')
MOON = render('🌙')
CAT = render('🐱')
THUMBS_UP = render('👍')
HEART = render('❤️')
PARTY = render('🎉')
WARNING_BOLT = render('⚠️')
FOLDER = render('📂')
DOWNLOAD = render('📥')
NOTE = render('📝')
WAVE = render('👋')
CALENDAR = render('📅')
QUESTION = render('❓')
USER = render('👤')
CHAT = render('💬')
LINK = render('🔗')
ID = render('🆔')
STAR = render('⭐️')
SEARCH = render('🔍')
GRID = render('📐')
PUZZLE = render('🧩')
SOLVE = render('🎯')
PONG = render('🏓')

# ─────────────────────────────────────────────────────────────────────────────
# STATUS & ALERTS
# ─────────────────────────────────────────────────────────────────────────────
BANNED      = render('🚫')
MUTED       = render('🔇')
UNMUTED     = render('🔊')
ONLINE      = render('🟢')
OFFLINE     = render('🔴')
IDLE        = render('🟡')
BUSY        = render('⛔')
VERIFIED    = render('✔️')
UNVERIFIED  = render('✖️')
PREMIUM     = render('💎')
BADGE       = render('🏅')
MEDAL       = render('🥇')
TROPHY      = render('🏆')
NEW_TAG     = render('🆕')
HOT         = render('♨️')
TRENDING    = render('📈')
DROPPED     = render('📉')

# ─────────────────────────────────────────────────────────────────────────────
# ACTIONS & CONTROLS
# ─────────────────────────────────────────────────────────────────────────────
PLAY        = render('▶️')
PAUSE       = render('⏸️')
STOP        = render('⏹️')
SKIP        = render('⏭️')
REWIND      = render('⏮️')
FAST_FWD    = render('⏩')
FAST_REV    = render('⏪')
REFRESH     = render('🔄')
REPEAT      = render('🔁')
SHUFFLE     = render('🔀')
ADD         = render('➕')
REMOVE      = render('➖')
EDIT        = render('✏️')
DELETE      = render('🗑️')
SAVE        = render('💾')
COPY        = render('📋')
PASTE       = render('📌')
SEND        = render('📤')
RECEIVE     = render('📥')
UPLOAD      = render('⬆️')
UNARCHIVE   = render('📦')
ARCHIVE     = render('🗃️')
EXPAND      = render('🔓')
COLLAPSE    = render('🔐')
SETTINGS    = render('🛠️')
FILTER      = render('🔽')
SORT        = render('🔼')
CLOSE       = render('✖️')
CONFIRM     = render('☑️')

# ─────────────────────────────────────────────────────────────────────────────
# MEDIA & CONTENT
# ─────────────────────────────────────────────────────────────────────────────
PHOTO       = render('🖼️')
VIDEO       = render('🎬')
AUDIO       = render('🔉')
VOICE       = render('🎙️')
STICKER     = render('🎭')
GIF         = render('🎞️')
DOCUMENT    = render('📄')
FILE        = render('🗂️')
BOOK        = render('📖')
NEWSPAPER   = render('📰')
CLIP        = render('📎')
PENCIL      = render('🖊️')
PAINT       = render('🎨')
CAMERA      = render('📷')
FILM        = render('🎥')
HEADPHONES  = render('🎧')
RADIO       = render('📻')
TV          = render('📺')

# ─────────────────────────────────────────────────────────────────────────────
# SOCIAL & IDENTITY
# ─────────────────────────────────────────────────────────────────────────────
ADMIN       = render('👮')
BOT         = render('🤖')
OWNER       = render('🦁')
MEMBER      = render('👥')
GUEST       = render('🧑')
ANONYMOUS   = render('👻')
VIP         = render('🌟')
SPY         = render('🕵️')
CLAP        = render('👏')
HANDSHAKE   = render('🤝')
PRAY        = render('🙏')
LOVE        = render('💕')
BROKEN_HEART= render('💔')
ANGER       = render('💢')
SLEEP       = render('💤')
IDEA        = render('💡')
MONEY       = render('💰')
GIFT        = render('🎁')
BALLOON     = render('🎈')
CONFETTI    = render('🎊')

# ─────────────────────────────────────────────────────────────────────────────
# SYMBOLS & OBJECTS
# ─────────────────────────────────────────────────────────────────────────────
BELL        = render('🔔')
NO_BELL     = render('🔕')
KEY         = render('🗝️')
UNLOCK      = render('🔓')
MAGNET      = render('🧲')
SWORD       = render('⚔️')
BOMB        = render('💣')
ZAP         = render('⚡')
DIAMOND     = render('💠')
CRYSTAL     = render('🔮')
MAP         = render('🗺️')
FLAG        = render('🏳️')
CHECKERED   = render('🏁')
RECYCLE     = render('♻️')
INFINITY    = render('♾️')
ATOM        = render('⚛️')
DNA         = render('🧬')
PILL        = render('💊')
SYRINGE     = render('💉')
MICROSCOPE  = render('🔬')
TELESCOPE   = render('🔭')

# ─────────────────────────────────────────────────────────────────────────────
# NATURE & ANIMALS
# ─────────────────────────────────────────────────────────────────────────────
LION        = render('🦁')
WOLF        = render('🐺')
FOX         = render('🦊')
OWL         = render('🦉')
EAGLE       = render('🦅')
SNAKE       = render('🐍')
BUTTERFLY   = render('🦋')
ROSE        = render('🌹')
CHERRY      = render('🍒')
LEAF        = render('🍃')
TREE        = render('🌲')
MOUNTAIN    = render('⛰️')
OCEAN       = render('🌊')
SUN         = render('☀️')
STORM       = render('⛈️')
SNOWFLAKE   = render('❄️')
COMET       = render('☄️')
GALAXY      = render('🌌')
PLANET      = render('🪐')
ALIEN       = render('👽')

# ─────────────────────────────────────────────────────────────────────────────
# GAMING & FUN
# ─────────────────────────────────────────────────────────────────────────────
GAME        = render('🎮')
DICE        = render('🎲')
CHESS       = render('♟️')
JOYSTICK    = render('🕹️')
SOCCER      = render('⚽')
BASKETBALL  = render('🏀')
TENNIS      = render('🎾')
BOWLING     = render('🎳')
DART        = render('🎯')
SLOT        = render('🎰')
CLOWN       = render('🤡')
SKULL       = render('💀')
GHOST       = render('👻')
ZOMBIE      = render('🧟')
NINJA       = render('🥷')
WIZARD      = render('🧙')

# ─────────────────────────────────────────────────────────────────────────────
# TECH & SYSTEM
# ─────────────────────────────────────────────────────────────────────────────
COMPUTER    = render('💻')
PHONE       = render('📱')
SERVER      = render('🖥️')
DATABASE    = render('🗄️')
WIFI        = render('📶')
BLUETOOTH   = render('🔵')
CPU         = render('🧠')
MEMORY      = render('💾')
CODE        = render('👨‍💻')
BUG         = render('🐛')
TERMINAL    = render('⌨️')
CLIPBOARD   = render('📋')
SPREADSHEET = render('📊')
CHART       = render('📈')
API         = render('🔌')
CLOUD       = render('☁️')
SATELLITE   = render('🛰️')

# ─────────────────────────────────────────────────────────────────────────────
# TIME & PROGRESS
# ─────────────────────────────────────────────────────────────────────────────
CLOCK       = render('🕐')
ALARM       = render('⏰')
TIMER       = render('⏱️')
HOURGLASS   = render('⌛')
HOURGLASS2  = render('⏳')
SUNRISE     = render('🌅')
SUNSET      = render('🌆')
NIGHT       = render('🌃')
MORNING     = render('🌄')
TODAY       = render('📆')
DEADLINE    = render('⏰')
FAST        = render('💨')
SLOW        = render('🐢')
INFINITE    = render('♾️')

