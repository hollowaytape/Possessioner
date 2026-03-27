"""run_explore.py — Flag-aware autonomous game explorer for Possessioner.

Uses ReadProcessMemory to read the game's internal flag state after
every action.  Flag changes are the primary progress signal:

  - Actions that change flags are "productive" — they advance the game.
  - Actions that don't change anything are deprioritized after one try.
  - The explorer exhausts productive actions before trying Move.
  - Scene changes (battles / H-scenes) are brute-forced through.

A persistent **knowledge cache** (exploration_cache.json) accumulates
findings across runs:
  - Which actions at each scene are productive vs dead ends
  - The scene graph (Move target → destination)
  - A known-good productive action sequence for replay

On subsequent runs, the explorer skips known dead ends and prioritizes
known productive actions, making each playthrough faster and more
targeted.

Usage:
    python run_explore.py                  # explore from File 1
    python run_explore.py --base 0xD3312A  # with known base addr
    python run_explore.py --no-cache       # ignore previous findings
"""

from __future__ import annotations

import argparse
import json
import os
import time

from mem_bridge import MemBridge, OFF_FLAGS, OFF_FLAGS_END, OFF_STATS
from mem_navigate import MemNavigator, NavigationTimeout
from experiment_emulator_route import (
    find_main_window, post_key, VK_BY_NAME,
    load_state_direct, capture_window_image,
)

CACHE_PATH = os.path.join(os.path.dirname(__file__), "exploration_cache.json")

# ── Configuration ────────────────────────────────────────────────────

MAX_TRIES_NO_CHANGE = 2    # skip after N tries with no flag change
MAX_TRIES_WITH_CHANGE = 5  # retry productive actions up to N times
MAX_ROUNDS_STUCK = 5       # declare exhausted after N fruitless rounds


# ── State snapshot ───────────────────────────────────────────────────

class GameState:
    """Immutable snapshot of the game's progression-relevant state."""

    __slots__ = ("map_byte", "flags", "stats")

    def __init__(self, bridge: MemBridge):
        self.map_byte = bridge.read_map_byte()
        self.flags = bridge.read_flags()        # 256 bytes
        self.stats = bridge.read_bytes(OFF_STATS, 0x26)  # 38 bytes

    def flag_diff(self, other: "GameState") -> list[dict]:
        """Return per-byte flag changes between self (before) and
        other (after)."""
        changes = []
        for i in range(len(self.flags)):
            if self.flags[i] != other.flags[i]:
                old, new = self.flags[i], other.flags[i]
                bits_set = []
                bits_cleared = []
                for bit in range(8):
                    ob = (old >> bit) & 1
                    nb = (new >> bit) & 1
                    if ob != nb:
                        if nb:
                            bits_set.append(bit)
                        else:
                            bits_cleared.append(bit)
                changes.append({
                    "offset": f"0x{i:02X}",
                    "old": f"0x{old:02X}",
                    "new": f"0x{new:02X}",
                    "bits_set": bits_set,
                    "bits_cleared": bits_cleared,
                })
        return changes

    def stat_diff(self, other: "GameState") -> list[dict]:
        """Return stat block changes."""
        changes = []
        for i in range(len(self.stats)):
            if self.stats[i] != other.stats[i]:
                changes.append({
                    "stat_offset": f"0x{OFF_STATS + i:03X}",
                    "old": self.stats[i],
                    "new": other.stats[i],
                })
        return changes

    @property
    def flag_count(self) -> int:
        """Total number of set flag bits."""
        return sum(bin(b).count("1") for b in self.flags)


# ── Persistent knowledge cache ───────────────────────────────────────

