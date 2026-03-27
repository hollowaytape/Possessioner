"""run_walkthrough.py — Memory-based walkthrough runner for Possessioner.

Drives the game using mem_navigate.MemNavigator: all menu navigation is
verified by reading cursor position, depth, and count from emulator
process memory.  No OCR, no screen classification, no recovery loops.

Usage:
    python run_walkthrough.py                    # run full slot from step 0
    python run_walkthrough.py --start-step 7     # resume from step 7
    python run_walkthrough.py --slot battle_test  # run a different slot
"""

from __future__ import annotations

import argparse
import json
import os
import time

from mem_navigate import MemNavigator, NavigationTimeout
from experiment_emulator_route import (
    find_main_window, post_key, VK_BY_NAME,
    load_state_direct, save_state_direct,
    capture_window_image,
)


# ── Helpers ───────────────────────────────────────────────────────

def _move_skip_set(verb_count: int) -> set[int] | None:
    """Return a set of verb indices to skip during brute-force.

    When Move is available (typically at index 0 in a 5-verb menu),
    we must not brute-force it — it would change rooms.  H-scenes
    (2-4 verbs) never have Move, so skip nothing.
    """
    if verb_count >= 5:
        return {0}  # Move is always at the top
    return None


# ── Route loading ────────────────────────────────────────────────────

def load_route(path: str = "walkthrough_route.json") -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


# ── Game startup ─────────────────────────────────────────────────────

def start_game(hwnd: int, nav: MemNavigator,
               load_state: int = 0, file_index: int = 0):
    """Load emulator state, navigate the file-select menu, and wait
    for the game's verb menu to become ready."""
    load_state_direct(hwnd, slot=load_state)
    time.sleep(2)
    # Continue (first menu item) → ENTER
    post_key(hwnd, VK_BY_NAME['DOWN']); time.sleep(0.3)
    post_key(hwnd, VK_BY_NAME['ENTER']); time.sleep(2)
    # Select file (DOWN × file_index+1, then ENTER)
    for _ in range(file_index + 1):
        post_key(hwnd, VK_BY_NAME['DOWN']); time.sleep(0.2)
    post_key(hwnd, VK_BY_NAME['ENTER'])
    # Wait for verb menu to appear (game loads + opening text)
    nav._advance_to_verb_menu(timeout=30.0)


# ── Walkthrough runner ───────────────────────────────────────────────

