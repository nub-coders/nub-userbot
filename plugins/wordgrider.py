import os
import re
import json
import cv2
import numpy as np
import pytesseract
import logging
from collections import Counter
from functools import lru_cache
from pyrogram import Client, filters
from pyrogram.types import Message
from tools import HARDCODED_PREFIXES
from config import GEMINI_API_KEY
from google import genai
from PIL import Image
from utils.message import Msg

# ── Gemini Vision config ──
GEMINI_MODEL = "gemini-2.0-flash"
gemini_client = genai.Client(api_key=GEMINI_API_KEY) if GEMINI_API_KEY else None

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ── 8 search directions: (row_delta, col_delta, label) ──
DIRECTIONS = [
    (0,  1,  "→"),   # right
    (0, -1,  "←"),   # left
    (1,  0,  "↓"),   # down
    (-1, 0,  "↑"),   # up
    (1,  1,  "↘"),   # diagonal down-right
    (1, -1,  "↙"),   # diagonal down-left
    (-1, 1,  "↗"),   # diagonal up-right
    (-1,-1,  "↖"),   # diagonal up-left
]

TITLE_WORDS = {
    "WORD", "GRID", "WORDGRID", "HARD", "MODE", "HARDMODE",
    "CHALLENGE", "EASY", "MEDIUM", "PUZZLE",
}


# ═══════════════════════ DICTIONARY ═══════════════════════

@lru_cache(maxsize=1)
def load_valid_words() -> frozenset:
    """
    Load a combined set of valid English words for validation.
    Uses words.txt (all lengths) as the primary source since
    allWords.json only contains 5-letter Wordle words.
    Both sources are merged for maximum coverage.
    """
    words = set()

    # Primary: words.txt — contains 880K+ words of ALL lengths
    txt_path = os.path.join(os.getcwd(), "words.txt")
    if os.path.exists(txt_path):
        try:
            with open(txt_path, "r", encoding="utf-8") as f:
                for line in f:
                    w = line.strip()
                    if w.isalpha():
                        words.add(w.upper())
            logger.info(f"[GRID] Loaded {len(words)} words from words.txt")
        except Exception as e:
            logger.warning(f"[GRID] Error reading words.txt: {e}")

    # Secondary: allWords.json — merge in for completeness
    json_paths = ["allWords.json", "data/allWords.json"]
    for p in json_paths:
        full = os.path.join(os.getcwd(), p)
        if os.path.exists(full):
            try:
                with open(full, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, list):
                    extra = {w.upper() for w in data if w.strip()}
                elif isinstance(data, dict):
                    extra = {w.upper() for w in data.keys() if w.strip()}
                else:
                    extra = set()
                before = len(words)
                words |= extra
                logger.info(
                    f"[GRID] Merged {len(extra)} from {full} "
                    f"(+{len(words) - before} new, {len(words)} total)"
                )
                break
            except Exception:
                continue

    if not words:
        logger.warning("[GRID] No word lists found!")
    return frozenset(words)



# ═══════════════════ IMAGE → GRID ═══════════════════
# Grid boundary detection, dimension finding (Sobel edge),
# and per-cell OCR with multi-threshold confidence scoring.

def _is_title_line(text: str) -> bool:
    clean = text.strip().upper()
    if clean in TITLE_WORDS:
        return True
    parts = re.split(r"\s+", clean)
    return all(p in TITLE_WORDS for p in parts if p)


def _find_grid_boundary(img):
    """
    Find the cyan/blue rectangular border of the grid.
    Returns (x, y, w, h) of the grid bounding box.
    """
    h, w = img.shape[:2]
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)

    # Detect cyan/blue border lines
    lower_cyan = np.array([80, 30, 80])
    upper_cyan = np.array([140, 255, 255])
    cyan_mask = cv2.inRange(hsv, lower_cyan, upper_cyan)

    kernel = np.ones((5, 5), np.uint8)
    cyan_dilated = cv2.dilate(cyan_mask, kernel, iterations=3)

    contours, _ = cv2.findContours(
        cyan_dilated, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
    )

    best = None
    max_area = 0
    for cnt in contours:
        area = cv2.contourArea(cnt)
        if area > max_area and area > (h * w * 0.1):
            best = cnt
            max_area = area

    if best is not None:
        bx, by, bw, bh = cv2.boundingRect(best)
        logger.info(
            f"[GRID] Found grid boundary: ({bx},{by}) {bw}x{bh}"
        )
        return bx, by, bw, bh

    # Geometric fallback
    logger.info("[GRID] No cyan border found, using geometric fallback")
    return (int(w * 0.05), int(h * 0.12), int(w * 0.9), int(h * 0.85))