class KnowledgeCache:
    """Accumulates exploration knowledge across runs.

    Stores per-scene action outcomes, the scene graph, and the ordered
    sequence of productive actions.  Loaded at startup and saved after
    each run so subsequent playthroughs skip known dead ends.
    """

    def __init__(self, path: str = CACHE_PATH):
        self.path = path
        # scene_key → action_key → ActionKnowledge
        self.scenes: dict[str, dict[str, dict]] = {}
        # scene_key → {move_target → destination scene_key}
        self.scene_graph: dict[str, dict[str, str]] = {}
        # Ordered list of productive actions across all runs
        self.productive_sequence: list[dict] = []
        self._load()

    def _load(self):
        if not os.path.exists(self.path):
            return
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                data = json.load(f)
            self.scenes = data.get("scenes", {})
            self.scene_graph = data.get("scene_graph", {})
            self.productive_sequence = data.get(
                "productive_sequence", [])
        except (json.JSONDecodeError, KeyError):
            pass

    def save(self):
        data = {
            "scenes": self.scenes,
            "scene_graph": self.scene_graph,
            "productive_sequence": self.productive_sequence,
            "updated": time.strftime("%Y-%m-%dT%H:%M:%S"),
        }
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    @staticmethod
    def _scene_key(map_byte: int) -> str:
        return f"0x{map_byte:02X}"

    @staticmethod
    def _action_key(verb: int, target: int) -> str:
        return f"{verb},{target}"

    # ── Queries ─────────────────────────────────────────────────

    def is_known_dead_end(self, map_byte: int,
                          verb: int, target: int) -> bool:
        """True if prior runs tried this action and it never changed
        any flags."""
        sk = self._scene_key(map_byte)
        ak = self._action_key(verb, target)
        info = self.scenes.get(sk, {}).get(ak)
        if info is None:
            return False
        return (info.get("attempts", 0) >= MAX_TRIES_NO_CHANGE
                and not info.get("ever_productive", False))

    def is_known_productive(self, map_byte: int,
                            verb: int, target: int) -> bool:
        """True if prior runs saw this action change flags."""
        sk = self._scene_key(map_byte)
        ak = self._action_key(verb, target)
        info = self.scenes.get(sk, {}).get(ak)
        if info is None:
            return False
        return info.get("ever_productive", False)

    def is_known_scene_changer(self, map_byte: int,
                               verb: int, target: int) -> bool:
        """True if prior runs saw this action change the map."""
        sk = self._scene_key(map_byte)
        ak = self._action_key(verb, target)
        info = self.scenes.get(sk, {}).get(ak)
        if info is None:
            return False
        return info.get("caused_scene_change", False)

    def known_move_destination(self, map_byte: int,
                               move_target: int) -> str | None:
        """Return the destination scene key if we've seen this Move
        target before, else None."""
        sk = self._scene_key(map_byte)
        return (self.scene_graph.get(sk, {})
                .get(str(move_target)))

    def get_productive_at(self, map_byte: int
                          ) -> list[tuple[int, int]]:
        """Return (verb, target) pairs known to be productive at this
        scene, in the order they were first discovered."""
        sk = self._scene_key(map_byte)
        scene_data = self.scenes.get(sk, {})
        results = []
        for ak, info in scene_data.items():
            if info.get("ever_productive"):
                parts = ak.split(",")
                results.append((int(parts[0]), int(parts[1])))
        return results

    # ── Updates ─────────────────────────────────────────────────

    def record_action(self, map_byte: int, verb: int, target: int,
                      productive: bool, flag_offsets: list[str],
                      scene_changed: bool = False):
        sk = self._scene_key(map_byte)
        ak = self._action_key(verb, target)
        if sk not in self.scenes:
            self.scenes[sk] = {}
        if ak not in self.scenes[sk]:
            self.scenes[sk][ak] = {
                "attempts": 0,
                "productive_count": 0,
                "ever_productive": False,
                "flag_offsets": [],
                "caused_scene_change": False,
            }
        info = self.scenes[sk][ak]
        info["attempts"] = info.get("attempts", 0) + 1
        if productive:
            info["productive_count"] = (
                info.get("productive_count", 0) + 1)
            info["ever_productive"] = True
            existing = set(info.get("flag_offsets", []))
            existing.update(flag_offsets)
            info["flag_offsets"] = sorted(existing)
        if scene_changed:
            info["caused_scene_change"] = True

    def record_move(self, from_map: int, move_target: int,
                    to_map: int):
        sk = self._scene_key(from_map)
        if sk not in self.scene_graph:
            self.scene_graph[sk] = {}
        self.scene_graph[sk][str(move_target)] = (
            self._scene_key(to_map))

    def record_productive_step(self, map_byte: int, verb: int,
                               target: int | None,
                               flag_diffs: list[dict]):
        """Append to the canonical productive sequence if this exact
        step isn't already recorded."""
        entry = {
            "map": f"0x{map_byte:02X}",
            "verb": verb,
            "target": target,
            "flags": [d["offset"] for d in flag_diffs],
        }
        # Avoid duplicates (same map+verb+target already in sequence)
        for existing in self.productive_sequence:
            if (existing["map"] == entry["map"]
                    and existing["verb"] == entry["verb"]
                    and existing["target"] == entry["target"]):
                # Update flag info if new flags found
                merged = set(existing["flags"]) | set(entry["flags"])
                existing["flags"] = sorted(merged)
                return
        self.productive_sequence.append(entry)


