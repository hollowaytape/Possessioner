"""
Per-page text capture for Possessioner emulator automation.

Provides a single function used by both the critical-path walkthrough runner
and the exhaustive text scanner:

    result = advance_capturing_text(hwnd, out_dir, prefix, ...)

This presses SPACE through all resulting dialogue/cutscene pages, screenshots
every page, fingerprints each page (for loop detection), and returns a
structured result.  It does NOT implement high-level looping or action
execution — those live in the callers.

Crash detection
---------------
If the game stops responding (no pixel change for CRASH_TIMEOUT seconds after
a SPACE press) the page is marked as a crash and the loop stops.  The caller
should treat a crash result as fatal for the current action attempt.
"""
from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from PIL import Image

from experiment_emulator_route import (
    VK_BY_NAME,
    _WC_CHROME_LEFT,
    _WC_CHROME_TOP,
    capture_window_image,
    images_different,
    post_key,
    wait_for_content_change,
    wait_for_content_stable,
)
from screen_state import classify_screen_state

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

CRASH_TIMEOUT   = 8.0   # seconds to wait for ANY pixel change after SPACE
STABLE_PERIOD   = 0.35  # seconds of stability before declaring page loaded
STABLE_TIMEOUT  = 6.0   # max seconds to wait for stability


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _game_area(img: Image.Image) -> Image.Image:
    """Strip window chrome."""
    w, h = img.size
    return img.crop((_WC_CHROME_LEFT, _WC_CHROME_TOP, w - _WC_CHROME_LEFT, h - 4))


def page_fingerprint(img: Image.Image) -> str:
    """Stable MD5 of the full game area — used to detect repeated dialogue pages."""
    raw = _game_area(img).convert("L").tobytes()
    return hashlib.md5(raw).hexdigest()


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------

@dataclass
class PageInfo:
    index: int
    path: str
    fingerprint: str
    state: str          # 'dialogue' | 'action_menu' | 'battle' | 'loading' | 'unknown'
    is_new: bool = True  # False if this fingerprint was already seen in a previous attempt


@dataclass
class TextCaptureResult:
    pages: list[PageInfo] = field(default_factory=list)
    final_state: str = "unknown"
    battle_detected: bool = False
    crashed: bool = False            # True if game stopped responding
    stopped_reason: str = ""        # human-readable reason the loop stopped


# ---------------------------------------------------------------------------
# Core function
# ---------------------------------------------------------------------------

