"""
Explore the current action menu by enumerating all verb/target combinations.

The emulator must already be running and showing an action_menu state.
The script navigates every verb with DOWN, opens each target submenu with SPACE,
cycles through all targets with DOWN, then returns to the action menu with ESC.
No action is ever actually executed.

Usage
-----
    python explore_menu.py --out out/explore

Output
------
    out/explore/action_00.png            — action menu, verb 0 highlighted
    out/explore/action_01.png            — action menu, verb 1 highlighted
    ...
    out/explore/action_00_target_00.png  — target submenu for verb 0, target 0
    out/explore/action_00_target_01.png  — target submenu for verb 0, target 1
    ...
    out/explore/report.json              — machine-readable summary
    out/explore/report.txt               — human-readable summary

OCR (via EasyOCR, free/local) is run on the baseline screenshots to label each
verb and target.  Results are cached in ocr_cache.json so each unique menu crop
is only processed once across all runs.  Pass --no-ocr to skip OCR entirely.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from pathlib import Path

from PIL import Image

from experiment_emulator_route import (
    VK_BY_NAME,
    _WC_CHROME_LEFT,
    _WC_CHROME_TOP,
    capture_window_image,
    find_emulator_windows,
    images_different,
    post_key,
    press_and_wait,
    screenshot_window,
    wait_for_content_change,
    wait_for_content_stable,
)
from ocr_cache import label_menu_screenshot, label_target_screenshot
from screen_state import classify_screen_state

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _game_crop(img: Image.Image) -> Image.Image:
    """Strip window chrome and return just the game area."""
    w, h = img.size
    return img.crop((_WC_CHROME_LEFT, _WC_CHROME_TOP, w - _WC_CHROME_LEFT, h - 4))


def _fingerprint(img: Image.Image) -> str:
    """MD5 hash of the greyscale game area — used for wrap-around detection."""
    raw = _game_crop(img).convert("L").tobytes()
    return hashlib.md5(raw).hexdigest()[:16]


def _panel_fingerprint(img: Image.Image) -> str:
    """MD5 hash of only the right-strip verb/target panel (top 45% of game area).

    Unlike _fingerprint(), this is unaffected by the dialogue box at the bottom
    of the screen.  Used to distinguish 'returned to action menu' (panel shows
    the known verb list) from 'opened target submenu' (panel shows targets).
    """
    area = _game_crop(img)
    w, h = area.size
    # Same bounds as screen_state._STRIP_X_START / _STRIP_Y_END
    x0 = int(w * 0.78)
    y1 = int(h * 0.45)
    panel = area.crop((x0, 0, w, y1)).convert("L")
    return hashlib.md5(panel.tobytes()).hexdigest()[:16]


def _require_action_menu(hwnd: int, context: str) -> None:
    img = capture_window_image(hwnd)
    state = classify_screen_state(img)
    if state != "action_menu":
        print(f"  WARNING: expected action_menu at {context}, got {state!r}")


def _press_down_and_wait(hwnd: int) -> Image.Image:
    """Press DOWN once and wait briefly for the cursor to move."""
    post_key(hwnd, VK_BY_NAME["DOWN"])
    time.sleep(0.25)          # menu cursor moves almost instantly; no need for long poll
    return capture_window_image(hwnd)


def _press_space_and_wait(hwnd: int) -> tuple[Image.Image, str]:
    """Press SPACE and wait for stable; return (image, classified_state)."""
    baseline = capture_window_image(hwnd)
    post_key(hwnd, VK_BY_NAME["SPACE"])
    wait_for_content_change(hwnd, baseline, timeout=5.0)
    wait_for_content_stable(hwnd, timeout=10.0, stable_period=0.75)
    img = capture_window_image(hwnd)
    return img, classify_screen_state(img)


def _press_esc_and_wait(hwnd: int) -> tuple[Image.Image, str]:
    """Press ESC and wait for stable; return (image, classified_state)."""
    baseline = capture_window_image(hwnd)
    post_key(hwnd, VK_BY_NAME["ESCAPE"])
    wait_for_content_change(hwnd, baseline, timeout=3.0)
    wait_for_content_stable(hwnd, timeout=8.0, stable_period=0.75)
    img = capture_window_image(hwnd)
    return img, classify_screen_state(img)


# ---------------------------------------------------------------------------
# Core exploration
# ---------------------------------------------------------------------------

def explore_current_menu(
    hwnd: int,
    out_dir: Path,
    *,
    max_actions: int = 12,
    max_targets: int = 6,
    use_ocr: bool = True,
) -> dict:
    """Enumerate all verbs and targets in the current action menu.

    Returns a summary dict with verb counts, target counts, and screenshot paths.
    Must be called while the emulator is showing an action_menu.
    """
    out_dir.mkdir(parents=True, exist_ok=True)

    # --- Baseline at action 0 ---
    img0 = capture_window_image(hwnd)
    state0 = classify_screen_state(img0)
    if state0 != "action_menu":
        print(f"ERROR: not at action_menu (state={state0!r}).  Run when action menu is visible.", file=sys.stderr)
        sys.exit(1)

    action0_fp       = _fingerprint(img0)        # full-screen fp — wrap sentinel
    action0_panel_fp = _panel_fingerprint(img0)  # panel-only fp — menu-vs-submenu
    # Set of panel fingerprints for every known action-menu cursor position.
    # After pressing SPACE, if the result panel fp is in this set we returned
    # to the action menu (no-submenu action like Think) rather than opening a
    # target submenu.
    known_action_panel_fps: set[str] = {action0_panel_fp}
    screenshot_window(hwnd, out_dir / "action_00.png")

    # OCR the baseline screenshot to get all verb labels top-to-bottom.
    # Running inline (not deferred) also gives the game a moment to settle
    # between navigation steps — removing this caused pacing issues.
    verb_labels: list[tuple[str, str]] = []
    if use_ocr:
        try:
            verb_labels = label_menu_screenshot(img0)
            print(f"  verb labels: {[en for _, en in verb_labels]}")
        except Exception as exc:
            print(f"  OCR failed: {exc}")

    print(f"  action 0: fingerprint={action0_fp}")

    actions: list[dict] = []
    action_index = 0
    current_action_fp       = action0_fp        # full-screen fp of current action position
    current_action_panel_fp = action0_panel_fp  # panel-only fp of current action position

    # --- Walk through each action ---
    while action_index < max_actions:
        verb_ja, verb_en = verb_labels[action_index] if action_index < len(verb_labels) else ("", "")
        action_entry: dict = {
            "action_index": action_index,
            "screenshot": f"action_{action_index:02d}.png",
            "verb_ja": verb_ja,
            "verb_en": verb_en,
            "targets": [],
            "note": "",
        }

        # Open the target submenu for this action
        img_after_space, state_after_space = _press_space_and_wait(hwnd)
        panel_fp_after = _panel_fingerprint(img_after_space)

        if state_after_space == "action_menu" and panel_fp_after in known_action_panel_fps:
            # The verb/target panel looks identical to a known action-menu cursor
            # position — SPACE returned us to the action menu without opening a
            # target submenu.  Typical of "Think"-style actions that execute
            # immediately.  The full-screen fingerprint may differ (dialogue box
            # content changes) but the panel is unambiguous.
            action_entry["note"] = "no-submenu (returned to action menu)"
            print(f"  action {action_index}: SPACE returned to action menu — no target submenu")
        elif state_after_space != "action_menu":
            # SPACE didn't open a target submenu — it either triggered a direct
            # dialogue (e.g. "Think") or a cutscene.  Only press SPACE again when
            # the red advance-arrow is visible; otherwise just wait for the game
            # to return to action_menu on its own.
            print(f"  action {action_index}: SPACE triggered {state_after_space!r} — waiting for action_menu (arrow-gated)")
            recovered = False
            for _attempt in range(20):
                time.sleep(0.4)
                img_cur = capture_window_image(hwnd)
                cur_state = classify_screen_state(img_cur)
                if cur_state == "action_menu":
                    recovered = True
                    break
                if cur_state == "battle":
                    print(f"    battle detected — stopping exploration")
                    break
                if cur_state == "dialogue":
                    # Red arrow confirmed — safe to press SPACE once
                    baseline = capture_window_image(hwnd)
                    post_key(hwnd, VK_BY_NAME["SPACE"])
                    wait_for_content_change(hwnd, baseline, timeout=3.0)
                    wait_for_content_stable(hwnd, timeout=6.0, stable_period=0.5)
                # else: loading or unknown — just loop and wait
            if recovered:
                action_entry["note"] = "no-submenu (direct, recovered)"
                print(f"    recovered to action_menu")
            else:
                action_entry["note"] = f"SPACE triggered {state_after_space!r}, could not recover"
                print(f"    could not recover — stopping exploration early")
                actions.append(action_entry)
                break
        else:
            # Enumerate targets in the submenu.
            target_fp_prev = _fingerprint(img_after_space)
            target_path = out_dir / f"action_{action_index:02d}_target_00.png"
            img_after_space.save(target_path)
            print(f"    target 0: fingerprint={target_fp_prev}")

            # OCR the baseline target screenshot to get all target labels
            target_labels: list[tuple[str, str]] = []
            if use_ocr:
                try:
                    target_labels = label_target_screenshot(img_after_space)
                    print(f"    target labels: {[en for _, en in target_labels]}")
                except Exception as exc:
                    print(f"    target OCR failed: {exc}")

            def _target_label(idx: int) -> tuple[str, str]:
                return target_labels[idx] if idx < len(target_labels) else ("", "")

            t_ja, t_en = _target_label(0)
            action_entry["targets"].append({
                "target_index": 0,
                "screenshot": target_path.name,
                "target_ja": t_ja,
                "target_en": t_en,
            })

            for target_index in range(1, max_targets + 1):
                img_t = _press_down_and_wait(hwnd)
                fp_t = _fingerprint(img_t)

                if fp_t == target_fp_prev:
                    # Cursor didn't move — already at last target
                    print(f"    target {target_index}: no change → {target_index} target(s) total")
                    break

                target_path = out_dir / f"action_{action_index:02d}_target_{target_index:02d}.png"
                img_t.save(target_path)
                print(f"    target {target_index}: fingerprint={fp_t}")
                t_ja, t_en = _target_label(target_index)
                action_entry["targets"].append({
                    "target_index": target_index,
                    "screenshot": target_path.name,
                    "target_ja": t_ja,
                    "target_en": t_en,
                })
                target_fp_prev = fp_t
            else:
                action_entry["note"] = f"target loop hit max ({max_targets}) — end not detected"
                print(f"    target loop hit max_targets={max_targets}")

            # ESC back to action menu.  Cursor resets to action 0.
            img_esc, state_esc = _press_esc_and_wait(hwnd)
            if state_esc != "action_menu":
                print(f"    WARNING: ESC did not return to action_menu (state={state_esc!r})")
                action_entry["note"] += f" | ESC→{state_esc!r}"

        actions.append(action_entry)

        # --- Advance to the next action ---
        # ESC reset cursor to action 0.  Navigate DOWN action_index times to
        # get back to the current position, then one more DOWN to advance.
        action_index += 1
        if action_index >= max_actions:
            print(f"  reached max_actions={max_actions} — stopping")
            break

        for _ in range(action_index - 1):
            _press_down_and_wait(hwnd)     # re-navigate to previous position

        img_next = _press_down_and_wait(hwnd)   # one more → new position
        fp_next       = _fingerprint(img_next)
        panel_fp_next = _panel_fingerprint(img_next)

        if panel_fp_next == current_action_panel_fp:
            # Panel unchanged — cursor didn't move, already at last action.
            # Use panel fp so that a changed dialogue box doesn't fool us.
            print(f"  action {action_index}: panel unchanged → {action_index} action(s) total")
            break

        if panel_fp_next == action0_panel_fp:
            # Panel matches action 0 — cursor wrapped back to the start.
            print(f"  action {action_index}: panel wrapped to action 0 → {action_index} action(s) total")
            break

        current_action_fp       = fp_next
        current_action_panel_fp = panel_fp_next
        known_action_panel_fps.add(panel_fp_next)

        # Save screenshot for this action position
        action_path = out_dir / f"action_{action_index:02d}.png"
        img_next.save(action_path)
        print(f"  action {action_index}: fingerprint={fp_next}")

    return {"actions": actions, "total_actions": len(actions)}


# ---------------------------------------------------------------------------
# Deferred OCR pass
# ---------------------------------------------------------------------------

def _add_ocr_labels(summary: dict, out_dir: Path) -> None:
    """Run OCR on saved baseline screenshots and fill in verb/target labels.

    Called after navigation is complete so the emulator loop is never blocked
    by OCR.  Results are served from ocr_cache.json on subsequent runs (fast).
    """
    # --- Verb labels from the action-0 baseline ---
    baseline = out_dir / "action_00.png"
    verb_labels: list[tuple[str, str]] = []
    if baseline.exists():
        try:
            verb_labels = label_menu_screenshot(Image.open(baseline))
            print(f"  verb labels: {[en for _, en in verb_labels]}")
        except Exception as exc:
            print(f"  verb OCR failed: {exc}")

    for a in summary["actions"]:
        ai = a["action_index"]
        if ai < len(verb_labels):
            a["verb_ja"], a["verb_en"] = verb_labels[ai]

        # --- Target labels from the first-target baseline for this action ---
        t0_path = out_dir / f"action_{ai:02d}_target_00.png"
        target_labels: list[tuple[str, str]] = []
        if t0_path.exists():
            try:
                target_labels = label_target_screenshot(Image.open(t0_path))
                print(f"  action {ai} target labels: {[en for _, en in target_labels]}")
            except Exception as exc:
                print(f"  action {ai} target OCR failed: {exc}")

        for t in a["targets"]:
            ti = t["target_index"]
            if ti < len(target_labels):
                t["target_ja"], t["target_en"] = target_labels[ti]


# ---------------------------------------------------------------------------
# Tree pretty-print
# ---------------------------------------------------------------------------

def print_action_tree(summary: dict, out_dir: Path | None = None) -> None:
    """Print a tree of discovered actions and targets to stdout."""
    actions = summary["actions"]
    n = len(actions)
    label = str(out_dir) if out_dir else "current location"
    print(f"\n{label} - {n} action(s)")
    for ai, a in enumerate(actions):
        is_last_action = ai == n - 1
        branch = "`--" if is_last_action else "+--"
        verb = a.get("verb_en") or a.get("verb_ja") or "?"
        note = f"  [{a['note']}]" if a["note"] else ""
        targets = a["targets"]
        print(f"{branch} {a['action_index']}  {verb}{note}")
        for ti, t in enumerate(targets):
            is_last_target = ti == len(targets) - 1
            indent = "    " if is_last_action else "|   "
            tbranch = "`--" if is_last_target else "+--"
            tgt = t.get("target_en") or t.get("target_ja") or "?"
            print(f"{indent}{tbranch} {t['target_index']}  {tgt}")
    print()


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------

def _write_report(summary: dict, out_dir: Path) -> None:
    # JSON
    json_path = out_dir / "report.json"
    with json_path.open("w", encoding="utf-8") as fh:
        json.dump(summary, fh, indent=2, ensure_ascii=False)
    print(f"\nWrote {json_path}")

    # Human-readable text
    txt_path = out_dir / "report.txt"
    lines = [
        "Possessioner menu exploration report",
        "=====================================",
        f"Total actions: {summary['total_actions']}",
        "",
        "To use in walkthrough_route.json:",
        "  action_index = 0-based DOWN presses before SPACE on the action menu",
        "  target_index = 0-based DOWN presses before SPACE on the target submenu",
        "",
    ]
    for a in summary["actions"]:
        ai = a["action_index"]
        tcount = len(a["targets"])
        note = f"  [{a['note']}]" if a["note"] else ""
        verb = f"  {a.get('verb_en') or a.get('verb_ja') or '?'}"
        lines.append(f"  action {ai:2d} ({tcount} target(s)){verb}  → see {a['screenshot']}{note}")
        for t in a["targets"]:
            tgt = f"  {t.get('target_en') or t.get('target_ja') or '?'}"
            lines.append(f"    target {t['target_index']:2d}{tgt}  → see {t['screenshot']}")
    lines += [""]
    txt_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"Wrote {txt_path}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Enumerate all action-menu verbs and targets in the running emulator.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--out", type=Path, required=True, help="Directory for screenshots and report")
    parser.add_argument("--max-actions", type=int, default=12, help="Safety limit on verb count (default 12)")
    parser.add_argument("--max-targets", type=int, default=6, help="Safety limit on target count (default 6)")
    parser.add_argument("--no-ocr", action="store_true", help="Skip OCR labelling (faster, no easyocr required)")
    args = parser.parse_args()

    windows = find_emulator_windows()
    if not windows:
        print("ERROR: no emulator window found — start np2debug first.", file=sys.stderr)
        sys.exit(1)
    hwnd = windows[0]

    print(f"Exploring action menu in window 0x{hwnd:08x} …")
    print(f"Output → {args.out}\n")

    summary = explore_current_menu(
        hwnd,
        args.out,
        max_actions=args.max_actions,
        max_targets=args.max_targets,
        use_ocr=not args.no_ocr,
    )

    _write_report(summary, args.out)
    print_action_tree(summary, args.out)


if __name__ == "__main__":
    main()
