"""
H-scene brute-force exhaustion for Possessioner walkthrough automation.

When the walkthrough runner encounters an unexpected action menu (verbs are
H-scene actions like さわる/キスする instead of the normal 移動/見る/話す/調べる/考える),
this module takes over and tries every verb × target combination until the
scene ends and the normal adventure menu returns.

Strategy
--------
Each iteration:
  1. OCR the verb menu fresh.
  2. Pick the least-tried verb, navigate to it, press SPACE.
  3. If a target submenu opened, OCR it fresh, pick the least-tried target,
     navigate to it, press SPACE.
  4. Advance through any resulting dialogue.
  5. Check if normal verbs returned → resolved.
  6. Repeat until every (verb, target) pair has been tried at least
     ``min_attempts`` times, or ``max_actions`` is reached.

Re-scanning the menu before each action means newly unlocked verbs/targets
are discovered immediately instead of waiting for the next round.
"""
from __future__ import annotations

import json
import time
from collections import Counter
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Callable

from experiment_emulator_route import (
    VK_BY_NAME,
    capture_window_image,
    post_key,
    press_and_wait,
    screenshot_window,
)
from ocr_cache import label_menu_screenshot, label_target_screenshot
from screen_state import (
    classify_screen_state,
    count_selectable_boxes,
)
from text_capture import PageInfo, TextCaptureResult, advance_capturing_text

# ---------------------------------------------------------------------------
# Known normal adventure verbs — if the menu contains ANY of these, the
# H-scene is over and we should hand control back to the walkthrough runner.
# ---------------------------------------------------------------------------
NORMAL_VERBS = {"移動", "見る", "見まわす", "話す", "調べる", "考える"}

# ---------------------------------------------------------------------------
# Timing (tuned for 200 % emulator speed)
# ---------------------------------------------------------------------------
_DOWN_DELAY = 0.15          # between DOWN presses
_POST_VERB_STABLE = 0.5     # stable_period after verb SPACE
_POST_TARGET_STABLE = 1.0   # stable_period after target SPACE
_INTER_ACTION_PAUSE = 0.2   # pause between actions
_MAX_MIN_ATTEMPTS = 5       # cap on dynamic min_attempts escalation


# ---------------------------------------------------------------------------
# Result dataclasses
# ---------------------------------------------------------------------------

@dataclass
class HSceneActionRecord:
    round: int
    verb_index: int
    verb_ja: str
    verb_en: str
    target_index: int | None       # None if verb had no submenu
    target_ja: str | None
    target_en: str | None
    page_count: int = 0
    text_pages: list[str] = field(default_factory=list)
    effect: str = "unknown"        # "dialogue", "no_effect", "battle", "crash"
    final_state: str = "unknown"


@dataclass
class HSceneBruteForceResult:
    actions: list[HSceneActionRecord] = field(default_factory=list)
    total_rounds: int = 0
    resolved: bool = False         # True if menu returned to normal verbs
    final_verb_labels: list[tuple[str, str]] = field(default_factory=list)
    crashed: bool = False


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _has_normal_verbs(verb_labels: list[tuple[str, str]]) -> bool:
    """True if any OCR'd verb label is a known normal adventure verb."""
    for ja, _en in verb_labels:
        if ja.strip() in NORMAL_VERBS:
            return True
    return False


def _navigate_to(hwnd: int, index: int) -> None:
    """Press DOWN `index` times to reach a menu item from position 0."""
    for _ in range(index):
        post_key(hwnd, VK_BY_NAME["DOWN"])
        time.sleep(_DOWN_DELAY)


def _press_escape(hwnd: int) -> None:
    """Press ESCAPE to back out of a submenu."""
    post_key(hwnd, VK_BY_NAME["ESCAPE"])
    time.sleep(0.3)


