"""
Drive the Possessioner emulator through a scripted walkthrough.

Reads walkthrough_route.json (or a file supplied via --route) and executes each
step with adaptive text advancement powered by the screen_state classifier.
Every dialogue/cutscene page is screenshotted individually so you can inspect
all text that appears.  A structured report.json is written at the end.

Uses experiment_emulator_route (Windows np2debug) for emulator control.

Usage
-----
# Run save-state slot 0, output screenshots to out/slot0/
python run_walkthrough.py --slot 0 --out out/slot0

# Run all slots defined in the route file
python run_walkthrough.py --all --out out/run

# Use a different route file
python run_walkthrough.py --slot 1 --route my_route.json --out out/test

# Keep the emulator window open after the run
python run_walkthrough.py --slot 0 --out out/slot0 --no-close

Artifacts produced per slot
----------------------------
  out/{slot}/
    00-after-load-state.png
    01-after-file-load.png
    02-after-opening-advance.png
    {step:03d}-{note}/           -- one sub-dir per step
      text_p000.png ...          -- every dialogue page (screenshotted before SPACE)
    report.json                  -- structured log of all steps, page counts, crashes
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import time
from pathlib import Path

import win32con
import win32gui
from PIL import Image

from experiment_emulator_route import (
    DEFAULT_EMULATOR_PATH,
    DEFAULT_HDI_PATH,
    VK_BY_NAME,
    _WC_CHROME_LEFT,
    _WC_CHROME_TOP,
    capture_window_image,
    close_existing_emulator_windows,
    find_main_window,
    load_file_from_main_menu,
    load_state_direct,
    post_key,
    save_state_direct,
    set_emulator_speed,
    press_and_wait,
    screenshot_window,
    wait_for_content_stable,
)
from screen_state import classify_screen_state
from text_capture import TextCaptureResult, advance_capturing_text

DEFAULT_ROUTE_PATH = Path("walkthrough_route.json")


# ---------------------------------------------------------------------------
# Route loading
# ---------------------------------------------------------------------------

def load_route(route_path: Path) -> dict:
    with route_path.open(encoding="utf-8") as fh:
        return json.load(fh)


def log_current_state(hwnd: int, prefix: str) -> str:
    state = classify_screen_state(capture_window_image(hwnd))
    print(f"{prefix} state={state!r}")
    return state


# ---------------------------------------------------------------------------
# Menu fingerprinting
# ---------------------------------------------------------------------------
# Captures the right-side action-menu strip and hashes it so we can detect
# when options change (new verbs / targets appearing due to flag changes).
# We can't read Japanese text without OCR, but we CAN detect that something
# changed and flag it for human review.

def _menu_fingerprint(hwnd: int) -> str:
    """Return a short hex hash of the action-menu verb column."""
    img = capture_window_image(hwnd)
    w, h = img.size
    # Strip chrome and grab just the right verb column (same region as screen_state)
    left = _WC_CHROME_LEFT
    top  = _WC_CHROME_TOP
    game = img.crop((left, top, w - left, h - 4))
    gw, gh = game.size
    strip = game.crop((int(gw * 0.78), int(gh * 0.02), gw, int(gh * 0.45)))
    raw = strip.convert("L").tobytes()
    return hashlib.md5(raw).hexdigest()[:12]


# ---------------------------------------------------------------------------
# OCR-verified menu navigation
# ---------------------------------------------------------------------------

# Normal adventure verbs — if the menu contains NONE of these, we've entered
# an unexpected scene (H-scene, mini-game, etc.) that needs brute-forcing.
NORMAL_VERBS = {"移動", "見る", "見まわす", "話す", "調べる", "考える"}


class UnexpectedMenuError(Exception):
    """Raised when the action menu has no normal adventure verbs (likely H-scene)."""

    def __init__(self, expected_verb: str, found_labels: list[tuple[str, str]]):
        self.expected_verb = expected_verb
        self.found_labels = found_labels
        readable = [ja for ja, _en in found_labels]
        super().__init__(
            f"Expected verb '{expected_verb}' but menu contains {readable}"
        )


class MenuMismatchError(Exception):
    """Raised when the menu is readable but the expected verb/target is absent.

    This prevents the runner from blindly pressing buttons with stale indices
    when the game is in a different state than the route expects (e.g. Move
    hasn't unlocked yet, or a prior step failed silently).
    """

    def __init__(self, kind: str, expected: str, found: list[str]):
        self.kind = kind          # "verb" or "target"
        self.expected = expected
        self.found = found
        super().__init__(
            f"{kind} '{expected}' not in menu {found}"
        )


def _find_label(labels: list[tuple[str, str]], query: str) -> int | None:
    """Return the display-order index of a label in an OCR result list.

    Matching strategy (first match wins):
      1. Exact Japanese match
      2. Case-insensitive English match
      3. Fuzzy Japanese: query starts with OCR text (OCR truncated the verb,
         e.g. OCR "話" matches query "話す", OCR "調べ" matches "調べる")
      4. Fuzzy Japanese: OCR text starts with query (OCR appended noise)
      5. Containment: OCR text is a substring of query or vice versa
         (handles mid-string character drops, e.g. OCR "ユ=中山" vs "ユミ=中山")
      6. Character overlap: ≥60% of query characters appear in OCR text
         (handles scattered single-char OCR errors)

    EasyOCR frequently truncates or garbles characters in the small menu crop,
    so the fuzzy passes are essential.
    """
    q = query.strip()
    q_lower = q.lower()
    # Pass 1: exact match
    for i, (ja, en) in enumerate(labels):
        if ja.strip() == q:
            return i
        if en and en.strip().lower() == q_lower:
            return i
    # Pass 2: fuzzy — query starts with OCR text (OCR truncated)
    # Only accept if OCR text is at least half the query length to avoid
    # single-character false positives on very short OCR results.
    for i, (ja, en) in enumerate(labels):
        ja_s = ja.strip()
        if ja_s and q.startswith(ja_s) and len(ja_s) >= max(1, len(q) // 2):
            return i
    # Pass 3: fuzzy — OCR text starts with query (OCR appended noise)
    for i, (ja, en) in enumerate(labels):
        ja_s = ja.strip()
        if ja_s and ja_s.startswith(q) and len(q) >= max(1, len(ja_s) // 2):
            return i
    # Pass 4: containment — OCR dropped characters from the middle
    # e.g. "ユ=中山" (OCR) is contained in "ユミ=中山" (query)
    for i, (ja, en) in enumerate(labels):
        ja_s = ja.strip()
        if len(ja_s) >= 2 and (ja_s in q or q in ja_s):
            return i
    # Pass 5: character overlap — at least 60% of query chars appear in OCR
    # Handles scattered single-character OCR errors
    if len(q) >= 3:
        best_idx = None
        best_ratio = 0.0
        for i, (ja, en) in enumerate(labels):
            ja_s = ja.strip()
            if not ja_s:
                continue
            common = sum(1 for c in q if c in ja_s)
            ratio = common / len(q)
            if ratio > best_ratio:
                best_ratio = ratio
                best_idx = i
        if best_ratio >= 0.6 and best_idx is not None:
            return best_idx
    return None


def _verb_target_from_note(note: str) -> tuple[str | None, str | None]:
    """Extract (verb, target) search hints from a step note.

    Notes are formatted ``"VERB-TARGET extra..."`` where the trailing part may
    include ``(from-X)`` movement annotations or ``[BATTLE]``/``[VERIFY ...]``
    flags.  We strip those before splitting on the first hyphen.

    Examples::

        "見る-ホンホア"               -> ("見る", "ホンホア")
        "移動-廊下 (from-本部)"       -> ("移動", "廊下")
        "話す-ポゼッショナー [BATTLE]" -> ("話す", "ポゼッショナー")
        "考える"                      -> ("考える", None)
    """
    # Strip trailing annotations — everything from the first '(' or '[' onward
    core = note.split("(")[0].split("[")[0].strip()
    if "-" in core:
        verb, target = core.split("-", 1)
        return verb.strip() or None, target.strip() or None
    return core.strip() or None, None


def _choose_verifying(
    hwnd: int,
    step: dict,
    route: dict,
    route_path: Path,
    trace_fn=None,
) -> tuple[str | None, str | None]:
    """Navigate action+target menus with OCR-based index verification.

    For steps that are not yet ``verified``:
      1. OCR the verb panel *before* pressing anything — find the verb by label
         and correct ``step["action_index"]`` if the stored value is wrong.
      2. Navigate to the verb and press SPACE to open the target submenu.
      3. OCR the target panel *while the submenu is visible* — find the target
         by label and correct ``step["target_index"]`` if needed.
      4. Navigate to the target and confirm.
      5. Set ``step["verified"] = True`` and rewrite the route file if anything
         changed, so the next run uses the confirmed indices directly.

    For already-verified steps the OCR lookup is skipped; we just navigate
    using the stored indices (fast path identical to the old behaviour).

    Special case: ``action_index == 99`` means the verb position is unknown.
    If the OCR lookup finds the verb it is auto-corrected; if not, a
    ``RuntimeError`` is raised so the step is logged as an error and skipped.

    Returns ``(ocr_verb_en, ocr_target_en)`` for inclusion in the step report.
    """
    from ocr_cache import label_menu_screenshot, label_target_screenshot

    verified = step.get("verified", False)
    action_index: int = step["action_index"]
    target_index: int = step["target_index"]

    # Resolve human-readable hints: prefer explicit fields, fall back to note
    verb_hint: str | None = step.get("verb")
    target_hint: str | None = step.get("target")
    if not verb_hint and not target_hint:
        verb_hint, target_hint = _verb_target_from_note(step.get("note", ""))

    ocr_verb: str | None = None
    ocr_target: str | None = None
    changed = False
    verb_resolved = False    # True when OCR positively matched the verb
    target_resolved = False  # True when OCR positively matched the target (or no target needed)

    # No focus/click needed — all input goes via PostMessage (background-safe)

    # ------------------------------------------------------------------ verb
    if verb_hint:
        img = capture_window_image(hwnd)
        verb_labels = label_menu_screenshot(img)

        # If OCR returns empty, the screen likely shows dialogue/transition
        # text that wasn't fully advanced.  Press SPACE a few times to try
        # to reach the action menu before giving up.
        if not verb_labels:
            for _recovery in range(6):
                press_and_wait(hwnd, VK_BY_NAME["SPACE"],
                               change_timeout=4.0, stable_timeout=6.0, stable_period=0.8)
                img = capture_window_image(hwnd)
                verb_labels = label_menu_screenshot(img)
                if verb_labels:
                    if trace_fn:
                        trace_fn(f"menu appeared after {_recovery + 1} SPACE advance(s)")
                    break

        if not verified:
            idx = _find_label(verb_labels, verb_hint)
            if idx is not None:
                verb_resolved = True
                ocr_verb = verb_labels[idx][1] or verb_labels[idx][0]
                if idx != action_index:
                    step["action_index"] = idx
                    action_index = idx
                    changed = True
            else:
                # Check if this is a completely unexpected menu (H-scene)
                found_ja = {ja.strip() for ja, _en in verb_labels}
                if verb_labels and not (found_ja & NORMAL_VERBS):
                    raise UnexpectedMenuError(verb_hint, verb_labels)
                readable = [e or j for j, e in verb_labels]
                # Save debug crops for diagnosis
                from ocr_cache import _VERB_CROP
                img.save("debug_verb_mismatch_full.png")
                w, h = img.size
                l, t, r, b = _VERB_CROP
                img.crop((max(0,l), max(0,t), min(w,r), min(h,b))).save("debug_verb_mismatch_crop.png")
                raise MenuMismatchError("verb", verb_hint, readable)
        else:
            # Verified — just read the label for reporting
            if action_index < len(verb_labels):
                ocr_verb = verb_labels[action_index][1] or verb_labels[action_index][0]

    # action_index=99 is a placeholder for unknown special verbs; if OCR
    # could not resolve it, raise so the step is safely skipped.
    if action_index == 99:
        raise RuntimeError(
            f"action_index=99: could not OCR-resolve verb '{verb_hint}' -- "
            "fill in the correct action_index and set verified=false to retry"
        )

    # Navigate to verb
    for _ in range(action_index):
        press_and_wait(hwnd, VK_BY_NAME["DOWN"], change_timeout=3.0, wait_for_stable=False)
    press_and_wait(hwnd, VK_BY_NAME["SPACE"], change_timeout=5.0, stable_timeout=10.0, stable_period=0.75)
    time.sleep(0.5)

    # --------------------------------------------------------------- target
    if target_hint:
        img = capture_window_image(hwnd)
        target_labels = label_target_screenshot(img)
        if not verified:
            idx = _find_label(target_labels, target_hint)
            if idx is not None:
                target_resolved = True
                ocr_target = target_labels[idx][1] or target_labels[idx][0]
                if idx != target_index:
                    step["target_index"] = idx
                    target_index = idx
                    changed = True
            else:
                readable = [e or j for j, e in target_labels]
                # Fall back to the stored target_index if it's in range.
                if target_index < len(target_labels):
                    fallback_label = target_labels[target_index][1] or target_labels[target_index][0]
                    if trace_fn:
                        trace_fn(f"target '{target_hint}' not in {readable}, "
                                 f"fallback to idx={target_index} ('{fallback_label}')")
                else:
                    if trace_fn:
                        trace_fn(f"target '{target_hint}' not in {readable}, "
                                 f"fallback to idx={target_index} (best effort)")
        else:
            if target_index < len(target_labels):
                ocr_target = target_labels[target_index][1] or target_labels[target_index][0]

    # Navigate to target
    for _ in range(target_index):
        press_and_wait(hwnd, VK_BY_NAME["DOWN"], change_timeout=3.0, wait_for_stable=False)
    time.sleep(0.3)
    press_and_wait(hwnd, VK_BY_NAME["SPACE"], change_timeout=12.0, stable_timeout=16.0, stable_period=1.5)

    # Mark step verified when OCR positively matched both verb and target.
    if not verified:
        target_ok = target_resolved or (target_hint is None)
        if verb_resolved and target_ok:
            step["verified"] = True
            changed = True
    if changed:
        route_path.write_text(
            json.dumps(route, indent=2, ensure_ascii=False), encoding="utf-8"
        )

    return ocr_verb, ocr_target


# ---------------------------------------------------------------------------
# Single-slot runner
# ---------------------------------------------------------------------------

def run_slot(
    hwnd: int,
    slot_data: dict,
    slot_label: str,
    out_dir: Path,
    route: dict,
    route_path: Path,
    on_battle: str = "wait",
    start_step: int = 1,
    load_checkpoint: int | None = None,
    save_slot: int | None = None,
) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    file_index: int = slot_data.get("file_index", 0)
    steps: list[dict] = slot_data.get("steps", [])
    description: str = slot_data.get("description", slot_label)

    print(f"\n=== Slot {slot_label}: {description} ===")
    print(f"  file_index={file_index}, {len(steps)} step(s), output → {out_dir}")
    print(f"  on_battle={on_battle!r}")
    if start_step > 1:
        print(f"  start_step={start_step}" +
              (f" (loading checkpoint slot {load_checkpoint})" if load_checkpoint is not None else ""))
    if save_slot is not None:
        print(f"  save_slot={save_slot}")

    if load_checkpoint is not None and start_step > 1:
        # Skip normal startup — load emulator checkpoint and jump to step
        load_state_direct(hwnd, load_checkpoint)
        time.sleep(1.5)
        screenshot_window(hwnd, out_dir / "00-after-checkpoint-load.png")
        log_current_state(hwnd, "  After checkpoint load:")
        # Assume we're already at the action menu
        state = classify_screen_state(capture_window_image(hwnd))
        if state != "action_menu":
            # Try advancing through any residual dialogue
            _r = advance_capturing_text(
                hwnd, out_dir / "000-checkpoint-advance", "text",
                on_battle=on_battle, trace_fn=lambda m: None,
            )
            state = _r.final_state
        print(f"  Checkpoint loaded, state={state}")
    else:
        load_state: int | None = slot_data.get("load_state", None)
        if load_state is not None:
            load_state_direct(hwnd, load_state)
        else:
            time.sleep(4.0)

        screenshot_window(hwnd, out_dir / "00-after-load-state.png")
        log_current_state(hwnd, "  After load-state:")

        load_file_from_main_menu(hwnd, file_index=file_index)
        screenshot_window(hwnd, out_dir / "01-after-file-load.png")
        log_current_state(hwnd, "  After file load:")

        # Capture opening text pages individually
        opening_dir = out_dir / "000-opening"
        opening_result = advance_capturing_text(
            hwnd, opening_dir, "text",
            on_battle=on_battle,
            trace_fn=lambda m: None,
        )
        screenshot_window(hwnd, out_dir / "02-after-opening-advance.png")
        print(f"  Opening: {len(opening_result.pages)} page(s), state={opening_result.final_state}")
        state = opening_result.final_state

    prev_fingerprint: str | None = None
    prev_state: str = state
    if state == "action_menu":
        prev_fingerprint = _menu_fingerprint(hwnd)

    # Structured log written to report.json at the end
    step_records: list[dict] = []

    for step_index, step in enumerate(steps, start=1):
        # Skip steps before --start-step
        if step_index < start_step:
            continue

        # When resuming from a checkpoint, force OCR verification on ALL steps
        # — the "verified" flag assumes the normal startup sequence, which a
        # checkpoint skip may bypass (e.g. landing in an H-scene instead of
        # the expected adventure menu).
        if load_checkpoint is not None:
            step = dict(step, verified=False)

        # Auto-save checkpoint if configured
        if save_slot is not None and step.get("save_checkpoint"):
            save_state_direct(hwnd, save_slot)
            print(f"  💾 Saved checkpoint to slot {save_slot} at step {step_index}")

        action_index: int = step["action_index"]
        target_index: int = step["target_index"]
        note: str = step.get("note", f"step-{step_index}")
        repeat: int = max(1, step.get("repeat", 1))

        for rep in range(repeat):
            rep_suffix = f"-rep{rep + 1}" if repeat > 1 else ""
            step_label = f"{step_index:03d}{rep_suffix}"
            step_dir = out_dir / f"{step_label}-{note}"

            # Use the (possibly OCR-corrected) indices from the step dict.
            ai = step["action_index"]
            ti = step["target_index"]
            verified_tag = "✓" if step.get("verified") else "?"

            # Build verb→target from note for the progress line
            _v_hint, _t_hint = _verb_target_from_note(note)
            _progress_cmd = f"{_v_hint or '?'} → {_t_hint}" if _t_hint else (_v_hint or note)

            # Helper: overwrite current terminal line with a progress message
            _COL_WIDTH = 100

            def _progress(phase: str, detail: str = "") -> None:
                msg = f"  {step_label} [{verified_tag}] {_progress_cmd:24s}  {phase}"
                if detail:
                    msg += f" {detail}"
                # Pad to clear previous longer text, then \r to overwrite
                sys.stdout.write(f"\r{msg:<{_COL_WIDTH}}")
                sys.stdout.flush()

            _progress("choosing…")

            step_rec: dict = {
                "step": step_index,
                "rep": rep,
                "note": note,
                "action_index": ai,
                "target_index": ti,
                "ocr_verb": None,
                "ocr_target": None,
                "text_pages": [],
                "page_count": 0,
                "battle_detected": False,
                "crashed": False,
                "final_state": "unknown",
                "menu_fingerprint": None,
                "menu_changed": False,
                "error": None,
            }

            # Collect trace messages from _choose_verifying to show inline
            choose_notes: list[str] = []

            def _choose_trace(m: str) -> None:
                choose_notes.append(m)
                _progress("choosing…", m[:40])

            choose_ok = False
            for _attempt in range(2):
                try:
                    ocr_verb, ocr_target = _choose_verifying(
                        hwnd, step, route, route_path,
                        trace_fn=_choose_trace,
                    )
                    step_rec["ocr_verb"] = ocr_verb
                    step_rec["ocr_target"] = ocr_target
                    step_rec["action_index"] = step["action_index"]
                    step_rec["target_index"] = step["target_index"]
                    choose_ok = True
                    break
                except UnexpectedMenuError as ume:
                    if _attempt > 0:
                        step_rec["error"] = "H-scene still present after brute-force"
                        break
                    sys.stdout.write("\r" + " " * _COL_WIDTH + "\r")
                    print(f"  {step_label} [{verified_tag}] {note}")
                    print(f"    ⚡ H-SCENE — brute-forcing...")
                    from hscene_bruteforce import brute_force_hscene
                    hscene_dir = out_dir / f"{step_label}-hscene"
                    hscene_result = brute_force_hscene(
                        hwnd, ume.found_labels, hscene_dir,
                        on_battle=on_battle,
                        trace_fn=lambda m: print(f"      {m}"),
                    )
                    step_rec["hscene"] = {
                        "detected": True,
                        "expected_verb": ume.expected_verb,
                        "found_verbs": [{"ja": ja, "en": en} for ja, en in ume.found_labels],
                        "total_rounds": hscene_result.total_rounds,
                        "total_actions": len(hscene_result.actions),
                        "resolved": hscene_result.resolved,
                        "crashed": hscene_result.crashed,
                    }
                    if hscene_result.crashed:
                        step_rec["crashed"] = True
                        step_rec["error"] = "crash during H-scene brute-force"
                        print(f"    ⚡ H-scene CRASHED after {hscene_result.total_rounds} rounds")
                        break
                    if not hscene_result.resolved:
                        step_rec["error"] = "H-scene brute-force did not resolve"
                        print(f"    ⚡ H-scene unresolved after {hscene_result.total_rounds} rounds")
                        break
                    print(f"    ⚡ H-scene resolved ({hscene_result.total_rounds} rounds), retrying")
                except MenuMismatchError as mme:
                    step_rec["error"] = f"menu_mismatch: {mme}"
                    screenshot_window(hwnd, step_dir / "mismatch.png")
                    # Clear progress line and print final error line
                    sys.stdout.write("\r" + " " * _COL_WIDTH + "\r")
                    print(f"  {step_label} [{verified_tag}] {_progress_cmd:24s}  ✗ MISMATCH: {mme}")
                    break
                except Exception as exc:
                    step_rec["error"] = str(exc)
                    screenshot_window(hwnd, step_dir / "error.png")
                    sys.stdout.write("\r" + " " * _COL_WIDTH + "\r")
                    print(f"  {step_label} [{verified_tag}] {_progress_cmd:24s}  ✗ ERROR: {exc}")
                    break

            if not choose_ok:
                step_records.append(step_rec)
                continue

            # Show "advancing text…" with live page count
            _page_counter = [0]

            def _text_trace(m: str) -> None:
                # Count pages from trace messages like "p003: dialogue ..."
                if m.startswith("p") and ":" in m:
                    try:
                        _page_counter[0] = int(m[1:4]) + 1
                    except ValueError:
                        pass
                _progress("advancing…", f"({_page_counter[0]} pages)")

            _progress("advancing…")

            # Capture every text page produced by this action
            cap = advance_capturing_text(
                hwnd, step_dir, "text",
                on_battle=on_battle,
                trace_fn=_text_trace,
            )

            step_rec["text_pages"]     = [p.path for p in cap.pages]
            step_rec["page_count"]     = len(cap.pages)
            step_rec["battle_detected"] = cap.battle_detected
            step_rec["crashed"]        = cap.crashed
            step_rec["final_state"]    = cap.final_state

            screenshot_window(hwnd, out_dir / f"{step_label}-{note}.png")

            # Detect menu changes
            menu_note = ""
            if cap.final_state == "action_menu":
                fp = _menu_fingerprint(hwnd)
                changed = prev_fingerprint is not None and fp != prev_fingerprint
                step_rec["menu_fingerprint"] = fp
                step_rec["menu_changed"] = changed
                if changed:
                    menu_note = "  [MENU CHANGED]"
                prev_fingerprint = fp

            # Build concise verb→target description
            verb_desc = step_rec.get("ocr_verb") or note.split("-")[0]
            target_desc = step_rec.get("ocr_target") or ""
            if target_desc:
                cmd_desc = f"{verb_desc} → {target_desc}"
            else:
                cmd_desc = verb_desc

            # Build result description
            result_parts = []
            if cap.final_state != prev_state:
                result_parts.append(f"state={cap.final_state}")
            prev_state = cap.final_state
            if cap.pages:
                result_parts.append(f"{len(cap.pages)} page(s)")
            if cap.battle_detected:
                result_parts.append("BATTLE")
            if cap.crashed:
                result_parts.append("CRASH")
            # Show any choose_notes (fallback, recovery, etc.)
            for cn in choose_notes:
                result_parts.append(cn)

            result_str = ", ".join(result_parts)

            # Clear progress line and print final result
            sys.stdout.write("\r" + " " * _COL_WIDTH + "\r")
            print(f"  {step_label} [{verified_tag}] {cmd_desc:30s} → {result_str}{menu_note}")

            step_records.append(step_rec)

    # Write structured report
    report = {
        "slot": slot_label,
        "description": description,
        "file_index": file_index,
        "opening_pages": len(opening_result.pages),
        "steps": step_records,
        "total_pages": sum(r["page_count"] for r in step_records) + len(opening_result.pages),
        "total_crashes": sum(1 for r in step_records if r["crashed"]),
        "total_battles": sum(1 for r in step_records if r["battle_detected"]),
    }
    report_path = out_dir / "report.json"
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    # Console summary
    crashes = report["total_crashes"]
    battles = report["total_battles"]
    pages   = report["total_pages"]
    print(f"\n--- Slot {slot_label} summary ---")
    print(f"  {pages} total text page(s)  |  {crashes} crash(es)  |  {battles} battle(s)")
    for r in step_records:
        status = "CRASH" if r["crashed"] else ("BATTLE" if r["battle_detected"] else "OK")
        changed = "  [MENU CHANGED]" if r.get("menu_changed") else ""
        rep_tag = f"-rep{r['rep']+1}" if r["rep"] > 0 else ""
        print(f"  {r['step']:3d}{rep_tag}  {status:6s}  {r['note']:30s}  {r['page_count']} page(s){changed}")
    print(f"  Report: {report_path}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Run a scripted Possessioner walkthrough in the emulator.")
    p.add_argument("--emulator", type=Path, default=DEFAULT_EMULATOR_PATH, help=f"Path to np2debug executable (default: {DEFAULT_EMULATOR_PATH})")
    p.add_argument("--hdi", type=Path, default=DEFAULT_HDI_PATH, help=f"HDI image path (default: {DEFAULT_HDI_PATH})")
    p.add_argument("--route", type=Path, default=DEFAULT_ROUTE_PATH, help="Path to walkthrough route JSON")
    p.add_argument("--out", type=Path, required=True, help="Output directory for screenshots")
    slot_group = p.add_mutually_exclusive_group(required=False)
    slot_group.add_argument("--slot", default="full",
        help="Route slot key from walkthrough_route.json (default: 'full')")
    slot_group.add_argument("--all", action="store_true", help="Run all slots in the route file")
    p.add_argument("--close-existing", action="store_true", help="Close any running emulator before launch")
    p.add_argument("--no-close", action="store_true", help="Leave the emulator open after the run")
    p.add_argument(
        "--on-battle",
        choices=["wait", "skip", "resolve"],
        default="wait",
        help=(
            "What to do when a battle screen is detected. "
            "'wait' (default) beeps and pauses until you press Enter — use this when near the computer. "
            "'skip' saves a screenshot and abandons the current step — safe for unattended runs. "
            "'resolve' attempts automated mouse-click resolution (unreliable, use skip or wait instead)."
        ),
    )
    p.add_argument(
        "--start-step", type=int, default=1, metavar="N",
        help="Skip to step N (1-based). Requires a save state at that point — "
             "use --load-checkpoint SLOT to load an emulator save state "
             "instead of the normal route startup.",
    )
    p.add_argument(
        "--load-checkpoint", type=int, default=None, metavar="SLOT",
        help="Load emulator save state SLOT (0-9) then skip directly to "
             "--start-step, bypassing the normal file-load sequence.",
    )
    p.add_argument(
        "--save-slot", type=int, default=None, metavar="SLOT",
        help="Emulator save-state slot (0-9) to use for automatic checkpoints. "
             "Steps with \"save_checkpoint\": true in the route will auto-save "
             "to this slot when reached.",
    )
    return p


def main() -> None:
    args = build_parser().parse_args()

    route = load_route(args.route)
    save_states: dict = route.get("save_states", {})
    if not save_states:
        print("ERROR: no save_states found in route file", file=sys.stderr)
        sys.exit(1)

    if args.close_existing:
        close_existing_emulator_windows()

    hdi_abs = str(args.hdi.resolve())
    process = subprocess.Popen([str(args.emulator), hdi_abs], cwd=str(args.emulator.parent))
    hwnd = find_main_window()
    print(f"Emulator PID={process.pid} HWND=0x{hwnd:08x}")

    slots_to_run= list(save_states.keys()) if args.all else [args.slot]

    for slot_label in slots_to_run:
        if slot_label not in save_states:
            print(f"WARNING: slot {slot_label!r} not found in route file, skipping")
            continue
        slot_out = args.out / f"slot{slot_label}"
        run_slot(
            hwnd, save_states[slot_label], slot_label, slot_out,
            route=route, route_path=args.route,
            on_battle=args.on_battle,
            start_step=args.start_step,
            load_checkpoint=args.load_checkpoint,
            save_slot=args.save_slot,
        )

    if not args.no_close:
        win32gui.PostMessage(hwnd, win32con.WM_CLOSE, 0, 0)


if __name__ == "__main__":
    main()