def _find_grid_dimensions(grid_gray):
    """
    Determine rows and columns using Sobel edge detection.
    Finds grid line peaks, computes median spacing to estimate
    cell size, then snaps to the closest known grid size.
    Returns (n_rows, n_cols).
    """
    grid_h, grid_w = grid_gray.shape[:2]

    # Sobel edge detection: horizontal and vertical
    sobel_h = np.abs(cv2.Sobel(grid_gray, cv2.CV_64F, 0, 1, ksize=3))
    sobel_v = np.abs(cv2.Sobel(grid_gray, cv2.CV_64F, 1, 0, ksize=3))

    h_profile = np.mean(sobel_h, axis=1)
    v_profile = np.mean(sobel_v, axis=0)

    def find_peaks(profile, min_spacing):
        threshold = np.mean(profile) + 0.8 * np.std(profile)
        above = profile > threshold
        peaks = []
        i = 0
        while i < len(profile):
            if above[i]:
                j = i
                while j < len(profile) and above[j]:
                    j += 1
                peak_center = (i + j) // 2
                if not peaks or (peak_center - peaks[-1]) >= min_spacing:
                    peaks.append(peak_center)
                i = j
            else:
                i += 1
        return peaks

    h_peaks = find_peaks(h_profile, 20)
    v_peaks = find_peaks(v_profile, 20)

    def estimate_n_from_peaks(peaks, total_size):
        if len(peaks) < 2:
            return None
        spacings = [peaks[i + 1] - peaks[i] for i in range(len(peaks) - 1)]
        median_spacing = np.median(spacings)
        n = round(total_size / median_spacing)
        return max(n, 1)

    n_rows_est = estimate_n_from_peaks(h_peaks, grid_h)
    n_cols_est = estimate_n_from_peaks(v_peaks, grid_w)

    logger.info(
        f"[GRID] Sobel: {len(h_peaks)} h-peaks, {len(v_peaks)} v-peaks "
        f"-> est {n_rows_est}x{n_cols_est}"
    )

    # Snap to closest known grid size
    if n_rows_est and n_cols_est:
        candidates = [
            (10, 10), (10, 9), (9, 10), (9, 9),
            (8, 8), (8, 7), (7, 8), (7, 7),
        ]
        best = min(
            candidates,
            key=lambda rc: abs(rc[0] - n_rows_est) + abs(rc[1] - n_cols_est),
        )
        logger.info(f"[GRID] Snapped to {best[0]}x{best[1]}")
        return best

    # Fallback: pick size with most square cells
    candidates = [(10, 10), (9, 9), (8, 8), (7, 7)]
    best = min(
        candidates,
        key=lambda rc: abs(grid_w / rc[1] / (grid_h / rc[0]) - 1.0),
    )
    logger.info(f"[GRID] Fallback dimensions: {best[0]}x{best[1]}")
    return best


