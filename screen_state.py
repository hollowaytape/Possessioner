"""
Screen state classifier for Possessioner emulator automation.

Uses pixel analysis with Pillow to classify a captured screenshot into one of
the game states.  No API key required.

The classifier handles two sources:
  - Full-window captures from capture_window_image() — includes window chrome
    (title bar + optional menu bar).  Chrome is detected and stripped
    automatically before analysis.
  - Raw 640×480 game screenshots (no chrome) — used for CLI smoke-testing.

Usage as a module:
    from screen_state import classify_screen_state
    state = classify_screen_state(pil_image)   # returns e.g. 'action_menu'

Usage as a CLI smoke-test:
    python screen_state.py screens/hq-move-patch-action2/01-after-file-load.png
    # should print: action_menu

    python screen_state.py --debug screens/hq-move-patch-action2/01-after-file-load.png
    # prints raw pixel metrics for threshold tuning
"""
from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image

# ---------------------------------------------------------------------------
# Chrome detection and cropping
# ---------------------------------------------------------------------------
# Both np2debug (title bar + menu bar ≈ 55 px) and np2kai (title bar ≈ 30 px)
# have a window chrome at the top.  A title bar is a nearly-uniform horizontal
# band; we detect it by low pixel variance in the top 28 px.

_CHROME_PROBE_HEIGHT = 28     # px of top strip to inspect for chrome
_CHROME_VARIANCE_MAX = 600    # below this → uniform band → title bar present
_CHROME_TOP_CROP = 60         # px to remove when chrome is detected


def _has_window_chrome(image: Image.Image) -> bool:
    """Return True if the top of the image looks like a window title bar."""
    if image.height < _CHROME_PROBE_HEIGHT + 10:
        return False
    strip = image.crop((0, 0, image.width, _CHROME_PROBE_HEIGHT)).convert("L")
    pixels = list(strip.getdata())
    if not pixels:
        return False
    mean = sum(pixels) / len(pixels)
    variance = sum((p - mean) ** 2 for p in pixels) / len(pixels)
    return variance < _CHROME_VARIANCE_MAX


