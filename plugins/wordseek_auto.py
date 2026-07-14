"""
WordSeek Auto-Player Plugin for Userbot
Automatically plays WordSeek Telegram bot games with intelligent solving
"""

import asyncio
import json
import re
import logging
from typing import Dict, Optional, List
from pyrogram import Client, filters, enums
from pyrogram.types import Message
from plugins.game_solver import get_solver
from tools import *
import wordseek_config as ws_config
# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Active game states: {chat_id: game_state}
# Active game states: {chat_id: game_state}
ACTIVE_GAMES: Dict[int, Dict] = {}
# Configuration
AUTO_DELAY = 4.0  # Seconds between guesses

# Trigger words - auto-play only starts when user types one of these
# Keep starter words aligned with supported game lengths.
TRIGGER_WORDS = {
    # 4-letter starters
    'ABLE',
    'ACID',
    'ACRE',
    'AFAR',
    'AFRO',
    'DARE',
    'SALT',
    'COIN',
    'HARE',
    'LIME',
    # 5-letter starters
    'STARE',
    'SLATE',
    'CRATE',
    'TRADE',
    'BLAZE',
    'CRANE',
    'FLARE',
    'GRACE',
    'SHADE',
    'TRACE',
    'AUDIO',
    'AROSE',
    'ADORE',
    # 6-letter starters
    'ABATED',
    'ABDUCT',
    'ABJECT',
    'ABOARD',
    'ABLAZE',
    'ABOUND',
    'ABROAD',
    'ABSENT',
    'ABSORB',
    'ABRUPT',
    'CASTLE',
    'ACTION',
    'BRIDGE',
    'DESIGN',
    'FACTOR',
}

def init_game_state(chat_id: int, word_length: int = None) -> Dict:
    """Initialize a new game state"""
    return {
        'chat_id': chat_id,
        'known_letters': {},  # {char: [wrong_positions]}
        'excluded_letters': set(),
        'position_hints': {},  # {pos: char}
        'min_letter_count': {},  # {char: int} — at least this many
        'max_letter_count': {},  # {char: int} — at most this many
        'guesses_made': 0,
        'attempts_left': 30,
        'game_active': True,
        'word_solution': None,
        'used_words': [],  # Store all guessed words
        'patterns': {},  # {word: feedback_pattern}
        'waiting_for_reply': False,  # Flag to prevent sending multiple words
        'last_sent_word': None,  # Track the last sent word
        'word_length': word_length,  # Set from trigger word length
    }


def get_supported_lengths() -> List[int]:
    """Return the supported WordSeek lengths from the live solver when possible."""
    try:
        solver_lengths = sorted(get_solver().all_words_by_length.keys())
        if solver_lengths:
            return solver_lengths
    except Exception as exc:
        logger.warning(f"[AUTO-GAME] Failed to read solver lengths: {exc}")

    configured = ws_config.GAME_SETTINGS.get('supported_lengths', [5])
    lengths = [length for length in configured if isinstance(length, int)]
    return lengths or [5]


def safe_text_preview(text: Optional[str], limit: int = 150) -> str:
    """Safely render text for logging without surrogate slicing errors."""
    if not text:
        return ""
    try:
        clean = text.encode("utf-16", "surrogatepass").decode("utf-16", "ignore")
    except Exception:
        clean = str(text)
    if len(clean) > limit:
        return f"{clean[:limit]}…"
    return clean


def parse_feedback_from_message(message_text: str) -> Optional[dict]:
    """
    Extract all words and their emoji feedback from bot message
    Looks for patterns like: 🟩 🟩 🟥 🟩 🟥 𝗕𝗘𝗔𝗡𝗦
    Returns: {word: feedback_string} dict
    """
    logger.debug(f"[PARSE] Attempting to parse message: {repr(safe_text_preview(message_text, 200))}")
    results = {}
    
    # Pattern: 4-6 emojis (with or without spaces) followed by a word
    # Match emoji sequence and extract the word after them
    lines = message_text.split('\n')
    logger.debug(f"[PARSE] Split into {len(lines)} lines")
    
    for i, line in enumerate(lines):
        logger.debug(f"[PARSE] Line {i}: {repr(safe_text_preview(line, 200))}")
        # Capture 4 to 6 emoji symbols in a row, then the word
        emoji_seq_pattern = r'((?:🟩|🟨|🟥)(?:\s*(?:🟩|🟨|🟥)){3,5})\s+([\w\U0001D400-\U0001D7FF]+)'
        match = re.search(emoji_seq_pattern, line)

        if match:
            # Group 1 contains the emoji sequence (with spaces); extract individual emojis
            emoji_seq = match.group(1)
            emojis = re.findall(r'(🟩|🟨|🟥)', emoji_seq)
            feedback = ''.join(emojis)
            word_raw = match.group(2)
            
            # Convert bold/styled Unicode letters to regular ASCII if needed
            import unicodedata
            word = unicodedata.normalize('NFKD', word_raw).upper()
            results[word] = feedback
            logger.info(f"[PARSE] ✓ Parsed: {word} → {feedback} (raw: {word_raw})")
        else:
            logger.debug(f"[PARSE] ✗ No match on line {i}")
    
    logger.info(f"[PARSE] Final results: {results if results else 'None'}")
    return results if results else None