def _ocr_cell(cell_gray) -> str:
    """
    OCR a single cell image with multi-threshold confidence scoring.
    Upscales to 200x200, tries thresholds (130, 150, 110), picks the
    result with highest Tesseract confidence.  OTSU fallback.
    """
    if cell_gray is None or cell_gray.size == 0:
        return "."
    if cell_gray.shape[0] < 5 or cell_gray.shape[1] < 5:
        return "."

    # Upscale to 200x200 for better OCR accuracy
    cell_big = cv2.resize(
        cell_gray, (200, 200), interpolation=cv2.INTER_CUBIC
    )

    config = "--psm 10 -c tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    results = []

    # Try multiple threshold values
    # Letters are white (~180-255) on dark bg (~30-60)
    # Grid line remnants are ~70-120
    for thresh_val in [130, 150, 110]:
        _, cell_bin = cv2.threshold(
            cell_big, thresh_val, 255, cv2.THRESH_BINARY
        )
        # Invert: black letter on white bg (Tesseract standard)
        cell_inv = cv2.bitwise_not(cell_bin)

        # Morphological cleanup
        kern = np.ones((3, 3), np.uint8)
        cell_clean = cv2.morphologyEx(cell_inv, cv2.MORPH_OPEN, kern)
        cell_clean = cv2.morphologyEx(cell_clean, cv2.MORPH_CLOSE, kern)

        # Validate letter coverage (5-40% black pixels)
        black_pct = np.sum(cell_clean == 0) / cell_clean.size
        if black_pct < 0.02 or black_pct > 0.5:
            continue

        # Add white border
        bordered = cv2.copyMakeBorder(
            cell_clean, 50, 50, 50, 50,
            cv2.BORDER_CONSTANT, value=255,
        )

        try:
            text = pytesseract.image_to_string(
                bordered, config=config
            ).strip()
            if text and text[0].isalpha():
                letter = text[0].upper()
                # Get confidence score
                data = pytesseract.image_to_data(
                    bordered, config=config,
                    output_type=pytesseract.Output.DICT,
                )
                confs = [int(c) for c in data["conf"] if int(c) > 0]
                conf = max(confs) if confs else 0
                results.append((letter, conf, thresh_val))
        except Exception:
            pass

    if results:
        # Pick the result with highest confidence
        results.sort(key=lambda x: x[1], reverse=True)
        return results[0][0]

    # Last resort: OTSU threshold
    _, cell_bin = cv2.threshold(
        cell_big, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU
    )
    white_pct = np.sum(cell_bin == 255) / cell_bin.size
    if white_pct > 0.5:
        cell_bin = cv2.bitwise_not(cell_bin)
    bordered = cv2.copyMakeBorder(
        cell_bin, 50, 50, 50, 50, cv2.BORDER_CONSTANT, value=255
    )
    try:
        text = pytesseract.image_to_string(
            bordered, config=config
        ).strip()
        if text and text[0].isalpha():
            return text[0].upper()
    except Exception:
        pass

    return "."


def _extract_grid_gemini(image_path: str) -> list:
    """
    Use Google Gemini Vision to extract the letter grid directly.
    Sends the full screenshot to Gemini and asks it to read every letter.
    Returns list of row strings, e.g. ['SHOWSUBC', 'CORFEDDO', ...].
    """
    try:
        img = Image.open(image_path)
        prompt = (
            "This is a Word Grid puzzle screenshot. "
            "There is a grid of single letters inside colored cells. "
            "Extract ALL the letters from the grid, row by row, "
            "from top-left to bottom-right. "
            "Output ONLY the letters, one row per line. "
            "No spaces, no numbering, no extra text. "
            "Example output for an 8x8 grid:\n"
            "ABCDEFGH\n"
            "IJKLMNOP\n"
            "QRSTUVWX\n"
            "..."
        )
        response = gemini_client.models.generate_content(
            model=GEMINI_MODEL,
            contents=[prompt, img],
        )
        text = response.text.strip()
        logger.info(f"[GRID] Gemini raw response:\n{text}")

        rows = []
        for line in text.split("\n"):
            clean = "".join(c.upper() for c in line if c.isalpha())
            if len(clean) >= 3:
                rows.append(clean)

        if rows:
            # Validate: all rows should be same length
            lengths = [len(r) for r in rows]
            most_common = max(set(lengths), key=lengths.count)
            rows = [r for r in rows if len(r) == most_common]
            if len(rows) >= 5:
                logger.info(
                    f"[GRID] Gemini extracted {len(rows)}x{len(rows[0])} grid"
                )
                return rows

        logger.warning(f"[GRID] Gemini returned unusable result: {len(rows)} rows")
        return []

    except Exception as e:
        logger.error(f"[GRID] Gemini extraction failed: {e}")
        return []


