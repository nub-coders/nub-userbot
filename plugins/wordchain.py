
from pyrogram import Client, filters
from pyrogram.types import Message
from pyrogram import enums
import random
import re
import asyncio
from config import *
from tools import *

used_words = {}

def find_random_words(filename, start_letter, word_length, include_letter=None):
    try:
        with open(filename, 'r') as file:
            words = file.read().splitlines()  # Read words from the file
    except FileNotFoundError:
        print(f"Error: The file '{filename}' was not found.")
        return []

    # Filtering words based on criteria
    filtered_words = [
        word for word in words
        if word.startswith(start_letter) and
           (not include_letter or include_letter in word) and
           len(word) >= word_length and len(word) >3 and re.match("^[A-Za-z]+$", word)
    ]

    if not filtered_words:
        return None

    return filtered_words

pattern = r"(is accepted\.|has been used\.|is not)"

# Listen to messages from the specific user @on9wordchainbot in a group context
@Client.on_message(filters.user("on9wordchainbot") & filters.group)
@retry()
async def wordchain_listener(client, message):
    text = message.text
    # Check if the message contains "Turn:" and a user mention immediately after
    if "Turn:" in text:
        try:
            # Extract mentions from the message using markdown format
            entities = message.entities or []
            first_mention = None
            for entity in entities:
                # Look for the first mention after "Turn:"
                if entity.type == enums.MessageEntityType.TEXT_MENTION:
                    if "Turn:" in text and message.text.index("Turn:") < entity.offset:
                        first_mention = entity.user
                        break

            # Verify if the first mention matches the current user ID
            if first_mention and first_mention.id == client.me.id:
                word_info_line = re.search(r"Your word must start with (.+)", text).group(1)
                # Extract capital letters and word length from the word info line
                capital_letters = re.findall(r'[A-Z]', word_info_line)
                word_length = int(re.search(r'\d+', word_info_line).group())


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
                filtered_words = find_random_words("words.txt", start_letter, word_length, include_letter)
                if not filtered_words:
                    await bot.send_message(client.me.id,f" No suitable word found.")
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
                        print("game is off, returning.")
                        return

                    await asyncio.sleep(4)
                    used_words[chat_id].append(random_word)
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
                                if f"is not" in response.text.lower() or f"has been used." in response.text.lower():
                                   break
                                elif f"is accepted." in response.text.lower():
                                   return print("worked1")
                    except Exception as e:
                       return print(e)

        except Exception as e:
           await bot.send_message(client.me.id,f"ERROR: {e}")


@Client.on_message(filters.command("clr") & filters.me)
@retry()
async def reset_used_words(client, message):
    chat_id = message.chat.id

    if chat_id in used_words:
        del used_words[chat_id]  # Remove all stored words for this chat
        await message.reply("All used words have been reset.")
    else:
        await message.reply("No used words to reset.")

