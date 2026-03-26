"""
Exhaustive text scanner for Possessioner emulator automation.

For every reachable game location and every action×target combination, this
script:

1. Saves emulator state to a scratch slot.
2. Executes the action.
3. Advances through all resulting text pages, screenshotting each one.
4. Detects crashes (game stops responding).
5. Restores emulator state.
6. Repeats steps 1–5 up to --repeat times per option, stopping early once
   page fingerprints stop producing new content (loop detection).
7. Follows Move actions to new locations (depth-limited).
8. Writes a location graph JSON showing how rooms connect.

Artifacts produced
------------------
    out/
      location_graph.json              -- empirical graph of all discovered locations
      loc_{fp8}/
        explore/                       -- explore_menu output (action labels, crops)
        a{ai:02d}_t{ti:02d}_{en}/     -- one dir per action×target
          attempt_{n}/
            text_p000.png ... .png     -- every dialogue/cutscene page
          result.json                  -- summary: attempts, pages seen, new pages, crashes
        location_report.json           -- summary for this location

Usage
-----
    # Exhaust all text reachable from current emulator state (up to depth 4)
    python exhaust_text.py --out out/exhaust --max-depth 4

    # Start from a specific save-state slot
    python exhaust_text.py --out out/exhaust --load-state 0 --file-index 2

    # Limit to top-level location only (no Move following)
    python exhaust_text.py --out out/exhaust --max-depth 0

    # Use scratch save slots 5-9 (default) or 1-4 (for deeper trees)
    python exhaust_text.py --out out/exhaust --scratch-base 5

Scratch slot allocation
-----------------------
The script saves state at each depth level using:
    slot = scratch_base + depth
With the default --scratch-base 5 and --max-depth 4, slots 5-9 are used.
Slots 0-4 are left untouched (they hold your checkpoint save states).

Repeat / loop detection
-----------------------
Each option is tried up to --repeat times.  After each attempt the page
fingerprints are compared against all fingerprints seen for this option so far.
If an attempt produces zero new fingerprints the option is considered exhausted
and remaining attempts are skipped.  Default --repeat 3.

Battle handling
---------------
When a battle is detected:
  * The pre-battle state is saved to slot (scratch_base + depth + BATTLE_SLOT_OFFSET).
  * A note is written to the report so you can identify which action triggers it.
  * The user is prompted to resolve the battle manually (then continue), unless
    --skip-battles is passed (in which case the attempt is abandoned immediately).
  * This pre-battle save state is the artifact needed for RE of unskippable battles.

In-game DATA saves
------------------
The in-game SYSTEM→Save is not yet automated (SYSTEM menu navigation is TBD).
When a battle is detected you can manually make an in-game save using the SYSTEM
menu in the emulator.  The script will print a reminder and wait.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from PIL import Image

from experiment_emulator_route import (
    DEFAULT_EMULATOR_PATH,
    DEFAULT_HDI_PATH,
    VK_BY_NAME,
    _WC_CHROME_LEFT,
    _WC_CHROME_TOP,
    capture_window_image,
    choose_menu_target,
    close_existing_emulator_windows,
    find_main_window,
    load_file_from_main_menu,
    load_state_direct,
    post_key,
    save_state_direct,
    screenshot_window,
    wait_for_content_stable,
)
from explore_menu import explore_current_menu, print_action_tree
from screen_state import classify_screen_state
from text_capture import TextCaptureResult, advance_capturing_text, page_fingerprint

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

BATTLE_SLOT_OFFSET = 10   # battle save: slot = scratch_base + depth + BATTLE_SLOT_OFFSET
                           # e.g. scratch_base=5, depth=0 → battle slot 15. Adjust if needed.
                           # (NP2 supports up to slot 9, so default is effectively capped;
                           #  change scratch_base to use lower range if you need battle saves)
DEFAULT_SCRATCH_BASE = 5
DEFAULT_MAX_DEPTH    = 4
DEFAULT_REPEAT       = 3


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _game_crop(img: Image.Image) -> Image.Image:
    w, h = img.size
    return img.crop((_WC_CHROME_LEFT, _WC_CHROME_TOP, w - _WC_CHROME_LEFT, h - 4))


def _location_fp(img: Image.Image) -> str:
    """Fingerprint the scene background (centre strip, excludes verb column and text box).

    Stable within a location even if the cursor position or dialogue box content
    changes.  Different between rooms because the background artwork differs.
    """
    area = _game_crop(img)
    w, h = area.size
    # Use left 73% × top 68% — this is the scene artwork, excluding the verb
    # column (right ~22%) and the text box (bottom ~22%).
    scene = area.crop((int(w * 0.05), int(h * 0.05), int(w * 0.73), int(h * 0.68)))
    return hashlib.md5(scene.convert("L").tobytes()).hexdigest()[:16]


def _safe_slug(text: str, maxlen: int = 20) -> str:
    """ASCII-safe filename slug for a label."""
    slug = "".join(c if c.isalnum() or c in "-_" else "_" for c in text)
    return slug[:maxlen].strip("_") or "unknown"


# ---------------------------------------------------------------------------
# No-target action execution (Think-style actions)
# ---------------------------------------------------------------------------

def _execute_action_no_target(hwnd: int, action_index: int) -> None:
    """Navigate the verb cursor to action_index and press SPACE exactly once.

    Used for actions that have no target submenu (e.g. Think/考える).
    choose_menu_target() presses SPACE twice (open submenu + confirm), which
    is wrong for these actions.
    """
    for _ in range(action_index):
        post_key(hwnd, VK_BY_NAME["DOWN"])
        time.sleep(0.25)
    post_key(hwnd, VK_BY_NAME["SPACE"])
    time.sleep(0.3)


# ---------------------------------------------------------------------------
# Per-action exhaustion
# ---------------------------------------------------------------------------

@dataclass
class ActionAttempt:
    attempt_index: int
    page_count: int
    new_page_count: int
    crashed: bool
    battle_detected: bool
    final_state: str
    page_fingerprints: list[str]
    out_dir: str


@dataclass
class ActionResult:
    action_index: int
    target_index: int          # -1 for no-target actions
    verb_ja: str
    verb_en: str
    target_ja: str
    target_en: str
    attempts: list[ActionAttempt] = field(default_factory=list)
    total_pages: int = 0
    total_new_pages: int = 0
    crashed: bool = False
    battle_detected: bool = False
    battle_slot: int = -1      # emulator slot where pre-battle state was saved
    led_to_new_location: bool = False
    new_location_fp: str = ""
    stopped_after_attempts: int = 0
    note: str = ""


def exhaust_action(
    hwnd: int,
    action_entry: dict,
    target_entry: dict | None,
    loc_dir: Path,
    scratch_slot: int,
    battle_slot: int,
    repeat: int,
    on_battle: str,
    loc_fp_before: str,
) -> ActionResult:
    """Try one action×target up to `repeat` times, stopping when pages stop changing.

    Parameters
    ----------
    action_entry: dict from explore_current_menu['actions']
    target_entry: dict from action_entry['targets'], or None for no-target actions
    loc_dir: output directory for this location
    scratch_slot: emulator save slot to use for save/restore
    battle_slot: emulator save slot to save the pre-battle state
    repeat: max number of attempts
    on_battle: 'wait' or 'skip'
    loc_fp_before: location fingerprint before executing, used to detect relocation
    """
    ai = action_entry["action_index"]
    ti = target_entry["target_index"] if target_entry is not None else -1
    verb_en = action_entry.get("verb_en") or action_entry.get("verb_ja") or f"a{ai}"
    verb_ja = action_entry.get("verb_ja", "")
    target_en = (target_entry or {}).get("target_en") or (target_entry or {}).get("target_ja") or (f"t{ti}" if ti >= 0 else "")
    target_ja = (target_entry or {}).get("target_ja", "")

    slug = _safe_slug(f"{verb_en}_{target_en}" if target_en else verb_en)
    action_dir = loc_dir / f"a{ai:02d}_t{ti:02d}_{slug}"
    action_dir.mkdir(parents=True, exist_ok=True)

    result = ActionResult(
        action_index=ai,
        target_index=ti,
        verb_ja=verb_ja,
        verb_en=verb_en,
        target_ja=target_ja,
        target_en=target_en,
        note=action_entry.get("note", ""),
    )

    seen_fps: set[str] = set()

    for attempt_i in range(repeat):
        attempt_dir = action_dir / f"attempt_{attempt_i}"
        attempt_dir.mkdir(parents=True, exist_ok=True)

        # Save state before this attempt
        save_state_direct(hwnd, scratch_slot)
        time.sleep(0.4)

        # Execute the action
        try:
            if ti < 0:
                # No-target action (Think, etc.)
                _execute_action_no_target(hwnd, ai)
            else:
                choose_menu_target(hwnd, ai, ti)
        except Exception as exc:
            print(f"    choose_menu_target failed: {exc}")
            load_state_direct(hwnd, scratch_slot)
            time.sleep(0.8)
            break

        # Capture all text pages for this attempt
        cap = advance_capturing_text(
            hwnd,
            attempt_dir,
            "text",
            on_battle=on_battle,
            known_page_fps=seen_fps,
            trace_fn=lambda m: print(f"      {m}"),
        )

        # Battle handling: save pre-battle emulator state as artifact
        if cap.battle_detected and not result.battle_detected:
            result.battle_detected = True
            try:
                save_state_direct(hwnd, battle_slot)
                result.battle_slot = battle_slot
                print(f"    Pre-battle state saved to slot {battle_slot}")
                print(f"    NOTE: Make an in-game SYSTEM save now if you want a DATA* file.")
            except Exception as e:
                print(f"    Could not save battle state: {e}")

        # Collect fingerprints from this attempt
        attempt_fps = [p.fingerprint for p in cap.pages]
        new_fps = [fp for fp in attempt_fps if fp not in seen_fps]
        seen_fps.update(attempt_fps)

        attempt_rec = ActionAttempt(
            attempt_index=attempt_i,
            page_count=len(cap.pages),
            new_page_count=len(new_fps),
            crashed=cap.crashed,
            battle_detected=cap.battle_detected,
            final_state=cap.final_state,
            page_fingerprints=attempt_fps,
            out_dir=str(attempt_dir),
        )
        result.attempts.append(attempt_rec)
        result.total_pages += len(cap.pages)
        result.total_new_pages += len(new_fps)
        if cap.crashed:
            result.crashed = True
        result.stopped_after_attempts = attempt_i + 1

        tag = f"({len(new_fps)} new)" if new_fps else "(no new content)"
        print(f"    attempt {attempt_i}: {len(cap.pages)} page(s) {tag}  final={cap.final_state!r}")

        if cap.crashed:
            print(f"    CRASH detected — stopping attempts for this action")
            load_state_direct(hwnd, scratch_slot)
            time.sleep(0.8)
            break

        # Check if we ended at a new location (e.g. Move action brought us somewhere new)
        if cap.final_state == "action_menu" and attempt_i == 0:
            img_after = capture_window_image(hwnd)
            loc_fp_after = _location_fp(img_after)
            if loc_fp_after != loc_fp_before:
                result.led_to_new_location = True
                result.new_location_fp = loc_fp_after
                print(f"    New location reached: {loc_fp_after}")

        # Restore state
        load_state_direct(hwnd, scratch_slot)
        time.sleep(0.8)
        wait_for_content_stable(hwnd, timeout=8.0, stable_period=0.8)

        # Loop detection: stop if no new content this attempt
        if attempt_i > 0 and not new_fps:
            print(f"    No new pages in attempt {attempt_i} — text exhausted")
            break

    # Write per-action result JSON
    result_path = action_dir / "result.json"
    result_path.write_text(
        json.dumps(asdict(result), indent=2, ensure_ascii=False), encoding="utf-8"
    )

    return result


# ---------------------------------------------------------------------------
# Per-location exhaustion
# ---------------------------------------------------------------------------

@dataclass
class LocationRecord:
    fp: str
    label: str              # verb+location slug for display
    out_dir: str
    depth: int
    action_results: list[dict] = field(default_factory=list)
    connections: list[dict] = field(default_factory=list)  # {action, target, dest_fp, dest_label}
    total_pages: int = 0
    total_crashes: int = 0
    total_battles: int = 0


def exhaust_location(
    hwnd: int,
    out_root: Path,
    *,
    depth: int,
    max_depth: int,
    scratch_base: int,
    repeat: int,
    on_battle: str,
    visited: dict[str, LocationRecord],   # fp → LocationRecord
    location_graph: dict,
) -> LocationRecord | None:
    """Exhaust all actions at the current location, follow Move targets recursively.

    Returns the LocationRecord for the current location, or None if already visited.
    """
    img = capture_window_image(hwnd)
    state = classify_screen_state(img)
    if state != "action_menu":
        print(f"  exhaust_location: expected action_menu, got {state!r} — skipping")
        return None

    loc_fp = _location_fp(img)
    if loc_fp in visited:
        print(f"  Location {loc_fp} already visited — skipping")
        return visited[loc_fp]

    scratch_slot = scratch_base + depth
    battle_slot  = scratch_base + depth + BATTLE_SLOT_OFFSET
    # NP2 only has slots 0-9; clamp battle_slot
    battle_slot  = min(battle_slot, 9)

    loc_dir = out_root / f"loc_{loc_fp}"
    loc_dir.mkdir(parents=True, exist_ok=True)

    loc_rec = LocationRecord(
        fp=loc_fp,
        label=f"d{depth}_{loc_fp[:8]}",
        out_dir=str(loc_dir),
        depth=depth,
    )
    visited[loc_fp] = loc_rec   # register early to prevent re-entry

    print(f"\n{'  ' * depth}=== Location {loc_fp} (depth {depth}) ===")

    # Enumerate all options using explore_menu
    explore_dir = loc_dir / "explore"
    screenshot_window(hwnd, loc_dir / "location_entry.png")
    summary = explore_current_menu(hwnd, explore_dir, use_ocr=True)

    # Update loc_rec label with verb labels if available
    verbs = [a.get("verb_en") or a.get("verb_ja") or "?" for a in summary["actions"]]
    loc_rec.label = f"d{depth}_{loc_fp[:8]}_[{','.join(verbs[:3])}{'...' if len(verbs)>3 else ''}]"

    print_action_tree(summary, explore_dir)

    # Update location graph
    location_graph["nodes"][loc_fp] = {
        "fp": loc_fp,
        "label": loc_rec.label,
        "depth": depth,
        "out_dir": str(loc_dir),
        "verbs": verbs,
    }

    # Separate Move actions (may lead to new locations) from others
    move_actions = [a for a in summary["actions"] if "move" in (a.get("verb_en") or "").lower()
                    or "移動" in (a.get("verb_ja") or "")]
    other_actions = [a for a in summary["actions"] if a not in move_actions]

    # ---- Try non-Move actions first (they stay in place) ----
    for action in other_actions:
        ai = action["action_index"]
        targets = action["targets"]

        if not targets:
            # No-target action (Think etc.)
            print(f"\n{'  ' * depth}  Action {ai} ({action.get('verb_en','?')}) — no target")
            ar = exhaust_action(hwnd, action, None, loc_dir, scratch_slot, battle_slot,
                                repeat, on_battle, loc_fp)
            loc_rec.action_results.append(asdict(ar))
            loc_rec.total_pages   += ar.total_pages
            loc_rec.total_crashes += int(ar.crashed)
            loc_rec.total_battles += int(ar.battle_detected)
        else:
            for target in targets:
                ti = target["target_index"]
                tgt_label = target.get("target_en") or target.get("target_ja") or f"t{ti}"
                print(f"\n{'  ' * depth}  Action {ai} ({action.get('verb_en','?')}) → {tgt_label}")
                ar = exhaust_action(hwnd, action, target, loc_dir, scratch_slot, battle_slot,
                                    repeat, on_battle, loc_fp)
                loc_rec.action_results.append(asdict(ar))
                loc_rec.total_pages   += ar.total_pages
                loc_rec.total_crashes += int(ar.crashed)
                loc_rec.total_battles += int(ar.battle_detected)

    # ---- Follow Move actions to new locations ----
    for action in move_actions:
        ai = action["action_index"]
        for target in action["targets"]:
            ti = target["target_index"]
            tgt_label = target.get("target_en") or target.get("target_ja") or f"t{ti}"
            print(f"\n{'  ' * depth}  Move → {tgt_label}")

            # Save current state at this depth level, execute Move
            save_state_direct(hwnd, scratch_slot)
            time.sleep(0.4)

            try:
                choose_menu_target(hwnd, ai, ti)
            except Exception as exc:
                print(f"    Move choose_menu_target failed: {exc}")
                load_state_direct(hwnd, scratch_slot)
                time.sleep(0.8)
                continue

            # Advance through any transition text
            cap = advance_capturing_text(
                hwnd,
                loc_dir / f"move_a{ai:02d}_t{ti:02d}_{_safe_slug(tgt_label)}",
                "transition",
                on_battle=on_battle,
                trace_fn=lambda m: print(f"      {m}"),
            )

            img_dest = capture_window_image(hwnd)
            dest_fp = _location_fp(img_dest)

            # Record Move as an action result too
            ar = ActionResult(
                action_index=ai, target_index=ti,
                verb_ja=action.get("verb_ja",""), verb_en=action.get("verb_en","Move"),
                target_ja=target.get("target_ja",""), target_en=tgt_label,
                total_pages=len(cap.pages), total_new_pages=len(cap.pages),
                led_to_new_location=(dest_fp != loc_fp),
                new_location_fp=dest_fp if dest_fp != loc_fp else "",
                stopped_after_attempts=1,
            )
            ar.attempts.append({
                "attempt_index": 0, "page_count": len(cap.pages),
                "new_page_count": len(cap.pages), "crashed": cap.crashed,
                "battle_detected": cap.battle_detected, "final_state": cap.final_state,
                "page_fingerprints": [p.fingerprint for p in cap.pages],
                "out_dir": str(loc_dir / f"move_a{ai:02d}_t{ti:02d}_{_safe_slug(tgt_label)}"),
            })
            loc_rec.action_results.append(asdict(ar))

            # Record connection in location graph
            edge = {
                "from": loc_fp,
                "to": dest_fp,
                "action": action.get("verb_en","Move"),
                "target": tgt_label,
                "action_index": ai,
                "target_index": ti,
            }
            loc_rec.connections.append(edge)
            location_graph["edges"].append(edge)

            if dest_fp == loc_fp:
                print(f"    Move to {tgt_label}: same location (no change)")
            elif depth < max_depth and cap.final_state == "action_menu":
                print(f"    Move to {tgt_label}: new location {dest_fp} — recursing (depth {depth+1})")
                child = exhaust_location(
                    hwnd, out_root,
                    depth=depth + 1, max_depth=max_depth,
                    scratch_base=scratch_base, repeat=repeat,
                    on_battle=on_battle,
                    visited=visited, location_graph=location_graph,
                )
                if child:
                    # Propagate child's label back into graph node
                    location_graph["nodes"].setdefault(dest_fp, {})["label"] = child.label
            else:
                if depth >= max_depth:
                    print(f"    Move to {tgt_label}: max depth {max_depth} reached — not recursing")
                else:
                    print(f"    Move to {tgt_label}: final_state={cap.final_state!r} — not recursing")

            # Restore to this location
            load_state_direct(hwnd, scratch_slot)
            time.sleep(0.8)
            wait_for_content_stable(hwnd, timeout=8.0, stable_period=0.8)

    # Write per-location report
    loc_report = {
        "fp": loc_fp,
        "label": loc_rec.label,
        "depth": depth,
        "total_pages": loc_rec.total_pages,
        "total_crashes": loc_rec.total_crashes,
        "total_battles": loc_rec.total_battles,
        "connections": loc_rec.connections,
        "action_results": loc_rec.action_results,
    }
    (loc_dir / "location_report.json").write_text(
        json.dumps(loc_report, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    print(f"\n{'  ' * depth}Location {loc_fp}: "
          f"{loc_rec.total_pages} pages, "
          f"{loc_rec.total_crashes} crash(es), "
          f"{loc_rec.total_battles} battle(s)")

    return loc_rec


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------

def write_session_report(
    out_root: Path,
    visited: dict[str, LocationRecord],
    location_graph: dict,
    elapsed: float,
) -> None:
    """Write the session-level report and location graph."""
    total_pages   = sum(r.total_pages   for r in visited.values())
    total_crashes = sum(r.total_crashes for r in visited.values())
    total_battles = sum(r.total_battles for r in visited.values())

    report = {
        "locations_visited": len(visited),
        "total_pages_seen": total_pages,
        "total_crashes": total_crashes,
        "total_battles": total_battles,
        "elapsed_seconds": round(elapsed, 1),
        "locations": [
            {"fp": fp, "label": r.label, "depth": r.depth,
             "pages": r.total_pages, "crashes": r.total_crashes, "battles": r.total_battles}
            for fp, r in visited.items()
        ],
    }

    (out_root / "report.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    (out_root / "location_graph.json").write_text(
        json.dumps(location_graph, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    print("\n" + "=" * 60)
    print(f"Session complete: {len(visited)} location(s), {total_pages} page(s)")
    print(f"  Crashes: {total_crashes}   Battles: {total_battles}")
    print(f"  Elapsed: {elapsed:.0f}s")
    print(f"  Report:  {out_root / 'report.json'}")
    print(f"  Graph:   {out_root / 'location_graph.json'}")
    print("=" * 60)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Exhaustive text scanner — try every action×target at every reachable location.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    p.add_argument("--out", type=Path, required=True, help="Output root directory")
    p.add_argument("--max-depth", type=int, default=DEFAULT_MAX_DEPTH,
                   help=f"Max Move-following depth (0 = current location only, default {DEFAULT_MAX_DEPTH})")
    p.add_argument("--repeat", type=int, default=DEFAULT_REPEAT,
                   help=f"Max attempts per action×target for loop detection (default {DEFAULT_REPEAT})")
    p.add_argument("--scratch-base", type=int, default=DEFAULT_SCRATCH_BASE,
                   help=f"Base emulator save slot for scratch saves (default {DEFAULT_SCRATCH_BASE})")
    p.add_argument("--load-state", type=int, default=None,
                   help="Load emulator save state before starting (slot 0-9)")
    p.add_argument("--file-index", type=int, default=None,
                   help="Load in-game save file index after loading state (0-based)")
    p.add_argument("--emulator", type=Path, default=DEFAULT_EMULATOR_PATH,
                   help=f"Path to np2debug executable (default: {DEFAULT_EMULATOR_PATH})")
    p.add_argument("--hdi", type=Path, default=DEFAULT_HDI_PATH,
                   help=f"HDI image path (default: {DEFAULT_HDI_PATH})")
    p.add_argument("--no-launch", action="store_true",
                   help="Don't launch the emulator — attach to an already-running instance")
    p.add_argument("--on-battle", choices=["wait", "skip"], default="wait",
                   help="'wait' pauses for manual resolution, 'skip' abandons the attempt (default: wait)")
    p.add_argument("--close-existing", action="store_true",
                   help="Close any running emulator before launch")
    return p


def main() -> None:
    args = build_parser().parse_args()
    args.out.mkdir(parents=True, exist_ok=True)

    # -- Emulator setup --
    if args.no_launch:
        from experiment_emulator_route import find_emulator_windows
        windows = find_emulator_windows()
        if not windows:
            print("ERROR: no emulator window found", file=sys.stderr)
            sys.exit(1)
        hwnd = windows[0]
        print(f"Attached to existing emulator HWND=0x{hwnd:08x}")
    else:
        if args.close_existing:
            close_existing_emulator_windows()
        hdi_abs = str(args.hdi.resolve())
        process = subprocess.Popen([str(args.emulator), hdi_abs],
                                   cwd=str(args.emulator.parent))
        hwnd = find_main_window()
        print(f"Emulator PID={process.pid} HWND=0x{hwnd:08x}")

    if args.load_state is not None:
        print(f"Loading emulator state slot {args.load_state}...")
        load_state_direct(hwnd, args.load_state)
        time.sleep(2.0)

    if args.file_index is not None:
        print(f"Loading in-game save file {args.file_index}...")
        load_file_from_main_menu(hwnd, file_index=args.file_index)
        # Advance through opening text to reach action_menu
        from text_capture import advance_capturing_text as _act
        opening = _act(hwnd, args.out / "_opening", "opening",
                       on_battle=args.on_battle,
                       trace_fn=lambda m: print(f"  [opening] {m}"))
        print(f"  Opening: {len(opening.pages)} page(s), final={opening.final_state!r}")

    # Verify we're at an action_menu
    img = capture_window_image(hwnd)
    state = classify_screen_state(img)
    if state != "action_menu":
        print(f"ERROR: expected action_menu before starting, got {state!r}", file=sys.stderr)
        print("  Start the emulator at an action menu, or use --load-state / --file-index.")
        sys.exit(1)

    location_graph: dict = {"nodes": {}, "edges": []}
    visited: dict[str, LocationRecord] = {}

    t0 = time.monotonic()
    try:
        exhaust_location(
            hwnd, args.out,
            depth=0,
            max_depth=args.max_depth,
            scratch_base=args.scratch_base,
            repeat=args.repeat,
            on_battle=args.on_battle,
            visited=visited,
            location_graph=location_graph,
        )
    except KeyboardInterrupt:
        print("\nInterrupted — writing partial report...")
    finally:
        elapsed = time.monotonic() - t0
        write_session_report(args.out, visited, location_graph, elapsed)


if __name__ == "__main__":
    main()