def run_slot(slot_name: str, route_data: dict, *,
             start_step: int = 0,
             verbose: bool = True,
             screenshot_dir: str | None = None,
             base_address: int | None = None):
    """Execute a walkthrough slot step-by-step using memory navigation.

    Parameters
    ----------
    slot_name : str
        Key in route_data["save_states"] (e.g. "full").
    route_data : dict
        Loaded walkthrough_route.json.
    start_step : int
        1-based step number to skip to (0 = start from beginning).
    verbose : bool
        Print per-step progress.
    screenshot_dir : str or None
        If set, save a screenshot after each step that changes the scene.
    base_address : int or None
        Known MemBridge base address (speeds up attachment).
    """
    slot = route_data["save_states"][slot_name]
    steps = slot["steps"]

    hwnd = find_main_window(timeout=5.0)
    print(f"Emulator: hwnd=0x{hwnd:X}")

    nav = MemNavigator(hwnd, known_base=base_address)
    b = nav.bridge
    print(f"Bridge: base=0x{b.base:X}")

    # Start the game and wait for verb menu
    start_game(hwnd, nav,
               slot.get("load_state", 0), slot.get("file_index", 0))
    print(f"Game ready: {b.menu_state()}")
    print()

    if screenshot_dir:
        os.makedirs(screenshot_dir, exist_ok=True)

    t0 = time.time()
    step_num = 0          # 1-based running step counter (with repeats)
    completed = 0
    skipped = 0
    consecutive_fails = 0
    stop = False
    errors = []

    for i, step in enumerate(steps):
        if stop:
            break
        note = step.get("note", "???")
        action = step["action_index"]
        target = step.get("target_index", 0)
        repeat = step.get("repeat", 1)
        is_battle = "[BATTLE]" in note

        for rep in range(repeat):
            if stop:
                break
            step_num += 1
            if step_num < start_step:
                continue

            label = note + (f" (#{rep+1})" if repeat > 1 else "")

            # ── Unresolved action index ──────────────────────────
            if action == 99:
                if verbose:
                    print(f"  {step_num:03d} [SKIP] {label}"
                          f"  — action_index=99 (unresolved)")
                skipped += 1
                consecutive_fails += 1
                if consecutive_fails >= 3:
                    print(f"       3 consecutive failures — stopping.")
                    stop = True
                    break
                continue

            # ── Verify verb is reachable ─────────────────────────
            vc = b.menu_count()
            if action >= vc:
                if verbose:
                    print(f"  {step_num:03d} [WAIT] {label}"
                          f"  — verb {action} not available (vc={vc}),"
                          f" brute-forcing scene...")
                # Skip Move (verb 0) during brute-force if it exists
                move_skip = _move_skip_set(vc)
                try:
                    bf = nav.brute_force_scene(verbose=verbose,
                                               min_attempts=3,
                                               skip_verbs=move_skip)
                    if verbose:
                        print(f"       brute-force: {bf['steps']} steps,"
                              f" map=0x{nav.map_byte:02X}")
                except NavigationTimeout as e:
                    msg = f"Step {step_num} brute-force failed: {e}"
                    errors.append(msg)
                    if verbose:
                        print(f"  {step_num:03d} [FAIL] {label} — {e}")
                    consecutive_fails += 1
                    if consecutive_fails >= 3:
                        print(f"       3 consecutive failures — stopping.")
                        stop = True
                        break
                    continue

                # Re-check
                vc = b.menu_count()
                if action >= vc:
                    msg = (f"Step {step_num}: verb {action} still not "
                           f"available after brute-force (vc={vc})")
                    errors.append(msg)
                    if verbose:
                        print(f"  {step_num:03d} [FAIL] {label}"
                              f"  — verb still missing (vc={vc})")
                    consecutive_fails += 1
                    if consecutive_fails >= 3:
                        print(f"       3 consecutive failures — stopping.")
                        stop = True
                        break
                    continue

            # ── Execute the step ─────────────────────────────────
            map_before = nav.map_byte
            try:
                result = nav.do_action(action, target)
            except NavigationTimeout as e:
                msg = f"Step {step_num} ({label}): {e}"
                errors.append(msg)
                if verbose:
                    print(f"  {step_num:03d} [FAIL] {label} — {e}")
                # Try to recover to verb menu
                try:
                    nav._advance_to_verb_menu(timeout=30.0)
                except NavigationTimeout:
                    print(f"       Could not recover — stopping.")
                    stop = True
                    break
                consecutive_fails += 1
                if consecutive_fails >= 3:
                    print(f"       3 consecutive failures — stopping.")
                    stop = True
                    break
                continue

            consecutive_fails = 0   # reset on success

            map_after = nav.map_byte
            new_vc = result["verb_count_after"]
            flags = ""
            if result["scene_changed"]:
                flags += f" ★ MAP 0x{map_after:02X}"
            if new_vc != vc:
                flags += f" vc={vc}→{new_vc}"

            if verbose:
                print(f"  {step_num:03d} {label:45s}{flags}")

            completed += 1

            # ── Handle battle → H-scene aftermath ────────────────
            if result["scene_changed"] and is_battle:
                if verbose:
                    print(f"       → Battle aftermath at map"
                          f" 0x{map_after:02X}, brute-forcing...")
                move_skip = _move_skip_set(b.menu_count())
                try:
                    bf = nav.brute_force_scene(verbose=verbose,
                                               min_attempts=3,
                                               skip_verbs=move_skip)
                    if verbose:
                        print(f"       → Done: {bf['steps']} steps,"
                              f" map=0x{nav.map_byte:02X}")
                except NavigationTimeout as e:
                    msg = f"Step {step_num} H-scene failed: {e}"
                    errors.append(msg)
                    if verbose:
                        print(f"       → H-scene failed: {e}")

            # ── Screenshot on scene change ───────────────────────
            if screenshot_dir and result["scene_changed"]:
                path = os.path.join(screenshot_dir,
                                    f"{step_num:03d}_map{map_after:02X}.png")
                capture_window_image(hwnd).save(path)

            # ── Save checkpoint if requested ─────────────────────
            if step.get("save_checkpoint") and rep == repeat - 1:
                save_state_direct(hwnd, slot=1)
                if verbose:
                    print(f"       → Checkpoint saved (slot 1)")

    elapsed = time.time() - t0
    print(f"\n{'='*60}")
    print(f"Completed: {completed} steps in {elapsed:.0f}s")
    print(f"Skipped:   {skipped}")
    print(f"Errors:    {len(errors)}")
    print(f"Final:     map=0x{nav.map_byte:02X}"
          f"  d={b.menu_depth()} c={b.menu_count()}")
    if errors:
        print(f"\nError details:")
        for e in errors:
            print(f"  • {e}")
    print()
    nav.close()
    return {"completed": completed, "skipped": skipped,
            "errors": errors, "elapsed": elapsed}


# ── CLI entry point ──────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Memory-based Possessioner walkthrough runner"
    )
    parser.add_argument("--slot", default="full",
                        help="Save-state slot name (default: full)")
    parser.add_argument("--start-step", type=int, default=0,
                        help="1-based step to resume from")
    parser.add_argument("--route", default="walkthrough_route.json",
                        help="Path to route JSON")
    parser.add_argument("--screenshots", default=None,
                        help="Directory for scene-change screenshots")
    parser.add_argument("--base", type=lambda x: int(x, 0), default=None,
                        help="Known MemBridge base address (hex)")
    parser.add_argument("-q", "--quiet", action="store_true",
                        help="Suppress per-step output")
    args = parser.parse_args()

    route = load_route(args.route)
    run_slot(args.slot, route,
             start_step=args.start_step,
             verbose=not args.quiet,
             screenshot_dir=args.screenshots,
             base_address=args.base)


if __name__ == "__main__":
    main()
