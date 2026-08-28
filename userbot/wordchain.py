
from pyrogram import Client, filters, enums
import random
import re
import asyncio
from config import *
from tools import *

import logging
logger = logging.getLogger("wordchain")

used_words = {}

# Remembering every word ever sent in a chat is what the list is for, but it had
# no ceiling: one long-lived process playing in a few groups grew it without
# limit. Keep the recent history, which is what matters within a game, and let
# older entries go. `.clr` still wipes a chat outright.
_MAX_USED_WORDS = 500

# words.txt is 9.5MB / 880k lines. Reading and splitting it takes 358ms and the
# filtering another 60ms, and this ran on the event loop for every single turn --
# nearly half a second during which no other handler could make progress, plus
# 9.5MB of disk read. Load it once, off the loop, and keep it.
_WORD_CACHE = {}
_WORD_CACHE_LOCK = asyncio.Lock()


def _load_words(filename):
    """Read and clean the word list. Blocking -- call through asyncio.to_thread."""
    try:
        with open(filename, 'r') as file:
            words = file.read().splitlines()
    except OSError as e:
        logger.warning(f"Could not read word file {filename}: {e}")
        return []
    # Hoisted out of the per-call filter below: the same test, applied once.
    return [word for word in words if re.fullmatch("[A-Za-z]+", word)]


def _filter_words(words, start_letter, word_length, include_letter):
    # ponytail: on9wordchainbot source says "at least N letters", but empirically
    # rejects longer words - using exact match
    return [
        word for word in words
        if word.startswith(start_letter)
        and (not include_letter or include_letter in word)
        and len(word) == word_length
    ]


async def find_random_words(filename, start_letter, word_length, include_letter=None):
    """Words matching the puzzle's constraints, or None if there are none."""
    async with _WORD_CACHE_LOCK:
        if filename not in _WORD_CACHE:
            _WORD_CACHE[filename] = await asyncio.to_thread(_load_words, filename)
    words = _WORD_CACHE[filename]
    if not words:
        return None
    filtered_words = await asyncio.to_thread(
        _filter_words, words, start_letter, word_length, include_letter
    )
    return filtered_words or None

pattern = r"(is accepted\.|has been used\.|is not)"

# Listen to messages from the specific user @on9wordchainbot in a group context
# filters.text: without it a photo or a service message from the bot arrived with
# message.text as None, and the "Turn:" test below raised TypeError.
# No @retry(): it re-runs the whole handler from the top, so a FloodWait midway
# through a turn replayed the send and put a second word into the chat. A lost
# turn is better than a duplicate guess, and the loop below already retries.
@Client.on_message(filters.user("on9wordchainbot") & filters.group & filters.text)
async def wordchain_listener(client, message):
    text = message.text or ""
    # Check if the message contains "Turn:" and a user mention immediately after
    if "Turn:" in text:
        try:
            # Extract mentions from the message using markdown format
            entities = message.entities or []
            first_mention = None
            for entity in entities:
                # Look for the first mention after "Turn:"
                if entity.type == enums.MessageEntityType.TEXT_MENTION:
                    if "Turn:" in text and text.index("Turn:") < entity.offset:
                        first_mention = entity.user
                        break

            # Verify if the first mention matches the current user ID
            if first_mention and first_mention.id == client.me.id:
                # Both of these used to .group() the match object directly. When
                # the bot phrases a turn differently -- a mode with no length
                # requirement, a hint line, a translated string -- the search
                # returns None and the whole handler died on AttributeError.
                # Skip the turn instead.
                info_match = re.search(r"Your word must start with (.+)", text)
                if not info_match:
                    logger.debug("wordchain: no word requirement in the turn message")
                    return
                word_info_line = info_match.group(1)
                # Extract capital letters and word length from the word info line
                capital_letters = re.findall(r'[A-Z]', word_info_line)
                length_match = re.search(r'\d+', word_info_line)
                if not length_match:
                    logger.debug("wordchain: no word length in %r", word_info_line)
                    return
                word_length = int(length_match.group())


                # Determine the starting letter and included letter
                if len(capital_letters) == 1:
                    start_letter = capital_letters[0]
                    include_letter = None
                elif len(capital_letters) == 2:
                    start_letter = capital_letters[0]
                    include_letter = capital_letters[1]
                else:
                    return

                # Find a random word based on the criteria
                filtered_words = await find_random_words("words.txt", start_letter, word_length, include_letter)
                if not filtered_words:
                    await bot.send_message(client.me.id, "No suitable word found.")
                    return

                # Initialize chat ID and used word list if not exists
                chat_id = message.chat.id
                if chat_id not in used_words:
                    used_words[chat_id] = []

                # Retry up to 5 times: pick an unused random word and send it
                for _ in range(5):
                    available = [w for w in filtered_words if w not in used_words[chat_id]]
                    if not available:
                        break
                    random_word = random.choice(available)

                    user_data = user_sessions.find_one({"user_id": client.me.id})
                    if user_data and not user_data.get('game', True):
                        logger.debug("wordchain: game is off, returning.")
                        return

                    await asyncio.sleep(4)
                    used_words[chat_id].append(random_word)
                    # Keep only the recent history; see _MAX_USED_WORDS above.
                    del used_words[chat_id][:-_MAX_USED_WORDS]
                    await client.send_chat_action(chat_id, enums.ChatAction.TYPING)
                    await client.send_message(chat_id, random_word)
                    try:
                        response = await client.listen.Message(
        filters.regex(pattern) & filters.user(message.from_user.id) & filters.chat(message.chat.id),
        timeout=4
    )
                        if response.entities:
                         for entity in response.entities:
                          if entity.type == enums.MessageEntityType.ITALIC:
                             italic_text = response.text[entity.offset:entity.offset + entity.length]
                             if random_word.lower() in italic_text.lower():
                                if "is not" in response.text.lower() or "has been used." in response.text.lower():
                                   break
                                elif "is accepted." in response.text.lower():
                                   logger.debug("wordchain: word accepted")
                                   return
                    except Exception as e:
                       logger.debug(f"wordchain: response wait failed: {e}")
                       return

        except Exception:
           # This used to DM the raw exception to the owner's saved messages,
           # parsed as HTML: an exception repr containing angle brackets came out
           # mangled or empty, and a turn message the bot had rephrased spammed
           # the DM on every single turn. A traceback belongs in the log.
           logger.exception("wordchain: turn handling failed")


@Client.on_message(filters.command("clr", prefixes=HARDCODED_PREFIXES) & filters.me)
@retry()
async def reset_used_words(client, message):
    chat_id = message.chat.id

    if chat_id in used_words:
        del used_words[chat_id]  # Remove all stored words for this chat
        await message.reply("All used words have been reset.")
    else:
        await message.reply("No used words to reset.")

