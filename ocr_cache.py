"""
Persistent OCR cache for Possessioner action/target menu text identification.

Strategy
--------
* OCR runs on the verb-panel or target-panel crop only (right portion of the
  game area where the menu boxes live).  This crop is small and consistent.
* Results are keyed by MD5 hash of the cropped image (greyscale).
* The cache is saved to ocr_cache.json next to this file and reloaded on
  subsequent runs, so each unique crop is only processed once.
* EasyOCR (free, local, Japanese) is used as the OCR engine and is imported
  lazily so startup is fast when every crop is already cached.

Usage from explore_menu.py
--------------------------
    from ocr_cache import label_menu_screenshot, label_target_screenshot

    # Returns list of (japanese, english) pairs, one per visible verb/target,
    # top-to-bottom in display order.
    verbs = label_menu_screenshot(img)   # PIL image, full window
    targets = label_target_screenshot(img)

    # Then index by action_index / target_index:
    ja, en = verbs[action_index]

Translation lookup
------------------
Looks up the raw OCR text in a local translation table built from
PSSR_dump.xlsx (cached in memory).  If no match is found the raw Japanese
text is returned for the English column.
"""
from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Any

from PIL import Image

# ---------------------------------------------------------------------------
# Crop regions (full-window pixel coordinates, 648×451 reference image)
# ---------------------------------------------------------------------------
# These are the bounding boxes for the menu panels as measured from the
# explore-rasu diff analysis.  Adjust if the window size ever changes.
#
# Verb panel:  right 20% of window, upper 50%
#   x: 510–640   y: 47–230
# Target panel: right 18% of window, upper 30%  (narrower than verb panel)
#   x: 518–640   y: 47–200
#
# For a 648×451 window image these are safe crops that stay within the
# game area even accounting for slight chrome-height variation.

_VERB_CROP   = (510, 35, 640, 250)   # (left, top, right, bottom) window px
_TARGET_CROP = (518, 35, 640, 210)   # 518 = leftmost x where EasyOCR detects 工場に入る

# ---------------------------------------------------------------------------
# Cache file
# ---------------------------------------------------------------------------
_CACHE_FILE = Path(__file__).parent / "ocr_cache.json"
_CACHE_VERSION = 1

_cache: dict[str, Any] | None = None   # loaded lazily


def _load_cache() -> dict[str, Any]:
    global _cache
    if _cache is not None:
        return _cache
    if _CACHE_FILE.exists():
        try:
            data = json.loads(_CACHE_FILE.read_text(encoding="utf-8"))
            if data.get("version") == _CACHE_VERSION:
                _cache = data
                return _cache
        except Exception:
            pass
    _cache = {"version": _CACHE_VERSION, "entries": {}}
    return _cache