def _extract_grid_tesseract(image_path: str) -> list:
    """
    Fallback: Extract grid using OpenCV + Tesseract.
    Sobel edge detection for dimensions, multi-threshold cell OCR.
    """
    img = cv2.imread(image_path)
    if img is None:
        return []

    h, w = img.shape[:2]
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    logger.info(
        f"[GRID] Image {w}x{h}, mean brightness={np.mean(gray):.1f}"
    )

    # Step 1: Find grid boundary
    bx, by, bw, bh = _find_grid_boundary(img)

    # Step 2: Crop to grid interior (skip cyan border ~12px)
    inset = 12
    gx1 = bx + inset
    gy1 = by + inset
    gx2 = bx + bw - inset
    gy2 = by + bh - inset
    grid_gray = gray[gy1:gy2, gx1:gx2]
    grid_h, grid_w = grid_gray.shape[:2]
    logger.info(f"[GRID] Grid interior: {grid_w}x{grid_h}")

    if grid_h < 50 or grid_w < 50:
        logger.warning("[GRID] Grid region too small")
        return []

    # Step 3: Determine grid dimensions
    n_rows, n_cols = _find_grid_dimensions(grid_gray)
    logger.info(
        f"[GRID] Grid: {n_rows}x{n_cols} = {n_rows * n_cols} cells"
    )

    # Step 4: OCR each cell
    cell_h = grid_h / n_rows
    cell_w = grid_w / n_cols

    rows = []
    for r in range(n_rows):
        row_str = ""
        for c in range(n_cols):
            y1 = int(r * cell_h)
            y2 = int((r + 1) * cell_h)
            x1 = int(c * cell_w)
            x2 = int((c + 1) * cell_w)

            # 20% inset to avoid grid line remnants
            pw = max(int((x2 - x1) * 0.20), 3)
            ph = max(int((y2 - y1) * 0.20), 3)
            cell = grid_gray[y1 + ph : y2 - ph, x1 + pw : x2 - pw]
            row_str += _ocr_cell(cell)

        rows.append(row_str)

    logger.info(
        f"[GRID] Tesseract extracted {len(rows)} rows x "
        f"{len(rows[0]) if rows else 0} cols"
    )
    return rows


def extract_grid_from_image(image_path: str) -> list:
    """
    Extract letter grid from a Word Grid screenshot.
    Primary: Google Gemini Vision (free, highly accurate).
    Fallback: OpenCV + Tesseract (local, no API needed).
    """
    # Try Gemini first
    logger.info("[GRID] Trying Gemini Vision extraction...")
    rows = _extract_grid_gemini(image_path)
    if rows:
        return rows

    # Fall back to Tesseract
    logger.info("[GRID] Gemini failed, falling back to Tesseract...")
    return _extract_grid_tesseract(image_path)


# ═══════════════════ GRID BUILDER ═══════════════════

def build_2d_grid(grid_strings: list) -> list:
    """
    Convert row-strings into a uniform rectangular 2D array.
    Filters title rows, normalises to the most-common row width.
    """
    if not grid_strings:
        return []

    filtered = [r for r in grid_strings if not _is_title_line(r)]
    if not filtered:
        return []

    lengths = [len(r) for r in filtered]
    expected_len = Counter(lengths).most_common(1)[0][0]

    grid = []
    for row in filtered:
        if abs(len(row) - expected_len) <= 1:
            trimmed = row[:expected_len].ljust(expected_len, ".")
            grid.append(list(trimmed))

    return grid


# ═══════════════════ 3D SOLVER ═══════════════════

