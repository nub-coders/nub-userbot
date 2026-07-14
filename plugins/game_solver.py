"""
WordSeek Game Solver - Auto-player for WordSeek Telegram bot
Analyzes game feedback and provides optimal word guesses
"""

import json
import os
from collections import Counter
from typing import Set, List, Dict, Tuple


class WordSolver:
    """
    Advanced solver for WordSeek (Wordle-like) game
    Uses letter frequency analysis and constraint filtering
    """

    def __init__(self):
        """Initialize solver with word lists from WordSeek"""
        # all_words_by_length: {length: set(words)}
        self.all_words_by_length = self._load_word_list('allWords.json')
        # common_words can remain a flat dict for lookups
        self.common_words = self._load_common_words('commonWords.json')
        # letter_frequency_by_length: {length: {char: freq}}
        self.letter_frequency = self._calculate_frequency()

    def _load_word_list(self, filename: str) -> Dict[int, Set[str]]:
        """Load words from JSON file and group by word length
        Returns dict: {length: set(words)}
        """
        words_by_len = {}
        
        # Try multiple paths
        paths = [
            f'{filename}',
            f'data/{filename}',
            f'plugins/data/{filename}',
            os.path.expanduser(f'~/{filename}'),
        ]
        
        for path in paths:
            if os.path.exists(path):
                try:
                    with open(path, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                        if isinstance(data, list):
                            items = [w for w in data if isinstance(w, str)]
                        elif isinstance(data, dict):
                            items = [w for w in data.keys() if isinstance(w, str)]
                        else:
                            items = []

                        for w in items:
                            w_clean = w.strip().lower()
                            wlen = len(w_clean)
                            if wlen == 0:
                                continue
                            words_by_len.setdefault(wlen, set()).add(w_clean)

                        if words_by_len:
                            total = sum(len(s) for s in words_by_len.values())
                            print(f"[SOLVER] Loaded {total} words (by lengths: {list(words_by_len.keys())}) from {path}")
                            return words_by_len
                except Exception as e:
                    print(f"[SOLVER] Error loading {path}: {e}")
                    continue
        
        # ponytail: no hardcoded fallback — trust the JSON word files
        print("[SOLVER] No word file found; returning empty set")
        return {}

    def _load_common_words(self, filename: str) -> Set[str]:
        """Load common words as a set for fast lookup.
        Handles both list and dict JSON formats.
        """
        paths = [
            f'{filename}',
            f'data/{filename}',
            f'plugins/data/{filename}',
        ]

        for path in paths:
            if os.path.exists(path):
                try:
                    with open(path, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                        if isinstance(data, list):
                            words = {w.strip().lower() for w in data if isinstance(w, str)}
                        elif isinstance(data, dict):
                            words = {w.strip().lower() for w in data.keys() if isinstance(w, str)}
                        else:
                            continue
                        print(f"[SOLVER] Loaded {len(words)} common words from {path}")
                        return words
                except Exception as e:
                    print(f"[SOLVER] Error loading {path}: {e}")
                    continue

        return set()

    def _calculate_frequency(self) -> Dict[int, Dict[str, int]]:
        """Calculate letter frequency per word length
        Returns dict: {length: {char: freq}}
        """
        frequency_by_len = {}

        for length, words in self.all_words_by_length.items():
            freq = {}
            for word in words:
                for char in set(word.lower()):
                    if char.isalpha():
                        freq[char] = freq.get(char, 0) + 1
            frequency_by_len[length] = freq

        return frequency_by_len

    def analyze_feedback(self, guess: str, feedback: str) -> Tuple[
        Dict[str, list], Set[str], Dict[int, str],
        Dict[str, int], Dict[str, int]
    ]:
        """
        Parse feedback from bot to extract constraints.
        Feedback format: 🟩🟨🟥🟩🟥 (one emoji per letter)

        Returns:
            known_letters:  {char: [wrong_positions]}  — char is in word but NOT at these positions
            excluded_letters: set of chars fully absent from the word
            position_hints:  {position: char}  — char is confirmed at this position
            min_letter_count: {char: int} — word must contain *at least* this many of char
            max_letter_count: {char: int} — word must contain *at most* this many of char
        """
        known_letters = {}   # {char: [wrong_positions]}
        excluded_letters = set()
        position_hints = {}  # {position: char}

        # Count how many times each char appears as 🟩 or 🟨 vs 🟥
        present_count = {}   # char -> number of 🟩/🟨 occurrences
        absent_chars = set()  # chars that got at least one 🟥

        n = min(len(guess), len(feedback))

        # First pass: gather counts
        for idx in range(n):
            guess_char = guess[idx].lower()
            fb = feedback[idx]
            if fb in ('🟩', '🟨'):
                present_count[guess_char] = present_count.get(guess_char, 0) + 1
            elif fb == '🟥':
                absent_chars.add(guess_char)

        # Second pass: build constraints
        for idx in range(n):
            guess_char = guess[idx].lower()
            fb = feedback[idx]

            if fb == '🟩':  # Correct position
                position_hints[idx] = guess_char
            elif fb == '🟨':  # Wrong position
                if guess_char not in known_letters:
                    known_letters[guess_char] = []
                if idx not in known_letters[guess_char]:
                    known_letters[guess_char].append(idx)
            elif fb == '🟥':  # Not in word (at this count)
                # Only fully exclude if char never appears as 🟩/🟨
                if guess_char not in present_count:
                    excluded_letters.add(guess_char)

        # Build letter-count constraints
        min_letter_count = {}  # at least this many
        max_letter_count = {}  # at most this many (when 🟥 caps it)

        for char, count in present_count.items():
            min_letter_count[char] = count
            # If the char also got a 🟥, the exact count is known
            if char in absent_chars:
                max_letter_count[char] = count

        return known_letters, excluded_letters, position_hints, min_letter_count, max_letter_count

    def filter_candidates(self, known_letters: Dict[str, list], excluded: Set[str],
                         position_hints: Dict[int, str], word_length: int = 5,
                         min_letter_count: Dict[str, int] = None,
                         max_letter_count: Dict[str, int] = None) -> List[str]:
        """
        Filter word list based on game constraints including letter-count bounds.
        """
        if min_letter_count is None:
            min_letter_count = {}
        if max_letter_count is None:
            max_letter_count = {}

        candidates = []
        words = self.all_words_by_length.get(word_length, set())

        for word in words:
            word_lower = word.lower()
            valid = True

            # Check excluded letters (fully absent)
            if any(char in word_lower for char in excluded):
                continue

            # Check position hints (correct positions)
            for pos, char in position_hints.items():
                if pos >= len(word_lower) or word_lower[pos] != char:
                    valid = False
                    break

            if not valid:
                continue

            # Check known letters (must be in word but not at known wrong positions)
            for char, wrong_positions in known_letters.items():
                if char not in word_lower:
                    valid = False
                    break
                for wrong_pos in wrong_positions:
                    if wrong_pos < len(word_lower) and word_lower[wrong_pos] == char:
                        valid = False
                        break
                if not valid:
                    break

            if not valid:
                continue

            # Check letter-count constraints (handles duplicate letters)
            word_counts = Counter(word_lower)
            for char, min_c in min_letter_count.items():
                if word_counts.get(char, 0) < min_c:
                    valid = False
                    break
            if not valid:
                continue

            for char, max_c in max_letter_count.items():
                if word_counts.get(char, 0) > max_c:
                    valid = False
                    break

            if valid:
                candidates.append(word_lower)

        return candidates

    def get_best_guess(self, candidates: List[str], position_hints: Dict[int, str],
                       word_length: int = 5) -> str:
        """
        Choose the best word from candidates using letter frequency.
        Penalizes already-confirmed letters to maximise information gain.
        Boosts common/real words since they are more likely answers.
        """
        if not candidates:
            # Return a common starting word appropriate for the target length
            starters_by_length = {
                4: ['dare', 'salt', 'coin', 'hare', 'lime'],
                5: ['audio', 'stare', 'arose', 'slate', 'adore'],
                6: ['action', 'bridge', 'castle', 'design', 'factor'],
            }
            common_starters = starters_by_length.get(word_length, starters_by_length[5])
            target_words = self.all_words_by_length.get(word_length, set())
            for word in common_starters:
                if word in target_words:
                    return word
            # Fallback: pick any word of the right length
            if target_words:
                return next(iter(target_words))
            # Last resort: pick any available word
            for words in self.all_words_by_length.values():
                if words:
                    return next(iter(words))
            return 'audio'

        if len(candidates) == 1:
            return candidates[0]

        # Score each candidate word
        scored_words = []
        confirmed_chars = set(position_hints.values())

        for word in candidates:
            unique_chars = set(word)

            # Letter frequency score — only for *unknown* letters to maximise information
            wf = len(word)
            freq_map = self.letter_frequency.get(wf, {})
            freq_score = sum(freq_map.get(ch, 0) for ch in unique_chars if ch not in confirmed_chars)

            # Penalize words that re-use already-confirmed letters in non-confirmed slots
            confirmed_penalty = sum(50 for ch in unique_chars if ch in confirmed_chars)

            # Reward letter diversity (unique letters reveal more info)
            diversity_bonus = len(unique_chars) * 10

            # Boost common/real words — they are far more likely to be the answer
            common_bonus = 200 if word in self.common_words else 0

            total_score = freq_score - confirmed_penalty + diversity_bonus + common_bonus
            scored_words.append((word, total_score))

        # Return word with highest score
        scored_words.sort(key=lambda x: x[1], reverse=True)
        return scored_words[0][0]


# Global solver instance
_solver = None


def get_solver() -> WordSolver:
    """Get or create solver instance"""
    global _solver
    if _solver is None:
        _solver = WordSolver()
    return _solver