def _read_labels_with_box_count(
    hwnd: int,
    ocr_fn,
    trace_fn: Callable[[str], None] | None = None,
) -> list[tuple[str, str]]:
    """OCR a menu and use box-colour counting to detect hidden highlighted items.

    The game renders the highlighted (cursor-position-0) item as white-on-white,
    making it invisible to OCR.  Instead of a fragile two-pass OCR approach, we
    count how many of the 6 menu-box slots are selectable based on pixel colour.
    If the box count exceeds the OCR count, we know position 0 is a hidden
    highlighted item and insert a placeholder label.
    """
    def log(msg: str) -> None:
        if trace_fn:
            trace_fn(msg)

    img = capture_window_image(hwnd)
    labels = ocr_fn(img)
    box_count = count_selectable_boxes(img)

    if len(labels) == 0 and box_count > 0:
        # Boxes are coloured but OCR reads nothing — the box outlines are
        # visible over CG content but contain no text.  This is the post-action
        # text-advance state, not an interactive menu.  Return empty so the
        # caller treats it as "no verbs" and presses SPACE.
        log(f"box_count={box_count} > ocr=0 ([]) — empty boxes, not a menu")
        return []

    if box_count > len(labels):
        # Position 0 is highlighted and invisible to OCR — insert placeholder
        missing = box_count - len(labels)
        log(f"box_count={box_count} > ocr={len(labels)} "
            f"({[j for j,_ in labels]}) — inserting {missing} placeholder(s)")
        placeholders = [("???", "???")] * missing
        labels = placeholders + labels
    else:
        log(f"box_count={box_count}, ocr={len(labels)} "
            f"({[j for j,_ in labels]})")

    return labels


def _ensure_action_menu(
    hwnd: int,
    out_dir: Path,
    action_num: int,
    on_battle: str,
    trace_fn: Callable[[str], None] | None,
) -> bool:
    """Advance through dialogue/loading until we reach the action menu.

    Returns True if action_menu reached, False if stuck or crashed.
    """
    def log(msg: str) -> None:
        if trace_fn:
            trace_fn(msg)

    img = capture_window_image(hwnd)
    state = classify_screen_state(img)
    if state == "action_menu":
        return True

    # First try: normal advance with generous cycle limit for H-scenes
    cap = advance_capturing_text(
        hwnd, out_dir / f"action_{action_num:03d}_inter", "inter",
        on_battle=on_battle, trace_fn=trace_fn, cycle_limit=8,
    )
    if cap.crashed:
        return False

    state = classify_screen_state(capture_window_image(hwnd))
    if state == "action_menu":
        return True

    # If cycle was detected but we're still in dialogue, try raw SPACE
    # presses — the game may just need a few more to break through a
    # CG transition.
    if state == "dialogue":
        log("_ensure_action_menu: still dialogue after advance, pressing SPACE…")
        for retry in range(8):
            post_key(hwnd, VK_BY_NAME["SPACE"])
            time.sleep(0.6)
            img = capture_window_image(hwnd)
            state = classify_screen_state(img)
            if state == "action_menu":
                return True
            if state not in ("dialogue", "loading"):
                break

    # Last resort: try ESCAPE (may exit a stuck submenu)
    if state != "action_menu":
        _press_escape(hwnd)
        time.sleep(0.4)
        state = classify_screen_state(capture_window_image(hwnd))

    return state == "action_menu"


def _open_submenu(
    hwnd: int,
    verb_index: int,
    pre_verb_labels: list[tuple[str, str]],
    trace_fn: Callable[[str], None] | None = None,
) -> list[tuple[str, str]] | None:
    """Navigate to a verb and press SPACE.  Return target labels if a
    submenu opened, or None if the verb acted directly (dialogue/loading).

    ``pre_verb_labels`` are the verb labels OCR'd *before* pressing SPACE so
    we can detect H-scene-style submenus that replace the verb list in-place
    (verb and target crop regions overlap).
    """
    _navigate_to(hwnd, verb_index)
    press_and_wait(
        hwnd, VK_BY_NAME["SPACE"],
        change_timeout=5.0, stable_timeout=8.0,
        stable_period=_POST_VERB_STABLE,
    )
    time.sleep(_INTER_ACTION_PAUSE)

    img = capture_window_image(hwnd)
    state = classify_screen_state(img)

    if state == "action_menu":
        post_verb_labels = label_menu_screenshot(img)
        target_labels = label_target_screenshot(img)

        # Normal-style submenu: target crop shows content that differs from
        # the (post-SPACE) verb crop — two separate columns visible.
        if target_labels and target_labels != post_verb_labels:
            return target_labels

        # H-scene-style submenu: targets replaced verbs in the same area.
        # Detect by comparing post-SPACE content to pre-SPACE verb labels.
        if post_verb_labels and post_verb_labels != pre_verb_labels:
            # Use box-colour counting to detect highlighted (invisible) items
            return _read_labels_with_box_count(hwnd, label_menu_screenshot, trace_fn)

        # No change — verb had no visible effect; escape to be safe
        _press_escape(hwnd)
        time.sleep(_INTER_ACTION_PAUSE)
        return None

    # state is dialogue/loading — verb acted directly (no targets)
    return None