def search_grid_3d(grid_2d, clues, valid_words):
    rows = len(grid_2d)
    cols = len(grid_2d[0]) if rows else 0
    results = []

    for clue in clues:
        start_char = clue["starts_with"]
        length = clue["length"]
        matches = []

        for r in range(rows):
            for c in range(cols):
                if grid_2d[r][c] != start_char:
                    continue

                for dr, dc, arrow in DIRECTIONS:
                    end_r = r + dr * (length - 1)
                    end_c = c + dc * (length - 1)
                    if not (0 <= end_r < rows and 0 <= end_c < cols):
                        continue

                    path, chars = [], []
                    for step in range(length):
                        nr, nc = r + dr * step, c + dc * step
                        if grid_2d[nr][nc] == ".":
                            break
                        path.append((nr, nc))
                        chars.append(grid_2d[nr][nc])
                    else:
                        candidate = "".join(chars)
                        is_valid = (
                            candidate in valid_words if valid_words else None
                        )
                        matches.append({
                            "word": candidate,
                            "path": path,
                            "direction": arrow,
                            "valid": is_valid,
                        })

        matches.sort(key=lambda m: (not m["valid"], m["word"]))
        results.append({"clue": clue, "matches": matches})

    return results


# ═══════════════════ FORMATTER ═══════════════════

def format_3d_results(grid_2d, results_3d, title):
    rows = len(grid_2d)
    cols = len(grid_2d[0]) if rows else 0

    out = f"**{title}**\n\n"
    out += f"{Msg.EMOJI_GRID} **Grid Size:** {rows} × {cols}\n\n"

    out += f"**{Msg.EMOJI_PUZZLE} 2D Grid** `grid[row][col]`:\n```\n"
    out += "    " + "  ".join(f"{c:>2}" for c in range(cols)) + "\n"
    for r, row in enumerate(grid_2d):
        out += f"{r:>2}| " + "  ".join(f"{ch:>2}" for ch in row) + "\n"
    out += "```\n\n"

    out += f"**{Msg.EMOJI_SOLVE} 3D Solutions** `results[clue][match]`:\n\n"

    if not results_3d:
        out += "_No riddle clues found in caption._\n"
        return out

    for ci, layer in enumerate(results_3d):
        clue = layer["clue"]
        matches = layer["matches"]
        valid = [m for m in matches if m["valid"]]
        out += (
            f"**[{ci}]** `{clue['starts_with']}` — "
            f"{clue['length']} letters "
            f"({len(valid)}✅ / {len(matches)} total)\n"
        )
        if not matches:
            out += "   _No candidates found._\n"
        else:
            shown = valid[:8] if valid else matches[:5]
            for mi, m in enumerate(shown):
                v = "✅" if m["valid"] else "❔"
                coords = "→".join(f"({r},{c})" for r, c in m["path"])
                out += (
                    f"  `[{ci}][{mi}]` {v} **{m['word']}** "
                    f"{m['direction']}  {coords}\n"
                )
            remaining = len(valid) - len(shown)
            if remaining > 0:
                out += f"  _…and {remaining} more valid words_\n"
        out += "\n"

    return out


# ═══════════════════ CLUE PARSER ═══════════════════

def parse_clues(text: str) -> list:
    clues = []
    pattern = re.compile(r"([a-zA-Z])[\-\s_]*\((\d+)\)")
    for line in text.split("\n"):
        for char, length in pattern.findall(line):
            clues.append({"starts_with": char.upper(), "length": int(length)})
    return clues


# ═══════════════════════ COMMANDS ═══════════════════════

