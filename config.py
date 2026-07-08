import os
import time
import pymongo
import certifi

# Telegram API credentials
# Required: Get these from https://my.telegram.org
API_ID = int(os.getenv('API_ID', 0))
API_HASH = os.getenv('API_HASH', '')

# Gemini API configuration
# Optional: Get from https://aistudio.google.com/app/apikey (needed for AI features)
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY', '')

# Optional: NUB_YTDLP API Key for YouTube downloads
NUB_YTDLP_API_KEY = os.getenv('NUB_YTDLP_API_KEY', os.getenv('NUBYTDLP_API', ''))

# NUB_YTDLP Base URL configuration
NUB_YTDLP_BASE_URL = os.getenv('NUB_YTDLP_BASE_URL', os.getenv('YTDLP_BASE_URL', 'http://api.nubcoders.com'))

# Optional: Backward-compatible alias for older environment variable names
YTDLP_BASE_URL = NUB_YTDLP_BASE_URL

# MongoDB connection (optional)
MONGO_URI = os.getenv('MONGO_URI', '')
DB_NAME = os.getenv('DB_NAME', 'userbot')

import copy

class _MemoryResult:
    """Mimics pymongo UpdateResult / InsertOneResult."""
    def __init__(self, matched=0, modified=0, inserted_id=None):
        self.matched_count = matched
        self.modified_count = modified
        self.inserted_id = inserted_id

class _MemoryCollection:
    """In-memory MongoDB-compatible collection. Works while the bot runs, lost on restart."""
    def __init__(self):
        self._docs = {}

    def _key(self, filt):
        return filt.get("user_id")

    def find_one(self, filt=None, *a, **kw):
        if not filt:
            return None
        doc = self._docs.get(self._key(filt))
        return copy.deepcopy(doc) if doc else None

    def insert_one(self, doc, *a, **kw):
        key = doc.get("user_id")
        self._docs[key] = copy.deepcopy(doc)
        return _MemoryResult(inserted_id=key)

    def update_one(self, filt, update, *a, upsert=False, **kw):
        key = self._key(filt)
        doc = self._docs.get(key)
        if doc is None:
            if not upsert:
                return _MemoryResult()
            doc = dict(filt)
            self._docs[key] = doc
        for op, fields in update.items():
            if op == "$set":
                doc.update(fields)
            elif op == "$unset":
                for f in fields:
                    doc.pop(f, None)
            elif op == "$push":
                for f, v in fields.items():
                    doc.setdefault(f, []).append(v)
            elif op == "$pull":
                for f, v in fields.items():
                    lst = doc.get(f, [])
                    if v in lst:
                        lst.remove(v)
            elif op == "$addToSet":
                for f, v in fields.items():
                    lst = doc.setdefault(f, [])
                    if v not in lst:
                        lst.append(v)
            elif op == "$inc":
                for f, v in fields.items():
                    doc[f] = doc.get(f, 0) + v
        return _MemoryResult(matched=1, modified=1)

    def delete_one(self, filt, *a, **kw):
        key = self._key(filt)
        self._docs.pop(key, None)
        return _MemoryResult(matched=1)

    def find(self, filt=None, *a, **kw):
        if not filt:
            return list(self._docs.values())
        return [d for d in self._docs.values() if all(d.get(k) == v for k, v in filt.items())]

if MONGO_URI:
    mongo_client = pymongo.MongoClient(MONGO_URI, tlsCAFile=certifi.where())
    db = mongo_client[DB_NAME]
    user_sessions = db['user_sessions']
else:
    mongo_client = None
    db = None
    user_sessions = _MemoryCollection()

# Command prefixes recognized by the userbot
HARDCODED_PREFIXES = ["!", ".", "?", "^", "_"]

# File-based admin list (legacy)
admin_file = os.path.join(os.getcwd(), "data", "admins.txt")

# Global variables
clients = {}
RAIDS = {}
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

ggg = os.getcwd()
from fonts import *
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

# Optional: The username of your userbot account (without @) to use in menus
USERBOT_USERNAME = os.getenv('USERBOT_USERNAME', '')
apps= {}