def is_game_over_message(text: str) -> bool:
    """Check if message indicates game is over"""
    game_over_keywords = [
        'congrats! you guessed it correctly.',
        'game over',
        'the word was',
        'correct word:',
        'congratulations',
        'won',
        'lost',
        'no more guesses',
        'out of attempts',
    ]
    text_lower = text.lower()
    return any(keyword in text_lower for keyword in game_over_keywords)


def is_game_started_message(text: str) -> bool:
    """Check if message indicates a game has started"""
    start_keywords = ['game started', 'new game', 'start a new game']
    t = text.lower()
    return bool(any(k in t for k in start_keywords) or re.search(r'guess the\s*\d', t))


def _is_game_bot_response(_, __, message: Message) -> bool:
    """Match a supported game bot message carrying feedback or a game-over notice."""
    if not (message.from_user and (message.from_user.username or '').lower() in ['wordseekbot', 'crocodilegameenn_bot']):
        return False
    text = message.text or ""
    has_emoji = '🟩' in text or '🟨' in text or '🟥' in text
    text_lower = text.lower()
    has_game_over = ('congrats' in text_lower or 'word was' in text_lower or
                     'correct word' in text_lower or 'game over' in text_lower)
    return has_emoji or has_game_over


async def wait_for_bot_response(client: Client, chat_id: int, timeout: int = 10):
    """
    Wait for a supported game bot response with feedback (or a game-over notice).
    Returns the bot's message, or None if the timeout elapses.
    """
    try:
        message = await client.listen.Message(
            filters.chat(chat_id) & filters.create(_is_game_bot_response),
            timeout=timeout,
        )
        if message:
            logger.info(f"[WAIT] ✓ Valid bot response found (ID: {message.id})")
            logger.info(f"[WAIT] Full message text:\n{safe_text_preview(message.text, 2000)}")
        return message
    except asyncio.TimeoutError:
        logger.warning(f"[WAIT] Timeout after {timeout}s waiting for bot response in chat {chat_id}")
        return None


