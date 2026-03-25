"""
Drive the Possessioner emulator through a scripted walkthrough.

Reads walkthrough_route.json (or a file supplied via --route) and executes each
step with adaptive text advancement powered by the Claude vision classifier in
screen_state.py.  A screenshot is saved after every step so you can inspect
what happened.

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
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

import win32con
import win32gui

from experiment_emulator_route import (
    DEFAULT_EMULATOR_PATH,
    DEFAULT_HDI_PATH,
    advance_to_menu,
    capture_window_image,
    choose_menu_target,
    close_existing_emulator_windows,
    find_main_window,
    load_file_from_main_menu,
    load_state_direct,
    screenshot_window,
    wait_for_content_stable,
)
from screen_state import classify_screen_state

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
# Single-slot runner
# ---------------------------------------------------------------------------

def run_slot(
    hwnd: int,
    slot_data: dict,
    slot_label: str,
    out_dir: Path,
) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    file_index: int = slot_data.get("file_index", 0)
    steps: list[dict] = slot_data.get("steps", [])
    description: str = slot_data.get("description", slot_label)

    print(f"\n=== Slot {slot_label}: {description} ===")
    print(f"  file_index={file_index}, {len(steps)} step(s), output → {out_dir}")

    # Optionally load an emulator save state (e.g. slot 0 = main menu).
    # Defaults to None (skip), since save states are volatile.
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

    # Advance through any opening text before the first interactive menu
    state = advance_to_menu(
        hwnd,
        classify_screen_state,
        trace_fn=lambda message: print(f"    [advance-opening] {message}"),
    )
    screenshot_window(hwnd, out_dir / "02-after-opening-advance.png")
    print(f"  Opening advance → state={state!r}")

    for step_index, step in enumerate(steps, start=1):
        action_index: int = step["action_index"]
        target_index: int = step["target_index"]
        note: str = step.get("note", f"step-{step_index}")
        repeat: int = max(1, step.get("repeat", 1))

        for rep in range(repeat):
            rep_suffix = f"-rep{rep + 1}" if repeat > 1 else ""
            frame_name = f"{step_index:03d}{rep_suffix}-{note}.png"
            print(f"  Step {step_index}{rep_suffix}: action={action_index} target={target_index}  ({note})")
            log_current_state(hwnd, "    Before choose:")

            try:
                choose_menu_target(
                    hwnd,
                    action_index,
                    target_index,
                    trace_fn=lambda message, step_label=f"{step_index}{rep_suffix}": print(
                        f"    [choose {step_label}] {message}"
                    ),
                )
            except Exception as exc:
                print(f"    WARNING: choose_menu_target failed: {exc}")
                screenshot_window(hwnd, out_dir / f"{frame_name}.error.png")
                continue

            log_current_state(hwnd, "    After choose:")
            state = advance_to_menu(
                hwnd,
                classify_screen_state,
                trace_fn=lambda message, step_label=f"{step_index}{rep_suffix}": print(
                    f"    [advance {step_label}] {message}"
                ),
            )
            screenshot_window(hwnd, out_dir / frame_name)
            print(f"    → state after advance: {state!r}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Run a scripted Possessioner walkthrough in the emulator.")
    p.add_argument("--emulator", type=Path, default=DEFAULT_EMULATOR_PATH, help=f"Path to np2debug executable (default: {DEFAULT_EMULATOR_PATH})")
    p.add_argument("--hdi", type=Path, default=DEFAULT_HDI_PATH, help=f"HDI image path (default: {DEFAULT_HDI_PATH})")
    p.add_argument("--route", type=Path, default=DEFAULT_ROUTE_PATH, help="Path to walkthrough route JSON")
    p.add_argument("--out", type=Path, required=True, help="Output directory for screenshots")
    slot_group = p.add_mutually_exclusive_group(required=True)
    slot_group.add_argument("--slot", help="Save state slot to run (key in walkthrough_route.json)")
    slot_group.add_argument("--all", action="store_true", help="Run all slots in the route file")
    p.add_argument("--close-existing", action="store_true", help="Close any running emulator before launch")
    p.add_argument("--no-close", action="store_true", help="Leave the emulator open after the run")
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

    process = subprocess.Popen([str(args.emulator), str(args.hdi)], cwd=str(args.emulator.parent))
    hwnd = find_main_window()
    print(f"Emulator PID={process.pid} HWND=0x{hwnd:08x}")

    slots_to_run = list(save_states.keys()) if args.all else [args.slot]

    for slot_label in slots_to_run:
        if slot_label not in save_states:
            print(f"WARNING: slot {slot_label!r} not found in route file, skipping")
            continue
        slot_out = args.out / f"slot{slot_label}"
        run_slot(hwnd, save_states[slot_label], slot_label, slot_out)

    if not args.no_close:
        win32gui.PostMessage(hwnd, win32con.WM_CLOSE, 0, 0)


if __name__ == "__main__":
    main()
