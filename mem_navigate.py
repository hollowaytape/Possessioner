"""mem_navigate.py — Memory-verified menu navigation for the Possessioner
walkthrough runner.

Replaces the screenshot/OCR-based approach with direct memory reads from
the emulator process via mem_bridge.  All menu navigation is driven by
reading cursor position and menu depth/count — no OCR, no screen
classification, no recovery loops.

Key insight: Possessioner dialogue is page-based.  After selecting a
verb+target, the game shows text.  If the text fits in one page, the
game returns to the verb menu (depth=0) immediately.  If there are
multiple pages, the game stays at depth=1 and the player must press
SPACE to advance through each page until depth returns to 0.

Usage:

    from mem_navigate import MemNavigator
    nav = MemNavigator(hwnd)
    nav.do_action(0, 2)       # Look at Meryl
    nav.do_action(1, 0)       # Talk to Honghua
    nav.do_action(2)          # Think (auto-confirms sub-menu)
"""

from __future__ import annotations

import time
from mem_bridge import MemBridge
from experiment_emulator_route import (
    find_main_window, post_key, VK_BY_NAME,
)


class NavigationTimeout(Exception):
    """Raised when a menu state transition doesn't happen in time."""


class MemNavigator:
    """Drive the game's menus using memory-verified cursor tracking."""

    def __init__(self, hwnd: int, bridge: MemBridge | None = None, *,
                 known_base: int | None = None,
                 key_delay: float = 0.08,
                 poll_interval: float = 0.05,
                 timeout: float = 5.0):
        self.hwnd = hwnd
        self.key_delay = key_delay
        self.poll_interval = poll_interval
        self.timeout = timeout

        if bridge is not None:
            self.bridge = bridge
        else:
            ref = open("patched/DATA1.SLD", "rb").read()
            self.bridge = MemBridge.attach(hwnd, reference_save=ref,
                                           known_base=known_base)

    def close(self):
        self.bridge.close()

    # ── Low-level helpers ────────────────────────────────────────────

    def _key(self, name: str):
        post_key(self.hwnd, VK_BY_NAME[name])
        time.sleep(self.key_delay)

    def _wait_for(self, predicate, what: str = "condition",
                  timeout: float | None = None) -> None:
        """Poll until *predicate()* returns True."""
        t0 = time.time()
        limit = timeout or self.timeout
        while time.time() - t0 < limit:
            if predicate():
                return
            time.sleep(self.poll_interval)
        raise NavigationTimeout(
            f"Timed out waiting for {what} after {limit:.1f}s "
            f"(menu_state={self.bridge.menu_state()})"
        )

    # ── State queries ────────────────────────────────────────────────

    def at_verb_menu(self) -> bool:
        return self.bridge.menu_depth() == 0 and self.bridge.menu_count() > 0

    def at_target_menu(self) -> bool:
        return self.bridge.menu_depth() == 1 and self.bridge.menu_count() > 0

    @property
    def map_byte(self) -> int:
        return self.bridge.read_map_byte()

    @property
    def cursor(self) -> int:
        return self.bridge.cursor_pos()

    @property
    def verb_count(self) -> int:
        """Number of verbs at the top-level menu."""
        return self.bridge.menu_count()

    @property
    def depth(self) -> int:
        return self.bridge.menu_depth()

    # ── Cursor navigation ────────────────────────────────────────────

    def navigate_cursor(self, target_index: int,
                        timeout: float | None = None) -> None:
        """Move the cursor to *target_index* in the current menu."""
        limit = timeout or self.timeout
        t0 = time.time()
        while time.time() - t0 < limit:
            cur = self.bridge.cursor_pos()
            if cur == target_index:
                return
            if cur < target_index:
                self._key("DOWN")
            else:
                self._key("UP")
            time.sleep(self.poll_interval)
        raise NavigationTimeout(
            f"Could not reach cursor position {target_index} "
            f"(stuck at {self.bridge.cursor_pos()})"
        )

    # ── Core action execution ────────────────────────────────────────

    def do_action(self, verb_index: int,
                  target_index: int | None = None) -> dict:
        """Execute one verb[+target] action from the verb menu.

        Protocol:
          1. At verb menu (d=0).  Navigate cursor to verb_index.
          2. SPACE → enters target sub-menu (d=1).
          3. If target_index given: navigate cursor, SPACE.
             If no target (Think-style): SPACE to confirm single item.
          4. Short dialogue (≤1 page): game returns to verb menu (d=0)
             immediately.
          5. Multi-page dialogue: game stays at d=1 while showing text.
             Press SPACE to advance through pages until d=0.

        Returns dict with map tracking and depth info.
        """
        map_before = self.map_byte
        verb_count_before = self.bridge.menu_count()

        # Step 1: ensure at verb menu, navigate to verb
        self._wait_for(self.at_verb_menu, "verb menu")
        self.navigate_cursor(verb_index)

        # Step 2: press SPACE to enter sub-menu
        self._key("SPACE")
        time.sleep(0.15)
        self._wait_for(self.at_target_menu, "target sub-menu")

        # Step 3: select target or auto-confirm
        sub_count = self.bridge.menu_count()
        if target_index is not None:
            self.navigate_cursor(target_index)
        self._key("SPACE")
        time.sleep(0.20)

        # Step 4: advance through dialogue / cutscene pages until verb
        # menu returns.  Short dialogue (≤1 page) returns d=0 instantly.
        # Multi-page dialogue needs SPACE per page.  Move cutscenes can
        # take 30+ seconds (scene loading + many dialogue pages).
        t0 = time.time()
        page_timeout = 60.0  # generous cap for long cutscenes
        while time.time() - t0 < page_timeout:
            if self.bridge.menu_depth() == 0 and self.bridge.menu_count() > 0:
                break
            self._key("SPACE")
            time.sleep(0.30)
        else:
            raise NavigationTimeout(
                f"Still at d=1 after {page_timeout:.0f}s of dialogue "
                f"advances (menu_state={self.bridge.menu_state()})"
            )

        map_after = self.map_byte
        return {
            "verb": verb_index,
            "target": target_index,
            "sub_count": sub_count,
            "map_before": f"0x{map_before:02X}",
            "map_after": f"0x{map_after:02X}",
            "scene_changed": map_before != map_after,
            "verb_count_before": verb_count_before,
            "verb_count_after": self.bridge.menu_count(),
        }

    def escape_to_verbs(self) -> None:
        """Press ESCAPE to return from target menu to verb menu."""
        if self.bridge.menu_depth() == 1:
            self._key("ESCAPE")
            self._wait_for(self.at_verb_menu, "verb menu after escape")

    # ── Walkthrough step execution ───────────────────────────────────

    def execute_step(self, verb_index: int,
                     target_index: int | None = None) -> dict:
        """Execute one walkthrough step from the verb menu.

        This is the main entry point for the walkthrough runner.
        """
        return self.do_action(verb_index, target_index)

    # ── Scene brute-force ─────────────────────────────────────────────

    def brute_force_scene(self, *, max_rounds: int = 30,
                          min_attempts: int = 2,
                          skip_verbs: set[int] | None = None,
                          verbose: bool = True) -> dict:
        """Cycle all verb+target combos until the scene changes.

        For each verb, enters the submenu to read the target count,
        then tries every target.  Repeats until the map byte changes
        or no new progress is made after *min_attempts* full rounds
        per combo.

        Parameters
        ----------
        skip_verbs : set of int, optional
            Verb indices to skip (e.g. {0} to skip Move when it's
            at the top of the menu).

        Returns dict with final map, step count, and whether the scene
        changed.
        """
        initial_map = self.map_byte
        step = 0
        skip = skip_verbs or set()
        # Track (verb, target) → attempt count
        seen: dict[tuple[int, int], int] = {}

        for rnd in range(1, max_rounds + 1):
            vc = self.bridge.menu_count()

            for vi in range(vc):
                if vi in skip:
                    continue
                # Enter verb's submenu to read target count
                self._wait_for(self.at_verb_menu, "verb menu")
                self.navigate_cursor(vi)
                self._key("SPACE")
                time.sleep(0.20)

                # Check if verb entered a submenu (d=1) or if
                # it's a direct action (d stayed 0 → CG/cutscene).
                if self.bridge.menu_depth() == 1:
                    tc = self.bridge.menu_count()
                    self._key("ESCAPE")
                    time.sleep(0.15)
                    self._wait_for(self.at_verb_menu, "verb menu after peek")
                else:
                    # Direct-action verb — no submenu.
                    # The action already executed.  Advance through any
                    # dialogue/CG pages until verb menu returns.
                    tc = 0
                    key = (vi, -1)
                    seen[key] = seen.get(key, 0) + 1
                    step += 1
                    self._advance_to_verb_menu()
                    new_map = self.map_byte
                    if verbose:
                        flag = ""
                        if new_map != initial_map:
                            flag = " *** MAP 0x%02X ***" % new_map
                        new_vc = self.bridge.menu_count()
                        if new_vc != vc:
                            flag += " VERBS(%d→%d)" % (vc, new_vc)
                        print("  R%d [%d] v=%d (direct)%s"
                              % (rnd, step, vi, flag))
                    if new_map != initial_map:
                        return {"map_before": initial_map,
                                "map_after": new_map,
                                "scene_changed": True,
                                "steps": step, "rounds": rnd}
                    vc = self.bridge.menu_count()
                    continue

                # Try each target for this verb
                for ti in range(tc):
                    key = (vi, ti)
                    seen[key] = seen.get(key, 0) + 1
                    step += 1
                    result = self.do_action(vi, ti)
                    new_map = self.map_byte
                    new_vc = self.bridge.menu_count()
                    if verbose:
                        flag = ""
                        if new_map != initial_map:
                            flag = " *** MAP 0x%02X ***" % new_map
                        if new_vc != vc:
                            flag += " VERBS(%d→%d)" % (vc, new_vc)
                        print("  R%d [%d] v=%d t=%d%s"
                              % (rnd, step, vi, ti, flag))
                    if new_map != initial_map:
                        return {"map_before": initial_map,
                                "map_after": new_map,
                                "scene_changed": True,
                                "steps": step, "rounds": rnd}
                    vc = new_vc

            # Check if all combos have been tried enough times
            if all(v >= min_attempts for v in seen.values()):
                if verbose:
                    print("  All combos tried ≥%d× — exhausted" %
                          min_attempts)
                break

        return {"map_before": initial_map,
                "map_after": self.map_byte,
                "scene_changed": self.map_byte != initial_map,
                "steps": step, "rounds": rnd}

    def _advance_to_verb_menu(self, timeout: float = 60.0):
        """Press SPACE to advance through dialogue/CGs until
        the verb menu (d=0, c>0) is reached.
        """
        t0 = time.time()
        while time.time() - t0 < timeout:
            d = self.bridge.menu_depth()
            c = self.bridge.menu_count()
            if d == 0 and c > 0:
                # Verify it's a real menu by trying to move the cursor.
                cur = self.bridge.cursor_pos()
                probe_key = "UP" if cur == c - 1 else "DOWN"
                undo_key = "DOWN" if cur == c - 1 else "UP"
                if c > 1:
                    self._key(probe_key)
                    time.sleep(0.10)
                    cur_after = self.bridge.cursor_pos()
                    if cur_after != cur:
                        # Cursor moved — real menu.  Undo the probe.
                        self._key(undo_key)
                        time.sleep(0.10)
                        return
                    # Cursor didn't move — CG with stale bytes.
                    self._key("SPACE")
                    time.sleep(0.30)
                    continue
                elif c == 1:
                    old_d, old_c = d, c
                    self._key("SPACE")
                    time.sleep(0.30)
                    if (self.bridge.menu_depth() == old_d
                            and self.bridge.menu_count() == old_c):
                        return
                    continue
            else:
                self._key("SPACE")
                time.sleep(0.30)
        raise NavigationTimeout(
            f"Could not reach verb menu after {timeout:.0f}s "
            f"(menu_state={self.bridge.menu_state()})"
        )

    # ── Convenience for the opening HQ route ─────────────────────────

    def execute_hq_opening(self, *, verbose: bool = True) -> bool:
        """Run the known HQ intro sequence (File 1 / map 0x01).

        The HQ intro requires: Look at everything x2, Talk to everyone x2,
        then Think x2, then Talk to Nedra once more.  After that, Move
        becomes available (verb count goes from 4 to 5).

        Returns True if Move became available.
        """
        LOOK, TALK, THINK = 0, 1, 2

        steps = [
            # Look at everything twice (targets: Room=0..Nedra=3)
            (LOOK, 0, "Look Room"),
            (LOOK, 1, "Look Honghua"),
            (LOOK, 2, "Look Meryl"),
            (LOOK, 3, "Look Nedra"),
            (LOOK, 0, "Look Room #2"),
            (LOOK, 1, "Look Honghua #2"),
            (LOOK, 2, "Look Meryl #2"),
            (LOOK, 3, "Look Nedra #2"),
            # Talk to everyone twice (targets: Honghua=0, Meryl=1, Nedra=2)
            (TALK, 0, "Talk Honghua"),
            (TALK, 1, "Talk Meryl"),
            (TALK, 2, "Talk Nedra"),
            (TALK, 0, "Talk Honghua #2"),
            (TALK, 1, "Talk Meryl #2"),
            (TALK, 2, "Talk Nedra #2"),
            # Think twice (no target — auto-confirms single item)
            (THINK, None, "Think"),
            (THINK, None, "Think #2"),
            # Talk to Nedra one more time
            (TALK, 2, "Talk Nedra #3"),
        ]

        for i, (verb, target, label) in enumerate(steps):
            result = self.do_action(verb, target)
            if verbose:
                sc = " ★ SCENE" if result["scene_changed"] else ""
                vc = result["verb_count_after"]
                print(f"  [{i+1:2d}/{len(steps)}] {label:22s}"
                      f"  verbs={vc}{sc}")

        final_count = self.bridge.menu_count()
        if verbose:
            print(f"\nVerb count: {final_count}"
                  f" ({'Move available!' if final_count >= 5 else 'no Move yet'})")
        return final_count >= 5