# ── Game startup ─────────────────────────────────────────────────────

def start_game(hwnd: int, nav: MemNavigator,
               load_state: int = 0, file_index: int = 0):
    """Load emulator state, pick save file, wait for verb menu."""
    load_state_direct(hwnd, slot=load_state)
    time.sleep(2)
    post_key(hwnd, VK_BY_NAME['DOWN']); time.sleep(0.3)
    post_key(hwnd, VK_BY_NAME['ENTER']); time.sleep(2)
    for _ in range(file_index + 1):
        post_key(hwnd, VK_BY_NAME['DOWN']); time.sleep(0.2)
    post_key(hwnd, VK_BY_NAME['ENTER'])
    nav._advance_to_verb_menu(timeout=30.0)


# ── Action outcome tracking ─────────────────────────────────────────

class ActionRecord:
    """Tracks attempts and outcomes for one (verb, target) combo
    at one scene."""

    __slots__ = ("verb", "target", "attempts", "flag_changes",
                 "ever_productive", "caused_scene_change",
                 "last_total_change")

    def __init__(self, verb: int, target: int):
        self.verb = verb
        self.target = target
        self.attempts = 0
        self.flag_changes = 0   # how many attempts changed flags
        self.ever_productive = False
        self.caused_scene_change = False  # action sent us to another map
        self.last_total_change = 0  # +N or -N total flag change last time

    @property
    def max_tries(self) -> int:
        if self.ever_productive:
            return MAX_TRIES_WITH_CHANGE
        return MAX_TRIES_NO_CHANGE

    @property
    def should_try(self) -> bool:
        return self.attempts < self.max_tries


# ── Scene tracking ───────────────────────────────────────────────────

class SceneTracker:
    """Tracks all exploration state for one map byte."""

    def __init__(self, map_byte: int):
        self.map_byte = map_byte
        self.actions: dict[tuple[int, int], ActionRecord] = {}
        self.move_targets_tried: set[int] = set()
        self.exhausted = False
        self.visit_count = 0

    def get_action(self, verb: int, target: int) -> ActionRecord:
        key = (verb, target)
        if key not in self.actions:
            self.actions[key] = ActionRecord(verb, target)
        return self.actions[key]


# ── Explorer ─────────────────────────────────────────────────────────

