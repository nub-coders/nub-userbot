# WordSeek Auto-Player Configuration
# Customize settings for auto-player behavior

# Enable/Disable auto-player
AUTO_ENABLED = True

# Delay between guesses (in seconds)
# Higher values = more respectful to bot API
AUTO_DELAY = 1.5

# Maximum guesses allowed per game
MAX_GUESSES = 30

# Minimum word confidence threshold (0.0 - 1.0)
# Higher = only guess high-confidence words
MIN_WORD_CONFIDENCE = 0.3

# Debug mode - prints detailed logging
DEBUG_MODE = False

# Word data files (relative to project root)
WORD_FILES = {
    'all_words': 'allWords.json',
    'common_words': 'commonWords.json',
    'daily_words': 'daily-word-lists.json',
}

# Game settings
GAME_SETTINGS = {
    # Primary active length (keeps backward compatibility)
    'word_length': 5,
    # Supported word lengths for WordSeek (add 4 and 6 support)
    'supported_lengths': [4, 5, 6],
    'max_attempts': 30,
    'start_command': '/new',
    'end_command': '/end',
    'daily_command': '/daily',
}

# Output settings
LOGGING = {
    'level': 'INFO',
    'format': '[AUTO-GAME] %(levelname)s - %(message)s',
}

# Telegram settings
TELEGRAM = {
    'message_delay': 1.5,  # Delay between messages to avoid rate limits
    'emoji_feedback': True,  # Parse emoji feedback from bot
    'verify_responses': True,  # Verify bot responses before proceeding
}

# Advanced settings
SOLVER_SETTINGS = {
    'use_letter_frequency': True,
    'prefer_common_words': True,
    'dynamic_difficulty': False,
    'learn_patterns': False,
}