# ── CLI for testing ──────────────────────────────────────────────────

def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="Memory-verified menu navigation test"
    )
    parser.add_argument("--hq", action="store_true",
                        help="Run the HQ opening sequence")
    parser.add_argument("--verb", type=int, default=None,
                        help="Select verb at this index")
    parser.add_argument("--target", type=int, default=None,
                        help="Select target at this index")
    parser.add_argument("--status", action="store_true",
                        help="Just print current menu state")
    parser.add_argument("--base", type=lambda x: int(x, 0), default=None,
                        help="Known base address (hex)")
    args = parser.parse_args()

    hwnd = find_main_window(timeout=5.0)
    print(f"Emulator: hwnd=0x{hwnd:X}")

    nav = MemNavigator(hwnd, known_base=args.base)
    print(f"Bridge: base=0x{nav.bridge.base:X}")
    print(f"State: {nav.bridge.menu_state()}")

    if args.status:
        print(f"  at_verb={nav.at_verb_menu()}")
        print(f"  at_target={nav.at_target_menu()}")
        nav.close()
        return

    if args.hq:
        print("\nRunning HQ opening sequence...")
        nav.execute_hq_opening()
        print(f"\nFinal: {nav.bridge.menu_state()}")
        # Check if Move is now available
        cnt = nav.bridge.menu_count()
        print(f"Verb count: {cnt} (5 = Move available)")
        nav.close()
        return

    if args.verb is not None:
        result = nav.execute_step(args.verb, args.target)
        print(f"Result: {result}")
        print(f"State: {nav.bridge.menu_state()}")

    nav.close()


if __name__ == "__main__":
    main()
