import os
import time
import logging
import pymongo
import certifi
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

# Telegram API credentials
# Required: Get these from https://my.telegram.org
raw_api_id = os.getenv('API_ID', '').strip()
API_ID = int(raw_api_id) if raw_api_id.isdigit() else 0
API_HASH = os.getenv('API_HASH', '')

# AI gateway configuration (Anthropic-compatible)
# Optional: powers the agentic `.ask` command in userbot/ai_agent.py
# AI_BASE_URL has no default — set it in .env to the gateway you use. Without
# it the AI features stay off, the same as an absent AI_API_KEY.
AI_API_KEY = os.getenv('AI_API_KEY', '')
AI_BASE_URL = os.getenv('AI_BASE_URL', '').rstrip('/')
AGENT_MODEL = os.getenv('AGENT_MODEL', 'claude-opus-4-8')
# Image requests need a vision-capable model. Kept separate from AGENT_MODEL so
# cheapest-model auto-selection can't route an image at a text-only model.
AGENT_VISION_MODEL = os.getenv('AGENT_VISION_MODEL', 'claude-opus-4-8')
AGENT_MAX_TOKENS = int(os.getenv('AGENT_MAX_TOKENS', '2048'))

# Agent behaviour / safety limits
AGENT_TOOL_TIMEOUT = int(os.getenv('AGENT_TOOL_TIMEOUT', '60'))          # seconds per shell command
AGENT_MAX_OUTPUT_CHARS = int(os.getenv('AGENT_MAX_OUTPUT_CHARS', '6000'))  # per tool result
AGENT_MAX_ITERATIONS = int(os.getenv('AGENT_MAX_ITERATIONS', '12'))       # tool-use loop cap
AGENT_MAX_HISTORY = int(os.getenv('AGENT_MAX_HISTORY', '20'))             # per-chat memory cap
AGENT_AUTO_COMPACT = os.getenv('AGENT_AUTO_COMPACT', 'true').lower() in ('true', '1', 'yes')
AGENT_COMPACT_THRESHOLD = int(os.getenv('AGENT_COMPACT_THRESHOLD', '14'))

# Model auto-selection: pick the cheapest model the gateway advertises
AGENT_USE_CHEAPEST_MODEL = os.getenv('AGENT_USE_CHEAPEST_MODEL', 'false').lower() in ('true', '1', 'yes')
AGENT_PRICING_API_URL = os.getenv(
    'AGENT_PRICING_API_URL',
    f'{AI_BASE_URL}/api/pricing' if AI_BASE_URL else '',
)
AGENT_MODEL_CACHE_TTL = int(os.getenv('AGENT_MODEL_CACHE_TTL', '3600'))

# Shell access for the agent. Off by default: `.ask` prompts can embed text from
# replied-to messages written by other people, so letting the model run commands
# turns that text into an injection path. `.eval`/`.sh` stay available for the
# owner to run commands directly.
AGENT_ALLOW_SHELL = os.getenv('AGENT_ALLOW_SHELL', 'false').lower() in ('true', '1', 'yes')

# Moderation (ban/kick/mute/promote, deleting and pinning messages) for the
# agent. Off by default for the same reason as AGENT_ALLOW_SHELL: `.ask` embeds
# other people's message text into the prompt, so an armed moderation tool turns
# that text into a way to get people removed. The tools also refuse to touch the
# chat owner, other admins, or the userbot itself, and cap how many actions one
# `.ask` run may take -- but the flag is the real gate.
AGENT_ALLOW_MODERATION = os.getenv('AGENT_ALLOW_MODERATION', 'false').lower() in ('true', '1', 'yes')