def _game_area(image: Image.Image) -> Image.Image:
    """Return the game content region, stripping window chrome if present.

    For captures with chrome (np2debug / np2kai), removes the title bar and
    optional menu bar.  For raw 640×480 screenshots the image is returned as-is.
    """
    if not _has_window_chrome(image):
        return image
    w, h = image.size
    top = min(_CHROME_TOP_CROP, h // 5)
    side = min(4, w // 40)
    if top >= h or side * 2 >= w:
        return image
    return image.crop((side, top, w - side, h))


# ---------------------------------------------------------------------------
# Loading detector
# ---------------------------------------------------------------------------
# Loading / blank / title-card screens are predominantly black.
# Pure-black loading (Queen Soft splash, POSSESSIONER title, blank transitions)
# typically exceeds 85 % dark pixels.  Dark cutscene backgrounds are usually
# 60–78 % dark and should NOT be classified as loading (we want to press SPACE
# through them).
#
# IMPORTANT: post-battle reward screens ("[ ITEM ] を手に入れた / DEFに+5") are
# also mostly black but contain white text that the player must press SPACE to
# dismiss.  These are NOT loading screens.  We distinguish them by checking for
# white pixels in the central area — true loading/blank transitions have none.

_LOADING_DARK_FRACTION = 0.82   # fraction of pixels where R, G, B all ≤ 40
_LOADING_TEXT_THRESHOLD = 0.003  # white-pixel fraction above which dark ≠ loading


def _dark_fraction(area: Image.Image) -> float:
    """Fraction of pixels where all three channels are ≤ 40."""
    total = area.width * area.height
    if total == 0:
        return 0.0
    rgb = area.convert("RGB")
    dark = sum(1 for r, g, b in rgb.getdata() if r <= 40 and g <= 40 and b <= 40)
    return dark / total


def _bright_text_fraction(area: Image.Image) -> float:
    """Fraction of bright pixels in the central region of a dark screen.

    Checks the middle 80 % x 75 % of the game area (avoids edges/borders).
    Counts any pixel where at least one channel is bright (≥ 180), catching
    white, cyan, yellow, and other colored text.  Post-battle text like
    '[ 力の護符 ] を手に入れた' typically produces 1-2 %; true blank loading
    screens produce < 0.1 %.
    """
    w, h = area.size
    mid = area.crop((int(w * 0.1), int(h * 0.15), int(w * 0.9), int(h * 0.90)))
    total = mid.width * mid.height
    if total == 0:
        return 0.0
    rgb = mid.convert("RGB")
    bright = sum(1 for r, g, b in rgb.getdata() if max(r, g, b) >= 180)
    return bright / total


def _is_loading(area: Image.Image) -> bool:
    """True only for genuinely blank dark screens (no visible text)."""
    if _dark_fraction(area) < _LOADING_DARK_FRACTION:
        return False
    # Dark screen with visible text = post-battle reward / info text, not loading.
    if _bright_text_fraction(area) >= _LOADING_TEXT_THRESHOLD:
        return False
    return True


# ---------------------------------------------------------------------------
# Action-menu detector
# ---------------------------------------------------------------------------
# The action verb column (and the H-scene target column) consists of stacked
# labelled boxes on the RIGHT side of the game area, starting from the top:
#
#   Normal scene   : Move / Look / Talk / Search / Think  →  5 boxes, 4+ transitions
#   H-scene        : Touch / Kiss / [greyed options]      →  6 boxes, 5+ transitions
#   Battle (top-R) : single character portrait box        →  1 box,   1–2 transitions
#   Dialogue       : scene image / portrait               →  0–2 transitions
#
# Analysis strip: rightmost 22 % of width, top 45 % of height.
# — Captures all verb boxes (they start at the very top of the game area).
# — Excludes the lower half where a character portrait or text box may appear.
# — Stays clear of the SYSTEM box and the lower portrait in normal scenes.

_STRIP_X_START = 0.78   # strip begins at this fraction of game-area width
_STRIP_Y_START = 0.02   # strip starts near the very top of the game area
_STRIP_Y_END   = 0.45   # strip ends before the lower portrait / text box

_DARK_THRESH   = 80     # row average below this → dark zone
_BRIGHT_THRESH = 140    # row average above this → bright zone (box interior / border)

_MIN_TRANSITIONS = 4    # standard full action/target menus
_PARTIAL_MENU_TRANSITIONS = 2  # some scenes expose only 2 visible verb rows initially
_SINGLE_MENU_CYAN_FRACTION = 0.50  # 1-action menus still keep a mostly teal right column
_DIALOGUE_TEXT_WHITE_FRACTION = 0.015  # spoken dialogue paints white glyphs in the left text box
_MENU_TOPSLOT_WHITE_FRACTION = 0.50  # actionable menus show bright white option interiors in the top slots


def _count_transitions(area: Image.Image) -> int:
    """Count dark→bright row-brightness transitions in the right-side strip.

    Uses 3-sample smoothing and hysteresis to suppress noise.
    """
    w, h = area.size
    x0 = int(w * _STRIP_X_START)
    y0 = int(h * _STRIP_Y_START)
    y1 = int(h * _STRIP_Y_END)
    if x0 >= w or y0 >= y1 or (w - x0) < 2:
        return 0

    strip = area.crop((x0, y0, w, y1)).convert("L")
    sw, sh = strip.size
    if sw == 0 or sh == 0:
        return 0

    px = strip.load()

    # Row-average brightness
    raw: list[float] = [
        sum(px[x, y] for x in range(sw)) / sw
        for y in range(sh)
    ]

    # 3-sample moving average to suppress single-pixel noise
    smoothed = list(raw)
    for i in range(1, len(raw) - 1):
        smoothed[i] = (raw[i - 1] + raw[i] + raw[i + 1]) / 3.0

    # Count dark→bright crossings with hysteresis
    transitions = 0
    in_bright = smoothed[0] > _BRIGHT_THRESH if smoothed else False
    for v in smoothed[1:]:
        if not in_bright and v > _BRIGHT_THRESH:
            transitions += 1
            in_bright = True
        elif in_bright and v < _DARK_THRESH:
            in_bright = False

    return transitions


def _right_strip(area: Image.Image) -> Image.Image | None:
    w, h = area.size
    x0 = int(w * _STRIP_X_START)
    y0 = int(h * _STRIP_Y_START)
    y1 = int(h * _STRIP_Y_END)
    if x0 >= w or y0 >= y1 or (w - x0) < 2:
        return None
    strip = area.crop((x0, y0, w, y1))
    if strip.width == 0 or strip.height == 0:
        return None
    return strip


def _right_strip_cyan_fraction(area: Image.Image) -> float:
    strip = _right_strip(area)
    if strip is None:
        return 0.0
    rgb = strip.convert("RGB")
    total = rgb.width * rgb.height
    if total == 0:
        return 0.0
    cyan = sum(1 for r, g, b in rgb.getdata() if g >= 100 and b >= 100 and r < 120)
    return cyan / total


def _dialogue_text_bright_fraction(area: Image.Image) -> float:
    """Fraction of bright pixels in the bottom text-box region.

    Counts any pixel with at least one bright channel (≥ 180), catching
    white, cyan, and other colored dialogue text.
    """
    w, h = area.size
    box = area.crop((int(w * 0.04), int(h * 0.78), int(w * 0.62), int(h * 0.90))).convert("RGB")
    total = box.width * box.height
    if total == 0:
        return 0.0
    bright = sum(1 for r, g, b in box.getdata() if max(r, g, b) >= 180)
    return bright / total


def _has_dialogue_overlay(area: Image.Image) -> bool:
    return _dialogue_text_bright_fraction(area) >= _DIALOGUE_TEXT_WHITE_FRACTION


def _menu_topslot_white_fraction(area: Image.Image) -> float:
    strip = _right_strip(area)
    if strip is None:
        return 0.0
    sw, sh = strip.size
    zone = strip.crop((int(sw * 0.18), int(sh * 0.04), int(sw * 0.52), int(sh * 0.42))).convert("RGB")
    total = zone.width * zone.height
    if total == 0:
        return 0.0
    white = sum(1 for r, g, b in zone.getdata() if min(r, g, b) >= 180)
    return white / total


def _is_action_menu(area: Image.Image) -> bool:
    right_transitions = _count_transitions(area)
    topslot_white = _menu_topslot_white_fraction(area)
    if topslot_white < _MENU_TOPSLOT_WHITE_FRACTION:
        return False
    if right_transitions >= _MIN_TRANSITIONS:
        return True
    if right_transitions >= _PARTIAL_MENU_TRANSITIONS:
        # Scenes with character portraits (HQ intro) produce left_transitions >= 3
        # alongside the action verb column (right_transitions 2-3).  High topslot_white
        # confirms verb-box interiors are present in the top-right — this is an action
        # menu regardless of what's on the left side.  Battles have character portraits
        # in the top-right instead (topslot_white ~0.11), so this check is safe.
        return True
    left_transitions = _count_left_transitions(area)
    if right_transitions != 1:
        return False
    if left_transitions >= _BATTLE_LEFT_TRANSITIONS:
        return False
    # topslot_white already passed the >= 0.50 gate above, confirming bright
    # menu-box interiors in the top-right.  This catches both single-action
    # cyan-column menus and H-scene menus (which lack the cyan column but
    # have the same bright box structure).
    return True


# ---------------------------------------------------------------------------
# Battle detector (heuristic)
# ---------------------------------------------------------------------------
# The battle screen places character portrait boxes in all four corners.
# The right strip (used for action-menu detection) shows only ONE portrait box
# in the top half → 1–2 transitions, so _is_action_menu() already returns False.
#
# Additional battle signal: the left 22 % of the image also has bordered portrait
# boxes (two, stacked), creating a similar transition pattern on the left side.
# Scene backgrounds in dialogue / action-menu states are continuous images that
# produce fewer regular transitions on the left edge.
#
# This heuristic may occasionally mis-classify a high-contrast scene as battle.
# The threshold can be tuned with --debug output from the CLI.
#
# TODO: improve using a more specific FIGHT-button pixel check once exact
# window-relative coordinates have been measured empirically.

_BATTLE_LEFT_TRANSITIONS = 3   # left-strip transitions ≥ this → probably battle


def _count_left_transitions(area: Image.Image) -> int:
    """Count dark→bright row transitions in the leftmost 22 % of the game area."""
    w, h = area.size
    x1 = int(w * 0.22)
    y0 = int(h * _STRIP_Y_START)
    if x1 == 0 or y0 >= h or h == 0:
        return 0

    strip = area.crop((0, y0, x1, h)).convert("L")
    sw, sh = strip.size
    if sw == 0 or sh == 0:
        return 0

    px = strip.load()
    raw: list[float] = [
        sum(px[x, y] for x in range(sw)) / sw
        for y in range(sh)
    ]
    smoothed = list(raw)
    for i in range(1, len(raw) - 1):
        smoothed[i] = (raw[i - 1] + raw[i] + raw[i + 1]) / 3.0

    transitions = 0
    in_bright = smoothed[0] > _BRIGHT_THRESH if smoothed else False
    for v in smoothed[1:]:
        if not in_bright and v > _BRIGHT_THRESH:
            transitions += 1
            in_bright = True
        elif in_bright and v < _DARK_THRESH:
            in_bright = False
    return transitions


def _is_battle(area: Image.Image) -> bool:
    """Heuristic battle detector: portrait boxes on BOTH left and right sides.

    Real battles have character portraits in the top-right (topslot_white ~0.11).
    Action menus have bright white verb-box interiors there (topslot_white ~0.60+).
    This distinction prevents false positives from scenes with character portraits
    alongside the action verb column (e.g. HQ intro).
    """
    right_transitions = _count_transitions(area)
    if right_transitions >= _MIN_TRANSITIONS:
        return False   # right side has verb column → action_menu, not battle
    # Bright verb-box interiors in top-right → action menu, not battle
    if _menu_topslot_white_fraction(area) >= _MENU_TOPSLOT_WHITE_FRACTION:
        return False
    # Dialogue text overlay at the bottom → H-scene or cutscene, not battle.
    # H-scene CGs can have enough left-side contrast to trigger left-transition
    # thresholds; the text overlay distinguishes them from real battles.
    if _has_dialogue_overlay(area):
        return False
    left_transitions = _count_left_transitions(area)
    return left_transitions >= _BATTLE_LEFT_TRANSITIONS


# ---------------------------------------------------------------------------
# Selectable-box counter
# ---------------------------------------------------------------------------
# The game always renders 6 menu-box slots in a vertical strip on the right
# side of the screen.  Each slot is either:
#   - HIGHLIGHTED (white/bright, selected cursor position)
#   - SELECTABLE  (red in H-scenes, grey in adventure scenes)
#   - INACTIVE    (brown in H-scenes, dark/teal in adventure scenes)
#
# Box centres are at fixed proportional Y positions with 32 px spacing
# (at ~450 px window height).  We sample a ±2 px band at each centre
# across the x range [80 %, 97 %] of the image width.
#
# Colour classification:
#   min(R,G,B) > 200            → highlighted (white) → selectable
#   R > 140 and G < 90          → red box (H-scene)   → selectable
#   spread < 20 and min > 140   → grey box (adventure) → selectable
#   everything else             → inactive / empty

import numpy as _np

_BOX_Y_FRACS = (0.159, 0.230, 0.301, 0.372, 0.443, 0.514)
_BOX_X_START_FRAC = 0.80
_BOX_X_END_FRAC = 0.97
_BOX_Y_HALFBAND = 2  # pixels above and below centre to average


def count_selectable_boxes(image: Image.Image) -> int:
    """Count how many of the 6 menu-box slots are selectable.

    Works on raw emulator captures (with or without window chrome) and
    on game-area crops.  Returns 0–6.
    """
    arr = _np.asarray(image.convert("RGB"))
    h, w = arr.shape[:2]
    x0 = int(w * _BOX_X_START_FRAC)
    x1 = int(w * _BOX_X_END_FRAC)
    selectable = 0
    for frac in _BOX_Y_FRACS:
        cy = int(h * frac)
        y0 = max(0, cy - _BOX_Y_HALFBAND)
        y1 = min(h, cy + _BOX_Y_HALFBAND + 1)
        band = arr[y0:y1, x0:x1]
        r = float(band[:, :, 0].mean())
        g = float(band[:, :, 1].mean())
        b = float(band[:, :, 2].mean())
        mn = min(r, g, b)
        mx = max(r, g, b)
        if mn > 200:                          # highlighted (white)
            selectable += 1
        elif r > 140 and g < 90:              # H-scene red
            selectable += 1
        elif (mx - mn) < 20 and mn > 140:     # adventure grey
            selectable += 1
    return selectable


# ---------------------------------------------------------------------------
# Public classifier
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Dialogue-advance arrow detector
# ---------------------------------------------------------------------------
# When the game is waiting for the player to press SPACE to advance text it
# displays a small red blinking down-arrow at the bottom of the text box.
# This is the ONLY reliable indicator that a SPACE press is required.
#
# Pixel signature: R > 150, G < 100, B < 100 in the bottom 30 % of game area.
# Reference counts (648×451 full-window captures):
#   intro.png (waiting) : 726 red pixels
#   yumi.png  (waiting) : 5403 red pixels
#   action menus        : 0–10 red pixels  (no arrow shown)
#
# Threshold of 50 pixels is conservative and avoids false positives from
# incidental red pixels in scene backgrounds.

_ARROW_MIN_R = 150
_ARROW_MAX_G = 100
_ARROW_MAX_B = 100
_ARROW_MIN_PIXELS = 50
_ARROW_Y_FRAC = 0.70   # inspect bottom 30 % of game area


def _has_advance_arrow(area: Image.Image) -> bool:
    """True if the red 'press SPACE to continue' arrow is visible."""
    w, h = area.size
    y0 = int(h * _ARROW_Y_FRAC)
    crop = area.crop((0, y0, w, h)).convert("RGB")
    count = sum(
        1 for r, g, b in crop.getdata()
        if r > _ARROW_MIN_R and g < _ARROW_MAX_G and b < _ARROW_MAX_B
    )
    return count >= _ARROW_MIN_PIXELS


# ---------------------------------------------------------------------------
# Public classifier
# ---------------------------------------------------------------------------

def classify_screen_state(image: Image.Image) -> str:
    """Classify a PIL screenshot into a game state string.

    Returns one of: 'action_menu', 'loading', 'battle', 'dialogue'.

    advance_to_menu() uses this to decide what to do:
      - 'action_menu' → stop advancing (interactive menu is ready)
      - 'loading'     → wait without pressing SPACE
      - 'battle'      → perform mouse-click battle resolution sequence
      - 'dialogue'    → press SPACE to advance text (only when red arrow visible)

    NOTE: 'dialogue' is returned ONLY when the red advance-arrow is confirmed OR
    the dialogue text overlay is detected.  Actions like "Think" that trigger a
    brief response and immediately restore the action menu are classified as
    'action_menu' because the verb-column structure is still present.
    """
    area = _game_area(image)
    # Red advance-arrow is the definitive "press SPACE to continue" signal.
    # However, H-scene menus display a persistent text box with the arrow
    # alongside the interactive action menu.  Pressing SPACE on those would
    # select a menu option, not dismiss text.
    #
    # We distinguish by checking whether the menu boxes actually contain
    # selectable content (count_selectable_boxes > 0).  When the game is
    # showing action-response text, the box outlines remain visible (producing
    # right-strip transitions) but the box interiors are empty — so the
    # selectable-box count drops to 0.
    if _has_advance_arrow(area):
        rt = _count_transitions(area)
        if rt >= _MIN_TRANSITIONS:
            # Full adventure verb column (≥4 transitions) + arrow = dismissable
            # dialogue overlay on the action menu.  SPACE clears text.
            return "dialogue"
        if rt >= 1:
            # Right-side structure exists.  Check whether the boxes actually
            # contain text or are just empty outlines over CG content.
            # count_selectable_boxes is unreliable here because CG pixels at
            # box positions can mimic selectable colors.  The topslot white
            # fraction (bright pixels in the top-right box zone) is a more
            # targeted signal: filled boxes have ts ≥ 0.47, empty boxes ~0.
            # Use a conservative threshold of 0.30.
            ts = _menu_topslot_white_fraction(area)
            if ts >= 0.30:
                return "action_menu"
            return "dialogue"
        # No right-side transitions at all → pure dialogue/cutscene.
        return "dialogue"
    if _is_loading(area):
        return "loading"
    if _is_battle(area):
        return "battle"
    # Check action_menu BEFORE dialogue so that screens where Think/etc. briefly
    # adds a text line at the bottom but keeps the verb column are not mis-classified
    # as dialogue.
    if _is_action_menu(area):
        # The game often shows Look/Talk response text at the bottom while
        # the verb column stays visible.  The player must press SPACE to
        # dismiss this text before the action counts as complete.  If the
        # dialogue overlay is detected alongside the action menu, classify
        # as "dialogue" so the text capture loop presses SPACE.
        # The red advance arrow blinks, so _has_advance_arrow may miss it;
        # the text-overlay check is a reliable fallback.
        #
        # However, H-scene menus have a PERMANENT text box that is not
        # dismissable.  Use count_selectable_boxes to distinguish: if the
        # boxes have selectable content the menu is interactive; if they
        # are empty the text just needs advancing.
        if _has_dialogue_overlay(area):
            rt = _count_transitions(area)
            if rt >= _MIN_TRANSITIONS:
                return "dialogue"
            # H-scene: check whether boxes are filled or empty
            ts = _menu_topslot_white_fraction(area)
            if ts >= 0.30:
                return "action_menu"
            return "dialogue"
        return "action_menu"
    # Dialogue overlay catches cutscenes where arrow may be mid-blink.
    if _has_dialogue_overlay(area):
        return "dialogue"
    return "dialogue"


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _debug_report(path: Path, image: Image.Image) -> None:
    area = _game_area(image)
    has_chrome = _has_window_chrome(image)
    df = _dark_fraction(area)
    wtf = _bright_text_fraction(area)
    rt = _count_transitions(area)
    lt = _count_left_transitions(area)
    cf = _right_strip_cyan_fraction(area)
    tf = _dialogue_text_bright_fraction(area)
    wf = _menu_topslot_white_fraction(area)
    arrow = _has_advance_arrow(area)
    boxes = count_selectable_boxes(image)
    state = classify_screen_state(image)
    print(
        f"{path.name}: {state}"
        f"  chrome={has_chrome}"
        f"  dark={df:.2f} (thr {_LOADING_DARK_FRACTION:.2f})"
        f"  dark_text={wtf:.4f} (thr {_LOADING_TEXT_THRESHOLD})"
        f"  right_transitions={rt} (thr {_MIN_TRANSITIONS})"
        f"  left_transitions={lt} (thr {_BATTLE_LEFT_TRANSITIONS})"
        f"  right_cyan={cf:.2f} (single-menu thr {_SINGLE_MENU_CYAN_FRACTION:.2f})"
        f"  text_white={tf:.2f} (dialogue thr {_DIALOGUE_TEXT_WHITE_FRACTION:.2f})"
        f"  topslot_white={wf:.2f} (action thr {_MENU_TOPSLOT_WHITE_FRACTION:.2f})"
        f"  advance_arrow={arrow} (thr {_ARROW_MIN_PIXELS}px)"
        f"  selectable_boxes={boxes}"
    )


if __name__ == "__main__":
    args = sys.argv[1:]
    debug = "--debug" in args
    paths = [a for a in args if not a.startswith("--")]

    if not paths:
        print("Usage: python screen_state.py [--debug] <image_path> [<image_path> ...]")
        sys.exit(1)

    for arg in paths:
        path = Path(arg)
        img = Image.open(path)
        if debug:
            _debug_report(path, img)
        else:
            print(f"{path.name}: {classify_screen_state(img)}")