def _save_cache() -> None:
    if _cache is None:
        return
    _CACHE_FILE.write_text(
        json.dumps(_cache, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def _crop_hash(img: Image.Image, box: tuple[int, int, int, int]) -> tuple[str, Image.Image]:
    """Return (md5_hex, crop_image) for the given box in the window image."""
    # Clamp box to image bounds
    w, h = img.size
    l, t, r, b = box
    l, t, r, b = max(0, l), max(0, t), min(w, r), min(h, b)
    crop = img.crop((l, t, r, b)).convert("L")   # greyscale for stable hash
    digest = hashlib.md5(crop.tobytes()).hexdigest()
    return digest, crop


# ---------------------------------------------------------------------------
# EasyOCR (lazy import)
# ---------------------------------------------------------------------------
_reader: Any = None   # easyocr.Reader, loaded once


def _get_reader():
    global _reader
    if _reader is None:
        try:
            import easyocr  # type: ignore
        except ImportError as exc:
            raise ImportError(
                "easyocr is not installed.  Run:  pip install easyocr"
            ) from exc
        print("Loading EasyOCR Japanese model (one-time, ~5 s)…")
        _reader = easyocr.Reader(["ja"], gpu=False, verbose=False)
    return _reader


def _run_ocr(crop_rgb: Image.Image) -> list[str]:
    """Run EasyOCR on a (small) crop and return text strings top-to-bottom.

    Uses a dual-pass strategy to handle varying menu backgrounds:
      Pass 1: original colour crop (best for light backgrounds)
      Pass 2: greyscale → invert → brightness boost (best for dark/teal backgrounds)
    Results are merged by vertical position, keeping the higher-confidence
    detection when both passes find text in the same row band.
    """
    import numpy as np
    from PIL import ImageOps, ImageEnhance

    reader = _get_reader()
    MIN_CONF = 0.05

    def _detect(img_array):
        results = reader.readtext(img_array, detail=1, paragraph=False)
        # (text, confidence, y_center)
        return [
            (r[1], float(r[2]), (r[0][0][1] + r[0][2][1]) / 2)
            for r in results if r[2] > MIN_CONF
        ]

    # Pass 1: original
    hits_normal = _detect(np.array(crop_rgb))

    # Pass 2: grey + invert + brightness (reveals dark-on-dark text)
    grey = crop_rgb.convert("L")
    inv = ImageOps.invert(grey)
    bright = ImageEnhance.Brightness(inv.convert("RGB")).enhance(1.5)
    hits_inv = _detect(np.array(bright))

    # Merge: group by y-center bands (~20px tolerance), keep best confidence
    Y_BAND = 20
    merged: list[tuple[str, float, float]] = []  # (text, conf, y)
    used = [False] * len(hits_inv)

    for text, conf, y in hits_normal:
        # Find best matching inverted hit in same y-band
        best_inv = None
        best_idx = -1
        for j, (t2, c2, y2) in enumerate(hits_inv):
            if not used[j] and abs(y - y2) < Y_BAND:
                if best_inv is None or c2 > best_inv[1]:
                    best_inv = (t2, c2, y2)
                    best_idx = j
        if best_inv and best_inv[1] > conf:
            merged.append(best_inv)
        else:
            merged.append((text, conf, y))
        if best_idx >= 0:
            used[best_idx] = True

    # Add any inverted-only detections (not matched to normal hits)
    for j, (t2, c2, y2) in enumerate(hits_inv):
        if not used[j]:
            merged.append((t2, c2, y2))

    merged.sort(key=lambda x: x[2])
    return [text for text, _conf, _y in merged]


# ---------------------------------------------------------------------------
# Translation table (from PSSR_dump.xlsx)
# ---------------------------------------------------------------------------
_trans_table: dict[str, str] | None = None   # ja → en


def _load_translations() -> dict[str, str]:
    """Load only the POS.EXE sheet, which contains adventure-game verb/target words.

    Column layout in PSSR_dump.xlsx differs by sheet type:
      POS.EXE  : Offset | Japanese | JP_len | English | EN_len | Comments
                 row[0]   row[1]    row[2]   row[3]   row[4]   row[5]
      MSD sheets: Offset | Command | CtrlCodes | Japanese | JP_len | English | ...
                  row[0]   row[1]    row[2]      row[3]    row[4]   row[5]

    We only want POS.EXE (verbs/targets).  MSD sheets contain full dialogue
    lines which cause false-positive substring matches.
    """
    global _trans_table
    if _trans_table is not None:
        return _trans_table
    _trans_table = {}
    xlsx = Path(__file__).parent / "PSSR_dump.xlsx"
    if not xlsx.exists():
        return _trans_table
    try:
        import openpyxl  # type: ignore
        wb = openpyxl.load_workbook(xlsx, read_only=True, data_only=True)
        pos_sheets = [s for s in wb.worksheets if s.title.strip().upper() == "POS.EXE"]
        if not pos_sheets:
            print("ocr_cache: WARNING — POS.EXE sheet not found in PSSR_dump.xlsx")
            wb.close()
            return _trans_table
        sheet = pos_sheets[0]
        for row in sheet.iter_rows(min_row=2, values_only=True):
            # POS.EXE columns: Offset(0) | Japanese(1) | JP_len(2) | English(3) | ...
            if not row or len(row) < 4:
                continue
            ja = row[1]
            en = row[3]
            if ja and en and isinstance(ja, str) and isinstance(en, str):
                ja_clean = ja.strip()
                en_clean = en.strip()
                if ja_clean and en_clean:
                    _trans_table[ja_clean] = en_clean
        wb.close()
        print(f"ocr_cache: loaded {len(_trans_table)} POS.EXE translations")
    except Exception as exc:
        print(f"ocr_cache: could not load PSSR_dump.xlsx ({exc})")
    return _trans_table


def _clean_ocr(text: str) -> str:
    """Normalise raw OCR output before translation lookup.

    EasyOCR sometimes appends '_' at crop boundaries and may confuse visually
    similar kanji (e.g. 者→考).  Strip artefacts and apply known corrections.
    """
    text = text.strip().rstrip("_").strip()
    # Known single-character OCR confusions for this font
    corrections = {
        "者える": "考える",
        "者え": "考え",       # truncated form
        "者": "考",           # standalone confusion
        "話む": "話す",       # す→む confusion in HQ verb panel
        "稲動": "移動",       # 移→稲 confusion (low-confidence detection)
    }
    return corrections.get(text, text)


def _translate(ja: str) -> str:
    """Return English translation for a Japanese string, or the raw OCR text if unknown.

    Uses exact match first, then limited fallbacks:
      1. Suffix match — crop clipped the leading character
         (e.g. OCR '場に入る' → table '工場に入る')
      2. Prefix match — OCR truncated the trailing character
         (e.g. OCR '調べ' → table '調べる')
    No general substring matching — that causes dialogue lines to swamp short
    verb lookups.
    """
    ja = _clean_ocr(ja)
    table = _load_translations()
    if ja in table:
        return table[ja]
    # Suffix fallback: the left crop edge may have clipped the leading character.
    # Accept a table key that is exactly 1 character longer and ends with `ja`.
    for k, v in table.items():
        if k.endswith(ja) and len(k) - len(ja) == 1:
            return v
    # Prefix fallback: EasyOCR truncated the trailing character of a short verb.
    # Accept a table key that is exactly 1 character longer and starts with `ja`.
    for k, v in table.items():
        if k.startswith(ja) and len(k) - len(ja) == 1:
            return v
    return ja   # unknown — return Japanese as-is so the user can correct the cache


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def _label_from_crop(img: Image.Image, box: tuple[int, int, int, int]) -> list[tuple[str, str]]:
    """Core function: crop → OCR (cached) → [(ja, en), …] top-to-bottom."""
    cache = _load_cache()
    digest, crop_grey = _crop_hash(img, box)

    if digest in cache["entries"]:
        entry = cache["entries"][digest]
        return [(t["ja"], t["en"]) for t in entry["texts"]]

    # Cache miss — run OCR on the colour crop (better accuracy than greyscale)
    w, h = img.size
    l, t, r, b = box
    l, t, r, b = max(0, l), max(0, t), min(w, r), min(h, b)
    crop_rgb = img.crop((l, t, r, b))

    t0 = time.monotonic()
    raw_texts = _run_ocr(crop_rgb)
    elapsed = time.monotonic() - t0
    cleaned = [_clean_ocr(t) for t in raw_texts]
    # Only log on slow (uncached) runs to avoid clutter
    if elapsed > 1.0:
        print(f"  OCR ({elapsed:.1f}s): {cleaned}")

    pairs = [(ja, _translate(ja)) for ja in cleaned]

    cache["entries"][digest] = {
        "texts": [{"ja": ja, "en": en} for ja, en in pairs],
        "crop_box": list(box),
        "added": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }
    _save_cache()

    return pairs


def label_menu_screenshot(img: Image.Image) -> list[tuple[str, str]]:
    """Return OCR labels for the verb panel in a full-window action-menu screenshot.

    Returns a list of (japanese, english) pairs in top-to-bottom display order.
    Index with action_index to get the label for a specific verb.

    Example::

        verbs = label_menu_screenshot(img)
        ja, en = verbs[action_index]   # e.g. ('見まわす', 'Look Around')
    """
    return _label_from_crop(img, _VERB_CROP)


def label_target_screenshot(img: Image.Image) -> list[tuple[str, str]]:
    """Return OCR labels for the target panel in a full-window target-submenu screenshot.

    Returns a list of (japanese, english) pairs in top-to-bottom display order.
    Index with target_index to get the label for a specific target.
    """
    return _label_from_crop(img, _TARGET_CROP)


def get_cache_stats() -> dict[str, int]:
    """Return a summary of the current cache state."""
    cache = _load_cache()
    return {
        "entries": len(cache["entries"]),
        "file": str(_CACHE_FILE),
    }