# ---------------------------------------------------------------------------
# Core brute-force function
# ---------------------------------------------------------------------------

def brute_force_hscene(
    hwnd: int,
    initial_labels: list[tuple[str, str]],
    out_dir: Path,
    *,
    min_attempts: int = 2,
    max_rounds: int = 120,
    max_actions: int = 200,
    on_battle: str = "skip",
    trace_fn: Callable[[str], None] | None = None,
) -> HSceneBruteForceResult:
    """Exhaust every verb × target combination in an H-scene action menu.

    Parameters
    ----------
    hwnd : int
        Emulator window handle.
    initial_labels : list of (ja, en) tuples
        Verb labels already OCR'd at detection time.
    out_dir : Path
        Directory for screenshots and report.
    min_attempts : int
        Minimum times each (verb, target) combo must be tried before we can
        declare the scene unresolved.  New options may appear after earlier
        actions, so 2 passes catches unlocked content.
    max_rounds : int
        Hard limit on total loop iterations to prevent infinite loops.
    max_actions : int
        Hard limit on total actions attempted.
    on_battle : str
        Passed through to advance_capturing_text.
    trace_fn : callable, optional
        Logging callback.

    Returns
    -------
    HSceneBruteForceResult
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    result = HSceneBruteForceResult()
    action_count = 0

    # Track how many times each (verb_ja, target_ja) pair has been executed.
    # target_ja=None for direct-action verbs (no submenu).
    attempt_counts: Counter[tuple[str, str | None]] = Counter()

    # Cache discovered targets per verb so we know when all combos are covered.
    # verb_ja → list of target_ja (None means direct-action verb).
    known_targets: dict[str, list[str | None]] = {}

    def log(msg: str) -> None:
        if trace_fn:
            trace_fn(msg)

    screenshot_window(hwnd, out_dir / "before.png")
    log(f"H-scene brute-force: {len(initial_labels)} verb(s), "
        f"min_attempts={min_attempts}")

    empty_menu_streak = 0
    _MAX_EMPTY_STREAK = 30       # bail after 30 consecutive empty-menu iterations

    for iteration in range(max_rounds):
        result.total_rounds = iteration + 1

        if action_count >= max_actions:
            log(f"hit max_actions={max_actions}")
            break

        # ---- Ensure we're at the action menu ----
        if not _ensure_action_menu(hwnd, out_dir, action_count, on_battle, trace_fn):
            result.crashed = True
            log("CRASH: could not reach action_menu")
            break

        # ---- OCR verb menu fresh each iteration ----
        # Single-pass OCR + box-colour counting detects highlighted items
        verb_labels = _read_labels_with_box_count(hwnd, label_menu_screenshot, trace_fn)
        if not verb_labels:
            empty_menu_streak += 1
            if empty_menu_streak >= _MAX_EMPTY_STREAK:
                log(f"iter {iteration}: {_MAX_EMPTY_STREAK} consecutive empty menus — bailing")
                result.crashed = True
                break
            # No readable verb text.  The most likely cause is post-action
            # dialogue text still being displayed while box outlines remain
            # visible.  Press SPACE to advance the text so the menu
            # repopulates on the next iteration.
            log(f"iter {iteration}: no verbs — pressing SPACE to advance")
            post_key(hwnd, VK_BY_NAME["SPACE"])
            time.sleep(0.6)
            continue
        empty_menu_streak = 0

        # ---- Check exit condition: normal verbs returned ----
        if _has_normal_verbs(verb_labels):
            if action_count > 0:
                log(f"normal verbs returned after {action_count} action(s) — resolved")
                result.resolved = True
                result.final_verb_labels = verb_labels
                break

        # ---- Sequential sweep: find the next untried/least-tried combo ----
        # Walk verbs in order; for each verb, walk its targets in order.
        # Pick the first (verb, target) pair with the fewest attempts.
        best_vi: int | None = None
        best_ti: int | None = None      # None = direct-action (no targets)
        best_count = min_attempts        # only pick if below this threshold

        for vi, (v_ja, _) in enumerate(verb_labels):
            targets = known_targets.get(v_ja)
            if targets is None:
                # Never opened this verb — guaranteed 0 attempts
                best_vi, best_ti, best_count = vi, None, 0
                break
            for ti_idx, t_ja in enumerate(targets):
                c = attempt_counts.get((v_ja, t_ja), 0)
                if c < best_count:
                    best_vi = vi
                    best_ti = ti_idx if t_ja is not None else None
                    best_count = c
                    if c == 0:
                        break  # can't do better than 0
            if best_count == 0:
                break

        if best_vi is None:
            # Every known (verb, target) combo has been tried ≥ min_attempts
            # times.  Before giving up, re-read the verb menu to check for
            # newly unlocked verbs.  New targets are discovered naturally
            # when the main loop opens submenus in the next round.
            fresh_verbs = _read_labels_with_box_count(hwnd, label_menu_screenshot, trace_fn)
            fresh_names = {v for v, _ in fresh_verbs} if fresh_verbs else set()
            known_names = set(known_targets.keys())
            if fresh_names - known_names:
                log(f"new verb(s) discovered: {fresh_names - known_names}")
                min_attempts += 1
                verb_labels = fresh_verbs
                continue
            # No new verbs — bump min_attempts to try more repetitions.
            # H-scenes sometimes need many interactions to progress.
            if min_attempts < _MAX_MIN_ATTEMPTS:
                min_attempts += 1
                log(f"raising min_attempts to {min_attempts} (max {_MAX_MIN_ATTEMPTS})")
                continue
            log(f"all combos tried ≥{min_attempts}× — exhausted")
            break

        vi = best_vi
        v_ja, v_en = verb_labels[vi]

        # ---- Open verb / submenu ----
        target_labels = _open_submenu(hwnd, vi, verb_labels, trace_fn)

        if target_labels is not None:
            # Update known targets for this verb
            t_ja_list = [t_ja for t_ja, _ in target_labels]
            known_targets[v_ja] = t_ja_list
            log(f"  verb[{vi}] {v_en or v_ja}: {len(target_labels)} target(s) "
                f"{[t for t, _ in target_labels]}")

            # Pick the least-tried target from the FRESH list
            target_attempts = [
                attempt_counts.get((v_ja, t_ja), 0)
                for t_ja, _ in target_labels
            ]
            ti = min(range(len(target_labels)), key=lambda i: target_attempts[i])
            t_ja, t_en = target_labels[ti]

            log(f"  [{action_count}] {v_en or v_ja}[{vi}] → {t_en or t_ja}[{ti}]"
                f"  (attempt #{attempt_counts.get((v_ja, t_ja), 0) + 1})")

            # Navigate to target and confirm
            _navigate_to(hwnd, ti)
            press_and_wait(
                hwnd, VK_BY_NAME["SPACE"],
                change_timeout=8.0, stable_timeout=12.0,
                stable_period=_POST_TARGET_STABLE,
            )

            # Advance through resulting dialogue
            _safe_v = v_ja.replace("?", "_").replace("*", "_")
            _safe_t = t_ja.replace("?", "_").replace("*", "_")
            action_dir = out_dir / f"a{action_count:03d}_{_safe_v}_{_safe_t}"
            cap = advance_capturing_text(
                hwnd, action_dir, "text",
                on_battle=on_battle, trace_fn=trace_fn, cycle_limit=8,
            )

            # On some CGs the classifier misidentifies the post-action
            # text-advance state as "action_menu" (CG content at box
            # positions fools the topslot heuristic), returning 0 pages.
            # Rather than blindly pressing SPACE (which could select a
            # menu option), we record a synthetic page so the action
            # counts as having produced text.  The main loop's "no verbs /
            # empty boxes" handler will press SPACE on the next iteration
            # to advance past the text and repopulate the menu.
            if not cap.pages and cap.final_state == "action_menu":
                diag = capture_window_image(hwnd)
                diag_path = action_dir / "diag_missed_text.png"
                diag.save(diag_path)
                log("    [missed text] 0 pages — recording synthetic page")
                cap.pages.append(PageInfo(
                    index=0, path=str(diag_path),
                    fingerprint="forced_advance",
                    state="dialogue", is_new=True,
                ))

            rec = HSceneActionRecord(
                round=iteration, verb_index=vi, verb_ja=v_ja, verb_en=v_en,
                target_index=ti, target_ja=t_ja, target_en=t_en,
                page_count=len(cap.pages),
                text_pages=[p.path for p in cap.pages],
                final_state=cap.final_state,
                effect=(
                    "crash" if cap.crashed else
                    "battle" if cap.battle_detected else
                    "dialogue" if cap.pages else
                    "no_effect"
                ),
            )
            result.actions.append(rec)
            attempt_counts[(v_ja, t_ja)] += 1
            action_count += 1
            log(f"    → {rec.effect} ({rec.page_count} pages)")

            if cap.crashed:
                result.crashed = True
                break
            if cap.battle_detected:
                break

        else:
            # Verb acted directly (no submenu) or had no effect
            known_targets.setdefault(v_ja, [None])   # mark as direct-action
            img2 = capture_window_image(hwnd)
            state2 = classify_screen_state(img2)

            if state2 in ("dialogue", "loading"):
                log(f"  [{action_count}] {v_en or v_ja}[{vi}] (direct)"
                    f"  (attempt #{attempt_counts.get((v_ja, None), 0) + 1})")

                _safe_v = v_ja.replace("?", "_").replace("*", "_")
                action_dir = out_dir / f"a{action_count:03d}_{_safe_v}_direct"
                cap = advance_capturing_text(
                    hwnd, action_dir, "text",
                    on_battle=on_battle, trace_fn=trace_fn, cycle_limit=8,
                )

                rec = HSceneActionRecord(
                    round=iteration, verb_index=vi, verb_ja=v_ja, verb_en=v_en,
                    target_index=None, target_ja=None, target_en=None,
                    page_count=len(cap.pages),
                    text_pages=[p.path for p in cap.pages],
                    final_state=cap.final_state,
                    effect=(
                        "crash" if cap.crashed else
                        "battle" if cap.battle_detected else
                        "dialogue" if cap.pages else
                        "no_effect"
                    ),
                )
                result.actions.append(rec)
                attempt_counts[(v_ja, None)] += 1
                action_count += 1
                log(f"    → {rec.effect} ({rec.page_count} pages)")

                if cap.crashed:
                    result.crashed = True
                    break
                if cap.battle_detected:
                    break

            elif state2 == "battle":
                log(f"  [{action_count}] {v_en or v_ja}[{vi}] → BATTLE")
                rec = HSceneActionRecord(
                    round=iteration, verb_index=vi, verb_ja=v_ja, verb_en=v_en,
                    target_index=None, target_ja=None, target_en=None,
                    effect="battle", final_state="battle",
                )
                result.actions.append(rec)
                attempt_counts[(v_ja, None)] += 1
                action_count += 1
                break

            else:
                # Verb had no visible effect (stayed on action_menu)
                log(f"  [{action_count}] {v_en or v_ja}[{vi}] → no effect")
                rec = HSceneActionRecord(
                    round=iteration, verb_index=vi, verb_ja=v_ja, verb_en=v_en,
                    target_index=None, target_ja=None, target_en=None,
                    effect="no_effect", final_state="action_menu",
                )
                result.actions.append(rec)
                attempt_counts[(v_ja, None)] += 1
                action_count += 1

    # Final state
    screenshot_window(hwnd, out_dir / "after.png")

    if not result.final_verb_labels:
        img = capture_window_image(hwnd)
        if classify_screen_state(img) == "action_menu":
            result.final_verb_labels = label_menu_screenshot(img)

    # Write detailed report
    report = {
        "total_rounds": result.total_rounds,
        "total_actions": len(result.actions),
        "resolved": result.resolved,
        "crashed": result.crashed,
        "attempt_counts": {
            f"{v}+{t}": n for (v, t), n in sorted(
                attempt_counts.items(), key=lambda x: (x[0][0], x[0][1] or "")
            )
        },
        "initial_menu": [{"ja": ja, "en": en} for ja, en in initial_labels],
        "final_menu": [{"ja": ja, "en": en} for ja, en in result.final_verb_labels],
        "actions": [asdict(a) for a in result.actions],
    }
    (out_dir / "hscene_report.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    log(f"brute-force done: {len(result.actions)} action(s), "
        f"{result.total_rounds} iter(s), resolved={result.resolved}")

    return result