def advance_capturing_text(
    hwnd: int,
    out_dir: Path,
    prefix: str,
    *,
    max_pages: int = 80,
    on_battle: str = "wait",
    known_page_fps: set[str] | None = None,
    trace_fn: Callable[[str], None] | None = None,
    cycle_limit: int = 5,
) -> TextCaptureResult:
    """Press SPACE through all dialogue, screenshotting every page.

    Parameters
    ----------
    hwnd:
        Emulator window handle.
    out_dir:
        Directory in which to write page screenshots.
    prefix:
        Filename prefix; pages are saved as ``{prefix}_p{N:03d}.png``.
    max_pages:
        Safety limit on SPACE presses.
    on_battle:
        ``'wait'`` — beep, prompt user, then continue once battle resolves.
        ``'skip'`` — screenshot and return immediately (caller must restore state).
    known_page_fps:
        Set of fingerprints already seen in earlier attempts of the same action.
        Pages whose fingerprint is in this set are marked ``is_new=False``.
        Pass ``None`` to treat all pages as new (first attempt).
    trace_fn:
        Optional logging callback.

    Returns
    -------
    TextCaptureResult
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    result = TextCaptureResult()
    known = known_page_fps if known_page_fps is not None else set()

    def log(msg: str) -> None:
        if trace_fn:
            trace_fn(msg)

    i = 0
    _fp_repeat: dict[str, int] = {}    # fingerprint → total-repeat count
    while i < max_pages:
        img = capture_window_image(hwnd)
        state = classify_screen_state(img)
        result.final_state = state

        if state == "action_menu":
            result.stopped_reason = "reached action_menu"
            log(f"p{i:03d}: action_menu — done")
            break

        if state == "loading":
            log(f"p{i:03d}: loading — waiting")
            time.sleep(0.8)
            continue      # don't increment i

        if state == "battle":
            result.battle_detected = True
            result.stopped_reason = "battle detected"
            log(f"p{i:03d}: BATTLE detected")

            # Save screenshot of the battle state
            path = out_dir / f"{prefix}_p{i:03d}_battle.png"
            img.save(path)

            if on_battle == "wait":
                try:
                    import winsound  # type: ignore
                    winsound.Beep(900, 300)
                    winsound.Beep(700, 300)
                    winsound.Beep(900, 300)
                except Exception:
                    pass
                print()
                print("  *** BATTLE DETECTED ***")
                print("  Resolve the battle manually, then press Enter to continue.")
                input("  > ")
                # Advance any post-battle text back to action_menu
                for _ in range(60):
                    img2 = capture_window_image(hwnd)
                    s2 = classify_screen_state(img2)
                    result.final_state = s2
                    if s2 == "action_menu":
                        result.stopped_reason = "battle resolved → action_menu"
                        break
                    if s2 == "dialogue":
                        baseline = img2
                        post_key(hwnd, VK_BY_NAME["SPACE"])
                        wait_for_content_change(hwnd, baseline, timeout=3.0)
                    time.sleep(0.4)
            break

        # Dialogue / cutscene — screenshot this page
        fp = page_fingerprint(img)

        # Cycle detection: if the same fingerprint keeps reappearing, we're
        # stuck in a loop (e.g. SPACE selecting a menu option that produces
        # dialogue and returns to the same screen).
        _fp_repeat[fp] = _fp_repeat.get(fp, 0) + 1
        if _fp_repeat[fp] >= cycle_limit:
            result.stopped_reason = f"cycle detected (fp={fp[:12]} seen {_fp_repeat[fp]}×)"
            # Check actual screen state instead of assuming action_menu
            fresh = capture_window_image(hwnd)
            actual = classify_screen_state(fresh)
            result.final_state = actual
            # Dump classifier metrics to help debug misclassification
            from screen_state import _game_area, _has_advance_arrow, _count_transitions, \
                _has_dialogue_overlay, _menu_topslot_white_fraction, _is_battle
            area = _game_area(fresh)
            arrow = _has_advance_arrow(area)
            rt = _count_transitions(area)
            overlay = _has_dialogue_overlay(area)
            topslot = _menu_topslot_white_fraction(area)
            battle = _is_battle(area)
            log(f"p{i:03d}: CYCLE — {_fp_repeat[fp]}× — state={actual} "
                f"(arrow={arrow} rt={rt} overlay={overlay} topslot={topslot:.2f} battle={battle})")
            fresh.save(out_dir / f"{prefix}_cycle_debug.png")
            break

        path = out_dir / f"{prefix}_p{i:03d}.png"
        img.save(path)
        result.pages.append(PageInfo(
            index=i,
            path=str(path),
            fingerprint=fp,
            state=state,
            is_new=(fp not in known),
        ))
        log(f"p{i:03d}: {state} fp={fp[:12]}  {'(new)' if fp not in known else '(seen)'}")

        # Advance
        baseline = img
        post_key(hwnd, VK_BY_NAME["SPACE"])

        # Crash detection: if NO pixel change happens within CRASH_TIMEOUT, the game
        # has likely frozen or the action hit an unhandled code path.
        changed = wait_for_content_change(hwnd, baseline, timeout=CRASH_TIMEOUT)
        if not changed:
            result.crashed = True
            result.final_state = "crashed"
            result.stopped_reason = f"no pixel change for {CRASH_TIMEOUT}s after SPACE (p{i:03d})"
            log(f"p{i:03d}: CRASH — game stopped responding")
            # Save the frozen screenshot
            frozen_path = out_dir / f"{prefix}_p{i:03d}_crash.png"
            capture_window_image(hwnd).save(frozen_path)
            break

        wait_for_content_stable(hwnd, timeout=STABLE_TIMEOUT, stable_period=STABLE_PERIOD)
        i += 1

    else:
        result.stopped_reason = f"hit max_pages={max_pages}"
        result.final_state = classify_screen_state(capture_window_image(hwnd))

    return result