class GameExplorer:
    """Flag-aware autonomous game explorer."""

    def __init__(self, nav: MemNavigator, *,
                 verbose: bool = True,
                 screenshot_dir: str | None = None,
                 cache: KnowledgeCache | None = None):
        self.nav = nav
        self.bridge = nav.bridge
        self.verbose = verbose
        self.screenshot_dir = screenshot_dir
        self.cache = cache or KnowledgeCache()
        self.log: list[dict] = []
        self.step = 0
        self.scenes: dict[int, SceneTracker] = {}
        self.total_flags_set = 0

        if screenshot_dir:
            os.makedirs(screenshot_dir, exist_ok=True)

    def scene_for(self, map_byte: int) -> SceneTracker:
        if map_byte not in self.scenes:
            self.scenes[map_byte] = SceneTracker(map_byte)
        return self.scenes[map_byte]

    # ── Logging ─────────────────────────────────────────────────

    def record(self, action_type: str, verb: int, target: int | None,
               state_before: GameState, state_after: GameState,
               **extra) -> dict:
        self.step += 1
        flag_diffs = state_before.flag_diff(state_after)
        stat_diffs = state_before.stat_diff(state_after)
        entry = {
            "step": self.step,
            "type": action_type,
            "verb": verb,
            "target": target,
            "map_before": f"0x{state_before.map_byte:02X}",
            "map_after": f"0x{state_after.map_byte:02X}",
            "scene_changed": state_before.map_byte != state_after.map_byte,
            "flags_changed": len(flag_diffs),
            "flag_diffs": flag_diffs,
            "stat_diffs": stat_diffs if stat_diffs else None,
            "total_flags": state_after.flag_count,
            **extra,
        }
        self.log.append(entry)
        self.total_flags_set = state_after.flag_count

        # Update knowledge cache
        productive = len(flag_diffs) > 0
        flag_offsets = [d["offset"] for d in flag_diffs]
        self.cache.record_action(
            state_before.map_byte,
            verb, target if target is not None else -1,
            productive, flag_offsets,
            scene_changed=entry["scene_changed"])
        if productive:
            self.cache.record_productive_step(
                state_before.map_byte, verb, target, flag_diffs)
        if entry["scene_changed"] and action_type == "move":
            self.cache.record_move(
                state_before.map_byte,
                target if target is not None else 0,
                state_after.map_byte)

        if self.screenshot_dir and entry["scene_changed"]:
            try:
                img = capture_window_image(self.nav.hwnd)
                path = os.path.join(
                    self.screenshot_dir,
                    f"step{self.step:04d}_0x{state_after.map_byte:02X}.png")
                img.save(path)
            except Exception:
                pass
        return entry

    # ── Verb peeking ────────────────────────────────────────────

    def peek_verb(self, verb_index: int) -> tuple[bool, int]:
        """Peek at verb: returns (has_submenu, target_count).
        If submenu, backs out.  If direct-action, caller handles."""
        nav = self.nav
        b = self.bridge
        nav._wait_for(nav.at_verb_menu, "verb menu for peek")
        nav.navigate_cursor(verb_index)
        nav._key("SPACE")
        time.sleep(0.20)
        if b.menu_depth() == 1:
            tc = b.menu_count()
            nav._key("ESCAPE")
            time.sleep(0.15)
            nav._wait_for(nav.at_verb_menu, "verb menu after peek")
            return True, tc
        else:
            return False, 0

    # ── Execute and measure ─────────────────────────────────────

    def do_measured_action(self, verb: int, target: int,
                           action_type: str = "action") -> dict | None:
        """Execute one action, measure flag changes, return log entry.
        target == -1 means direct-action verb (already triggered by
        peek)."""
        nav = self.nav
        state_before = GameState(self.bridge)
        try:
            if target == -1:
                nav._advance_to_verb_menu()
            else:
                nav.do_action(verb, target)
        except NavigationTimeout as e:
            if self.verbose:
                print(f"    TIMEOUT v={verb} t={target}: {e}")
            try:
                nav._advance_to_verb_menu(timeout=30)
            except NavigationTimeout:
                pass
            return None

        state_after = GameState(self.bridge)
        return self.record(action_type, verb,
                           target if target >= 0 else None,
                           state_before, state_after)

    # ── Move probe (interleaved between local rounds) ──────────

    def _try_move_between_rounds(self, scene: SceneTracker) -> bool:
        """Try all Move targets once.  Called between local action
        rounds to catch flag-gated Move that becomes available only
        after enough Talk/Look cycles.  Returns True if map changed."""
        nav = self.nav
        b = self.bridge

        is_sub, move_tc = self.peek_verb(0)
        if not is_sub:
            # Move was a direct action (unusual) — it already fired.
            nav._advance_to_verb_menu()
            return nav.map_byte != scene.map_byte

        for mt in range(move_tc):
            entry = self.do_measured_action(0, mt, "move")
            if entry is None:
                continue
            vc = b.menu_count()
            self._print_entry(entry, vc,
                              label=f"Move t={mt} (probe)")
            if entry["scene_changed"]:
                scene.move_targets_tried.add(mt)
                return True
        return False

    # ── Phase 1: Exhaust non-Move local actions ─────────────────

    def exhaust_local(self, scene: SceneTracker) -> bool:
        """Try all non-Move verb+target combos, prioritizing actions
        that change flags.  Uses the knowledge cache to skip known dead
        ends and front-load known productive actions.
        Returns True if map changed."""
        nav = self.nav
        b = self.bridge
        cache = self.cache
        cur_map = scene.map_byte
        rounds_stuck = 0
        # Track which flag bits have EVER been set across all rounds.
        # New bits appearing = real progress even if totals oscillate.
        gs = GameState(b)
        bits_ever_seen = set()
        for i, byte_val in enumerate(gs.flags):
            for bit in range(8):
                if byte_val & (1 << bit):
                    bits_ever_seen.add((i, bit))

        while self.step < 5000:
            did_something_new = False
            vc = b.menu_count()
            has_move = vc >= 5

            # Build the todo list by peeking at each verb
            todo: list[tuple[int, int]] = []  # (verb, target)

            for vi in range(vc):
                if has_move and vi == 0:
                    continue

                is_sub, tc = self.peek_verb(vi)

                if not is_sub:
                    # Direct action already fired by peek
                    rec = scene.get_action(vi, -1)
                    cached_dead = cache.is_known_dead_end(
                        cur_map, vi, -1)
                    if rec.should_try and not cached_dead:
                        rec.attempts += 1
                        entry = self.do_measured_action(vi, -1, "direct")
                        if entry is not None:
                            productive = entry["flags_changed"] > 0
                            if productive:
                                rec.flag_changes += 1
                                rec.ever_productive = True
                                did_something_new = True
                            self._print_entry(entry, vc)
                            if entry["scene_changed"]:
                                rec.caused_scene_change = True
                                return True
                            if b.menu_count() != vc:
                                did_something_new = True
                                break
                    else:
                        nav._advance_to_verb_menu()
                    continue

                for ti in range(tc):
                    rec = scene.get_action(vi, ti)
                    cached_dead = cache.is_known_dead_end(
                        cur_map, vi, ti)
                    if rec.should_try and not cached_dead:
                        todo.append((vi, ti))

            # Sort: cache-known productive first, then this-run
            # productive, then untried, then by attempt count.
            # Actions that previously caused scene changes go last
            # (they'll send us elsewhere before trying other targets).
            # Actions that decrease total flags are also deprioritized
            # to avoid clearing flags needed for progression.
            def priority(item):
                v, t = item
                rec = scene.get_action(v, t)
                cached_prod = cache.is_known_productive(
                    cur_map, v, t)
                is_scene_changer = (
                    rec.caused_scene_change
                    or cache.is_known_scene_changer(cur_map, v, t))
                is_decreaser = rec.last_total_change < 0
                return (
                    3 if is_scene_changer else
                    2 if is_decreaser else
                    0,
                    0 if cached_prod else
                    1 if rec.ever_productive else
                    2,
                    rec.attempts,
                )
            todo.sort(key=priority)

            for vi, ti in todo:
                rec = scene.get_action(vi, ti)
                rec.attempts += 1
                before_total = self.total_flags_set
                entry = self.do_measured_action(vi, ti)
                if entry is None:
                    continue

                productive = entry["flags_changed"] > 0
                if productive:
                    rec.flag_changes += 1
                    rec.ever_productive = True
                    did_something_new = True
                rec.last_total_change = (
                    self.total_flags_set - before_total)

                self._print_entry(entry, vc)

                if entry["scene_changed"]:
                    rec.caused_scene_change = True
                    return True
                new_vc = b.menu_count()
                if new_vc != vc:
                    did_something_new = True
                    break

                if nav.map_byte != cur_map:
                    return True

            if nav.map_byte != cur_map:
                return True

            # Interleave: try Move after each round of local actions.
            # Some scenes gate Move behind an internal counter that
            # increments with each Talk/Look, not just flag bits.
            vc_now = b.menu_count()
            if vc_now >= 5:
                if self._try_move_between_rounds(scene):
                    return True

            if not did_something_new:
                rounds_stuck += 1
                if rounds_stuck >= MAX_ROUNDS_STUCK:
                    scene.exhausted = True
                    if self.verbose:
                        print(f"  ✓ Local actions exhausted"
                              f" (flags={self.total_flags_set})")
                    self._maximize_flags(scene)
                    return False
            else:
                # Check for NEW flag bits (not just total count).
                # Oscillating flags toggle the same bits, but real
                # progress adds bits never seen before.
                gs_now = GameState(b)
                new_bits = set()
                for i, byte_val in enumerate(gs_now.flags):
                    for bit in range(8):
                        if byte_val & (1 << bit):
                            key = (i, bit)
                            if key not in bits_ever_seen:
                                new_bits.add(key)
                                bits_ever_seen.add(key)

                if new_bits:
                    # Genuinely new flag bits — real progress
                    rounds_stuck = 0
                else:
                    # Flags changed but no new bits appeared —
                    # pure oscillation of existing bits.
                    rounds_stuck += 1
                    if rounds_stuck >= MAX_ROUNDS_STUCK:
                        scene.exhausted = True
                        if self.verbose:
                            print(f"  ✓ Local actions exhausted"
                                  f" (flags oscillating at"
                                  f" {self.total_flags_set})")
                        self._maximize_flags(scene)
                        return False

        return False

    def _maximize_flags(self, scene: SceneTracker):
        """After oscillation, re-execute all productive non-Move
        actions once more.  Since oscillation alternates between
        high and low states, one additional round from the current
        low state should restore the peak flag values, allowing
        flag-gated Move targets to work."""
        nav = self.nav
        b = self.bridge
        vc = b.menu_count()
        has_move = vc >= 5

        # Collect all productive non-Move, non-scene-changing actions
        targets = []
        for key, rec in scene.actions.items():
            vi, ti = key
            if has_move and vi == 0:
                continue
            if rec.ever_productive and not rec.caused_scene_change:
                targets.append((vi, ti))

        if not targets:
            return

        targets.sort()  # deterministic order
        if self.verbose:
            print(f"  ↑ Maximizing flags ({len(targets)} actions)...")

        for vi, ti in targets:
            entry = self.do_measured_action(
                vi, ti if ti >= 0 else -1)
            if entry is None:
                continue
            self._print_entry(entry, vc)
            if entry.get("scene_changed"):
                break
            if nav.map_byte != scene.map_byte:
                break

    # ── Phase 2: Try Move targets ───────────────────────────────

    def try_move(self, scene: SceneTracker) -> bool:
        """Try Move targets in order, preferring targets that lead to
        unvisited scenes (from the knowledge cache).
        Returns True if moved."""
        nav = self.nav
        b = self.bridge
        cache = self.cache
        cur_map = scene.map_byte

        is_sub, move_tc = self.peek_verb(0)
        if not is_sub:
            nav._advance_to_verb_menu()
            if self.verbose:
                print(f"  No Move verb (verb 0 is direct).")
            return False

        # Build candidate list: untried targets first, then targets
        # whose destinations still have unexplored actions
        candidates = []
        retry_candidates = []
        for mt in range(move_tc):
            if mt not in scene.move_targets_tried:
                candidates.append(mt)
            else:
                # Allow retrying if destination has untried actions
                dest = cache.known_move_destination(cur_map, mt)
                if dest is not None:
                    dest_int = int(dest, 16)
                    dest_scene = self.scenes.get(dest_int)
                    if dest_scene and not dest_scene.exhausted:
                        retry_candidates.append(mt)
        if not candidates and not retry_candidates:
            return False

        # Prefer Move targets whose destination we haven't visited
        # this run, or that we've never seen before
        def move_priority(mt):
            dest = cache.known_move_destination(cur_map, mt)
            if dest is None:
                return 0  # unknown destination — highest priority
            dest_int = int(dest, 16)
            if dest_int not in self.scenes:
                return 1  # known dest but not visited this run
            return 2  # already visited this run
        all_candidates = candidates + retry_candidates
        all_candidates.sort(key=move_priority)

        for mt in all_candidates:
            scene.move_targets_tried.add(mt)

            entry = self.do_measured_action(0, mt, "move")
            if entry is None:
                continue

            self._print_entry(entry, b.menu_count(),
                              label=f"Move t={mt}")

            if entry["scene_changed"]:
                # Move led to a new scene — don't brute-force,
                # just let the main loop handle the new scene.
                return True
            else:
                if entry["flags_changed"] > 0:
                    scene.exhausted = False

        return False

    # ── Scene-change handler ────────────────────────────────────

    def _handle_hscene(self):
        """Brute-force through an H-scene or battle aftermath.
        Called when we arrive at a scene with vc <= 3 after a non-Move
        action triggered a scene change."""
        nav = self.nav
        b = self.bridge
        new_map = nav.map_byte

        vc = b.menu_count()
        gs = GameState(b)
        if self.verbose:
            print(f"       → Scene 0x{new_map:02X} vc={vc}"
                  f" flags={gs.flag_count},"
                  f" brute-forcing...")
        try:
            bf = nav.brute_force_scene(
                verbose=self.verbose, min_attempts=3)
            if self.verbose:
                print(f"       → Done: {bf['steps']} steps,"
                      f" now 0x{nav.map_byte:02X}")
            nav._advance_to_verb_menu(timeout=60)
        except NavigationTimeout as e:
            if self.verbose:
                print(f"       → Brute-force timeout: {e}")

    # ── Output ──────────────────────────────────────────────────

    def _print_entry(self, entry: dict, prev_vc: int,
                     label: str | None = None):
        if not self.verbose:
            return
        v, t = entry["verb"], entry["target"]
        if label is None:
            label = (f"v={v} (direct)" if t is None
                     else f"v={v} t={t}")
        flags = ""
        if entry["scene_changed"]:
            flags += f" ★ MAP {entry['map_after']}"
        nf = entry["flags_changed"]
        if nf > 0:
            flags += f" 🏁{nf} flags"
            for fd in entry["flag_diffs"]:
                flags += f" [{fd['offset']}]"
        new_vc = self.bridge.menu_count()
        if new_vc != prev_vc:
            flags += f" vc:{prev_vc}→{new_vc}"
        marker = "+" if nf > 0 else " "
        print(f"  {marker}{self.step:03d} {label}{flags}"
              f"  (total={self.total_flags_set})")

    # ── Main loop ───────────────────────────────────────────────

    def run(self, max_steps: int = 5000) -> list[dict]:
        nav = self.nav
        b = self.bridge

        initial_state = GameState(b)
        self.total_flags_set = initial_state.flag_count
        if self.verbose:
            print(f"Initial flags set: {initial_state.flag_count}")
            cached_scenes = len(self.cache.scenes)
            cached_edges = sum(
                len(v) for v in self.cache.scene_graph.values())
            cached_prod = len(self.cache.productive_sequence)
            if cached_scenes:
                print(f"Cache: {cached_scenes} scenes,"
                      f" {cached_edges} edges,"
                      f" {cached_prod} productive actions")

        while self.step < max_steps:
            cur_map = nav.map_byte
            vc = b.menu_count()
            scene = self.scene_for(cur_map)
            scene.visit_count += 1
            gs = GameState(b)

            if self.verbose:
                print(f"\n{'─'*60}")
                cached_info = ""
                sk = KnowledgeCache._scene_key(cur_map)
                if sk in self.cache.scenes:
                    n_known = len(self.cache.scenes[sk])
                    n_prod = sum(
                        1 for v in self.cache.scenes[sk].values()
                        if v.get("ever_productive"))
                    cached_info = (f"  [cache: {n_known} actions,"
                                   f" {n_prod} productive]")
                print(f"Scene 0x{cur_map:02X}  vc={vc}  "
                      f"visit #{scene.visit_count}  "
                      f"flags={gs.flag_count}  "
                      f"(step {self.step}){cached_info}")

            # Phase 1: exhaust local non-Move actions
            if not scene.exhausted:
                if self.exhaust_local(scene):
                    # Non-Move action triggered a scene change.
                    # Ensure we're at verb menu of new scene.
                    try:
                        nav._advance_to_verb_menu(timeout=60)
                    except NavigationTimeout:
                        if self.verbose:
                            print(f"  Timeout after scene change")
                        break
                    new_vc = b.menu_count()
                    if new_vc <= 3:
                        # Low verb count — H-scene/battle aftermath.
                        self._handle_hscene()
                    continue

            # Phase 2: try Move targets (only when vc >= 5 = has Move)
            vc = b.menu_count()
            if vc < 2:
                if self.verbose:
                    print(f"  No verbs — stuck.")
                break

            has_move = vc >= 5
            if has_move and self.try_move(scene):
                continue

            # If Move didn't work and flags were oscillating,
            # try maximizing flags and retrying Move.
            if scene.exhausted and has_move:
                for _ in range(2):
                    self._maximize_flags(scene)
                    if nav.map_byte != scene.map_byte:
                        break
                    scene.move_targets_tried.clear()
                    if self.try_move(scene):
                        break
                if nav.map_byte != scene.map_byte:
                    continue

            # All Move targets tried (or no Move verb).
            # Retry locals if they might have been unlocked.
            if not scene.exhausted:
                if self.verbose:
                    print(f"  Retrying local actions after Move...")
                if self.exhaust_local(scene):
                    try:
                        nav._advance_to_verb_menu(timeout=60)
                    except NavigationTimeout:
                        break
                    new_vc = b.menu_count()
                    if new_vc <= 3:
                        self._handle_hscene()
                    continue
                if has_move and self.try_move(scene):
                    continue

            if self.verbose:
                print(f"  Scene fully explored.")
            break

        # Save updated cache
        self.cache.save()

        if self.verbose:
            gs = GameState(b)
            print(f"\n{'='*60}")
            print(f"Exploration complete: {self.step} steps")
            visited = sorted(f"0x{k:02X}" for k in self.scenes)
            print(f"Scenes visited: {visited}")
            print(f"Final: map=0x{nav.map_byte:02X}"
                  f"  flags={gs.flag_count}")
            print(f"Cache saved: {len(self.cache.scenes)} scenes,"
                  f" {len(self.cache.productive_sequence)}"
                  f" productive actions")

            # Summary of productive actions
            productive = [e for e in self.log
                          if e.get("flags_changed", 0) > 0]
            if productive:
                print(f"\nProductive actions ({len(productive)}"
                      f"/{len(self.log)}):")
                for e in productive:
                    diffs = " ".join(
                        f"{d['offset']}:{d['old']}→{d['new']}"
                        for d in e["flag_diffs"])
                    print(f"  #{e['step']:03d} {e['type']}"
                          f" v={e['verb']} t={e['target']}"
                          f" @ {e['map_before']} → {diffs}")

        return self.log