async def play_game_loop(client: Client, chat_id: int):
    """
    Main game loop - waits for bot responses and sends next guesses
    """
    if chat_id not in ACTIVE_GAMES:
        logger.warning(f"[LOOP] No active game for chat {chat_id}")
        return
    
    game = ACTIVE_GAMES[chat_id]

    while game['game_active'] and game['attempts_left'] > 0:
        # Wait for bot response
        bot_message = await wait_for_bot_response(client, chat_id)
        
        if not bot_message:
            logger.warning(f"[LOOP] No bot response received, stopping game")
            ACTIVE_GAMES.pop(chat_id, None)
            break
        
        # Check if game is over
        if is_game_over_message(bot_message.text):
            logger.info(f"[LOOP] Game ended in chat {chat_id}")
            logger.info(f"[LOOP] Bot message: {bot_message.text[:100]}")
            
            # Extract solution word (support multiple lengths)
            lengths = get_supported_lengths()
            min_len = min(lengths)
            max_len = max(lengths)
            solution_pattern = rf'(?:word was:|correct word:)\s*(\w{{{min_len},{max_len}}})'
            match = re.search(solution_pattern, bot_message.text.lower())
            if match:
                game['word_solution'] = match.group(1)
                logger.info(f"[LOOP] Solution: {game['word_solution']}")
            
            # Clean up
            ACTIVE_GAMES.pop(chat_id, None)
            logger.info(f"[LOOP] Cleaned up game data for chat {chat_id}")
            break
        
        # Handle duplicate-word response (no feedback provided)
        message_lower = (bot_message.text or "").lower()
        if "someone has already guessed your word" in message_lower:
            logger.info("[LOOP] Duplicate word detected; selecting a new guess")
            if game.get('last_sent_word') and game['last_sent_word'] not in game['used_words']:
                game['used_words'].append(game['last_sent_word'])
                logger.info(f"[LOOP] Marked as used: {game['last_sent_word']}")
        else:
            # Parse feedback from bot message
            logger.debug(f"[LOOP] Bot message text: {bot_message.text}")
            feedback = parse_feedback_from_message(bot_message.text)
            
            if not feedback or not isinstance(feedback, dict):
                logger.warning(f"[LOOP] Could not parse feedback from message: {safe_text_preview(bot_message.text, 200)}")
                ACTIVE_GAMES.pop(chat_id, None)
                break
        
            # Process all words found in the message
            for word, word_feedback in feedback.items():
                # Skip if already processed
                if word in game['used_words']:
                    logger.debug(f"[LOOP] Word {word} already processed, skipping")
                    continue
                
                # Validate feedback length matches the word length and is supported
                supported = get_supported_lengths()
                if len(word_feedback) not in supported or len(word_feedback) != len(word):
                    logger.warning(f"[LOOP] Invalid feedback length or mismatch for {word}: {word_feedback}")
                    continue
            
                # Store word and pattern
                game['used_words'].append(word)
                game['patterns'][word] = word_feedback
            
                logger.info(f"[LOOP] Feedback: {word} → {word_feedback}")
            
                # Record detected word length for this game
                game['word_length'] = len(word_feedback)

                # Analyze feedback (now returns 5-tuple with letter count constraints)
                solver = get_solver()
                known_letters, excluded_letters, position_hints, min_lc, max_lc = solver.analyze_feedback(
                    word, word_feedback
                )
            
                # Update game state
                for ch, positions in known_letters.items():
                    if ch not in game['known_letters']:
                        game['known_letters'][ch] = []
                    for p in positions:
                        if p not in game['known_letters'][ch]:
                            game['known_letters'][ch].append(p)
                            
                game['excluded_letters'].update(excluded_letters)
                game['position_hints'].update(position_hints)

                # Merge letter-count constraints (take the tightest bounds)
                for ch, mc in min_lc.items():
                    game['min_letter_count'][ch] = max(game['min_letter_count'].get(ch, 0), mc)
                for ch, mc in max_lc.items():
                    prev = game['max_letter_count'].get(ch)
                    game['max_letter_count'][ch] = mc if prev is None else min(prev, mc)
                
                game['guesses_made'] += 1
                game['attempts_left'] -= 1
            
            logger.info(f"[LOOP] Guesses made: {game['guesses_made']}/30")
            logger.info(f"[LOOP] Used words: {game['used_words']}")
        
        # Get next guess
        await asyncio.sleep(AUTO_DELAY)
        
        solver = get_solver()
        # Prefer the detected game length, then the live supported default
        target_length = game.get('word_length') or get_supported_lengths()[0]
        candidates = solver.filter_candidates(
            game['known_letters'],
            game['excluded_letters'],
            game['position_hints'],
            word_length=target_length,
            min_letter_count=game.get('min_letter_count', {}),
            max_letter_count=game.get('max_letter_count', {}),
        )
        
        # Filter out already used words
        # Normalize used words to lowercase for comparison
        used_lower = {u.lower() for u in game.get('used_words', [])}
        available_candidates = [w for w in candidates if w not in used_lower]
        
        if available_candidates:
            next_guess = solver.get_best_guess(available_candidates, game['position_hints'],
                                                word_length=target_length)
            # Ensure first letter is uppercase when sending
            send_word = next_guess.capitalize()
            game['last_sent_word'] = send_word

            logger.debug(f"[LOOP] Next guess: {next_guess} ({len(available_candidates)} candidates)")

            # Send the word to the bot
            await client.send_chat_action(chat_id, enums.ChatAction.TYPING)
            logger.info(f"[LOOP] Sending word: '{send_word}'")
            await client.send_message(chat_id, send_word)
        else:
            logger.warning(f"[LOOP] No available candidates found!")
            ACTIVE_GAMES.pop(chat_id, None)
            break