@Client.on_message(
    filters.command("solvegrid", prefixes=HARDCODED_PREFIXES) & filters.me
)
async def solve_wordgrid(client: Client, message: Message):
    """Reply to a Word Grid photo+caption to auto-solve."""
    target_msg = message.reply_to_message
    if not target_msg or not target_msg.photo:
        await message.reply(
            "Reply to an image with `.solvegrid`.\n"
            "Or use `.grid` to type the letters manually."
        )
        return

    m = await message.reply(f"{Msg.EMOJI_DOWNLOAD} Downloading photo…")
    photo_path = await target_msg.download()

    try:
        caption = target_msg.caption or target_msg.text or ""
        clues = parse_clues(caption)
        await m.edit(
            f"{Msg.EMOJI_SEARCH} **{len(clues)}** clues found. "
            f"Extracting grid (Gemini Vision → Tesseract fallback)…"
        )

        raw_rows = extract_grid_from_image(photo_path)
        if not raw_rows:
            await m.edit(
                "❌ OCR couldn't extract the grid.\n"
                "Use `.grid` to input the letters manually."
            )
            return

        grid_2d = build_2d_grid(raw_rows)
        if not grid_2d:
            await m.edit(
                "❌ Couldn't normalise grid rows.\n"
                "Use `.grid` to input the letters manually."
            )
            return

        nrows, ncols = len(grid_2d), len(grid_2d[0])
        await m.edit(
            f"{Msg.EMOJI_SUCCESS} **{nrows}×{ncols}** grid extracted. Solving…"
        )

        valid_words = load_valid_words()
        results_3d = search_grid_3d(grid_2d, clues, valid_words)

        cap_up = caption.upper()
        if "HARD MODE" in cap_up:
            title = f"{Msg.EMOJI_FIRE} Hard Mode — 3D Grid Solver"
        elif "WORD GRID" in cap_up:
            title = f"{Msg.EMOJI_FIRE} Word Grid — 3D Grid Solver"
        else:
            title = f"{Msg.EMOJI_PUZZLE} Word Grid — 3D Grid Solver"

        response = format_3d_results(grid_2d, results_3d, title)
        await m.edit(response)

    except Exception as e:
        logger.error(f"Error processing WordGrid: {e}")
        await m.edit(f"{Msg.EMOJI_ERROR} Error: {e}")
    finally:
        if os.path.exists(photo_path):
            os.remove(photo_path)


@Client.on_message(
    filters.command("grid", prefixes=HARDCODED_PREFIXES) & filters.me
)
async def manual_grid(client: Client, message: Message):
    """
    Type the grid letters manually — guaranteed accuracy.

    Usage (reply to the puzzle message that has the clues):
        .grid
        SHOWSUBC
        CORFEDDO
        SAWXELEM
        BANNDOSM
        TBCEEVUO
        FHKRERLN
        MSOREDSS
        AYYVVDLQ
    """
    text = message.text or ""
    parts = text.split(None, 1)
    grid_text = parts[1].strip() if len(parts) > 1 else ""

    if not grid_text:
        await message.reply(
            "**Usage:** reply to the puzzle message, then:\n"
            "```\n.grid\nSHOWSUBC\nCORFEDDO\nSAWXELEM\n"
            "BANNDOSM\nTBCEEVUO\nFHKRERLN\n"
            "MSOREDSS\nAYYVVDLQ```"
        )
        return

    m = await message.reply(f"{Msg.EMOJI_GEAR} Processing manual grid…")

    try:
        raw_rows = []
        for line in grid_text.split("\n"):
            clean = "".join(c.upper() for c in line if c.isalpha())
            if len(clean) >= 3:
                raw_rows.append(clean)

        if not raw_rows:
            await m.edit(f"{Msg.EMOJI_ERROR} No valid rows found.")
            return

        grid_2d = build_2d_grid(raw_rows)
        if not grid_2d:
            await m.edit(f"{Msg.EMOJI_ERROR} Could not build grid from input.")
            return

        clues = []
        target_msg = message.reply_to_message
        if target_msg:
            caption = target_msg.caption or target_msg.text or ""
            clues = parse_clues(caption)

        nrows, ncols = len(grid_2d), len(grid_2d[0])
        await m.edit(
            f"{Msg.EMOJI_SUCCESS} **{nrows}×{ncols}** grid loaded. "
            f"Searching with **{len(clues)}** clues…"
        )

        valid_words = load_valid_words()
        results_3d = search_grid_3d(grid_2d, clues, valid_words)
        title = f"{Msg.EMOJI_PUZZLE} Word Grid — 3D Grid Solver (Manual)"
        response = format_3d_results(grid_2d, results_3d, title)
        await m.edit(response)

    except Exception as e:
        logger.error(f"Error processing manual grid: {e}")
        await m.edit(f"{Msg.EMOJI_ERROR} Error: {e}")