# ── CLI entry point ──────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Flag-aware autonomous Possessioner explorer"
    )
    parser.add_argument("--load-state", type=int, default=0,
                        help="Emulator save-state slot (default: 0)")
    parser.add_argument("--file-index", type=int, default=0,
                        help="In-game file index (default: 0)")
    parser.add_argument("--base", type=lambda x: int(x, 0), default=None,
                        help="Known MemBridge base address (hex)")
    parser.add_argument("--screenshots", default=None,
                        help="Directory for scene-change screenshots")
    parser.add_argument("--max-steps", type=int, default=5000,
                        help="Maximum total steps")
    parser.add_argument("--log", default="exploration_log.json",
                        help="Output log file")
    parser.add_argument("--no-cache", action="store_true",
                        help="Ignore previous exploration cache")
    parser.add_argument("--cache-file", default=CACHE_PATH,
                        help=f"Cache file path (default: {CACHE_PATH})")
    parser.add_argument("-q", "--quiet", action="store_true",
                        help="Suppress per-step output")
    args = parser.parse_args()

    hwnd = find_main_window(timeout=5.0)
    print(f"Emulator: hwnd=0x{hwnd:X}")

    nav = MemNavigator(hwnd, known_base=args.base)
    b = nav.bridge
    print(f"Bridge: base=0x{b.base:X}")

    # Load or create knowledge cache
    if args.no_cache:
        cache = KnowledgeCache.__new__(KnowledgeCache)
        cache.path = args.cache_file
        cache.scenes = {}
        cache.scene_graph = {}
        cache.productive_sequence = []
    else:
        cache = KnowledgeCache(args.cache_file)

    start_game(hwnd, nav, args.load_state, args.file_index)
    print(f"Game ready: {b.menu_state()}")

    explorer = GameExplorer(nav, verbose=not args.quiet,
                            screenshot_dir=args.screenshots,
                            cache=cache)
    t0 = time.time()
    log = explorer.run(max_steps=args.max_steps)
    elapsed = time.time() - t0
    print(f"\nTotal time: {elapsed:.0f}s")

    with open(args.log, "w", encoding="utf-8") as f:
        json.dump(log, f, indent=2, ensure_ascii=False)
    print(f"Log saved to {args.log} ({len(log)} entries)")

    nav.close()


if __name__ == "__main__":
    main()