@Client.on_message(
    filters.text
    & (filters.user(['wordseekbot', 'crocodilegameenn_bot']) | filters.group)
    & ~filters.incoming
)
async def auto_play_handler(client: Client, message: Message):
    """Handle auto-play of WordSeek game - trigger words and user input"""
    chat_id = message.chat.id
    text = message.text.strip().upper()
    
    # Skip bot commands
    if text.startswith('/'):
        return
    
    # Skip if an active game already exists
    if chat_id in ACTIVE_GAMES:
        return

    # Determine if we should start auto-play:
    # 1. Direct trigger word match
    is_trigger_word = text in TRIGGER_WORDS
    
    # 2. Any valid length guess word in a private bot chat
    supported_lens = get_supported_lengths()
    is_valid_len_word = len(text) in supported_lens and text.isalpha()
    is_private_bot = message.chat.type == enums.ChatType.PRIVATE and (message.chat.username or '').lower() in ['wordseekbot', 'crocodilegameenn_bot']
    
    # 3. Any valid length guess word in a group chat where a game was recently started
    is_game_active_in_group = False
    if not is_private_bot and is_valid_len_word and message.chat.type in (enums.ChatType.GROUP, enums.ChatType.SUPERGROUP):
        try:
            async for msg in client.get_chat_history(chat_id, limit=5):
                if msg.from_user and (msg.from_user.username or '').lower() in ['wordseekbot', 'crocodilegameenn_bot']:
                    if msg.text and is_game_started_message(msg.text):
                        is_game_active_in_group = True
                        break
        except Exception as e:
            logger.debug(f"[AUTO-GAME] Error checking chat history: {e}")

    should_start = is_trigger_word or (is_valid_len_word and (is_private_bot or is_game_active_in_group))
    
    if should_start:
        trigger_length = len(text)
        logger.info(f"[AUTO-GAME] Starting auto-play with word '{text}' ({trigger_length} letters)")
        ACTIVE_GAMES[chat_id] = init_game_state(chat_id, word_length=trigger_length)
        game = ACTIVE_GAMES[chat_id]
        game['last_sent_word'] = text
        
        logger.info(f"[AUTO-GAME] Starting game loop for first word: {text}")
        await play_game_loop(client, chat_id)


@Client.on_message(filters.command('gameinfo', prefixes=HARDCODED_PREFIXES))
async def show_game_info(client: Client, message: Message):
    """Show current game information"""
    chat_id = message.chat.id
    
    if chat_id not in ACTIVE_GAMES:
        await message.reply("No active auto-game.")
        return
    
    game = ACTIVE_GAMES[chat_id]
    
    info = f"""
📊 **Game Information**
━━━━━━━━━━━━━━━━━━━
• **Status:** {'Active' if game['game_active'] else 'Ended'}
• **Guesses Made:** {game['guesses_made']}/30
• **Attempts Left:** {game['attempts_left']}
• **Confirmed Letters:** {len(game['position_hints'])}
• **Excluded Letters:** {len(game['excluded_letters'])}
• **Known Letters:** {len(game['known_letters'])}

📍 **Position Hints:**
{', '.join(f'{k}: {v}' for k, v in sorted(game['position_hints'].items())) if game['position_hints'] else 'None'}

🚫 **Excluded:** {', '.join(sorted(game['excluded_letters'])) if game['excluded_letters'] else 'None'}
    """
    
    await message.reply(info)


@Client.on_message(filters.command('wordseek',prefixes=HARDCODED_PREFIXES) & filters.me)
async def wordseek_info(client: Client, message: Message):
    """Show WordSeek auto-play info and trigger words"""
    chat_id = message.chat.id
    supported = get_supported_lengths()

    words = ", ".join(sorted(TRIGGER_WORDS))
    info = (
        "🎮 **WordSeek Auto-Play**\n"
        "━━━━━━━━━━━━━━━━━━━\n"
        "• **How to start:** Send any trigger word below\n"
        f"• **Trigger words:** {words}\n"
        f"• **Supported word lengths:** {supported}\n"
        "• **Note:** The bot will auto-guess after the first word\n"
    )
    await message.reply(info)


# Manual guess submission
@Client.on_message(
    filters.text & 
    ~filters.regex(r"^/") & 
    ~filters.incoming
)
async def manual_guess(client: Client, message: Message):
    """Handle manual word guesses in auto-game"""
    chat_id = message.chat.id
    
    # Check if game is won
    if "Congrats! You guessed it correctly." in message.text:
        logger.info(f"[AUTO-GAME] Game won in chat {chat_id}")
        
        # Clean up saved things for this chat
        if chat_id in ACTIVE_GAMES:
            ACTIVE_GAMES.pop(chat_id, None)
            logger.info(f"[AUTO-GAME] Cleaned up game data for chat {chat_id}")
        
        return
    
    if chat_id not in ACTIVE_GAMES:
        return
    
    word = message.text.strip().lower()
    
    # Validate supported word lengths
    supported = get_supported_lengths()
    if not (len(word) in supported and word.isalpha()):
        return
    
    game = ACTIVE_GAMES[chat_id]
    game['last_sent_word'] = word
    
    logger.info(f"[AUTO-GAME] Manual guess: {word}")