# The whole Telegram API for the agent: any Pyrogram client method, not just the
# moderation subset. This is strictly more dangerous than AGENT_ALLOW_MODERATION
# -- calling `ban_chat_member` directly goes around the owner/admin/self refusals
# and the per-run action cap those tools apply, and it reaches every chat the
# account is in, not only the one `.ask` ran in. Session- and account-ending
# methods (log_out, cloud password, handlers, raw `invoke`) stay blocked either
# way. Enable it only where you would hand the same person the account.
AGENT_ALLOW_TELEGRAM_API = os.getenv('AGENT_ALLOW_TELEGRAM_API', 'false').lower() in ('true', '1', 'yes')

# Optional: YT_DLP API Key for YouTube downloads
YT_DLP_API_KEY = os.getenv('YT_DLP_API_KEY', '')

# YT_DLP Base URL configuration
YT_DLP_BASE_URL = os.getenv('YT_DLP_BASE_URL', 'https://api.nubcoders.com')

# MongoDB connection (optional)
# Leave MONGO_URI empty to run fully in-memory (data is lost on restart).
MONGO_URI = os.getenv('MONGO_URI', '')
DB_NAME = os.getenv('DB_NAME', 'userbot')

from storage import MemoryCollection, SqliteCollection

# Backend selection: STORAGE_BACKEND=mongo|sqlite|memory. When unset, keep the
# original behavior — mongo if MONGO_URI is set, else memory.
STORAGE_BACKEND = os.getenv('STORAGE_BACKEND', '').strip().lower()
SQLITE_PATH = os.getenv('SQLITE_PATH', os.path.join(os.getcwd(), 'data', 'sessions.db'))


def _init_storage():
    backend = STORAGE_BACKEND or ('mongo' if MONGO_URI else 'memory')
    if backend == 'mongo':
        try:
            client = pymongo.MongoClient(
                MONGO_URI, tlsCAFile=certifi.where(), serverSelectionTimeoutMS=5000
            )
            # Force an actual connection so a bad URI/unreachable host fails fast here
            client.admin.command("ping")
            logger.info("Connected to MongoDB (database: %s)", DB_NAME)
            return client, client[DB_NAME]["user_sessions"]
        except Exception as e:
            logger.warning(
                "MongoDB connection failed (%s); falling back to in-memory storage. "
                "Data will not persist across restarts.", e
            )
            return None, MemoryCollection()
    if backend == 'sqlite':
        logger.info("Using SQLite storage at %s", SQLITE_PATH)
        return None, SqliteCollection(SQLITE_PATH)
    logger.info("Using in-memory storage. Data will not persist across restarts.")
    return None, MemoryCollection()


mongo_client, user_sessions = _init_storage()
db = mongo_client[DB_NAME] if mongo_client else None

# Command prefixes recognized by the userbot
HARDCODED_PREFIXES = ["!", ".", "?", "^", "_"]

# File-based admin list (legacy)
admin_file = os.path.join(os.getcwd(), "data", "admins.txt")

# Global variables
clients = {}
conversations = {}
chat_queues = {}
active_streams = {}
last_response_time = {}
used_words = {}
active = {}
songs_client = {}
IGNORE_DURATION = 5
StartTime = time.time()

# Sudo users cache: {owner_id: [sudo_user_id, ...]}
from collections import defaultdict
SUDO = defaultdict(list)

from pyrogram import Client, filters
from convopyro import Conversation

# Optional: Your support group username (without @)
GROUP = os.getenv('GROUP', 'nub_coder_s')

# Optional: Your updates channel username (without @)
CHANNEL = os.getenv('CHANNEL', 'nub_coders')

# Optional: Get from @BotFather on Telegram (used for inline bot features)
BOT_TOKEN = os.getenv('BOT_TOKEN', '')

# Required: Your Pyrogram String Session
SESSION_STR = os.getenv('SESSION_STR', '')

apps= {}

# External community plugins (Phase 5): drop *.py files in EXTRA_PLUGINS_DIR and
# they load at startup. loaded_extra_plugins is populated by main.py and read by
# the .plugins command.
EXTRA_PLUGINS_DIR = os.getenv('EXTRA_PLUGINS_DIR', os.path.join(os.getcwd(), 'plugins'))
loaded_extra_plugins = []
