"""
Apply cheat patches to the original ROM without touching any translation work.

Copies original/Possessioner.hdi → patched/Possessioner.hdi, then patches
POS.EXE with testing cheats:

  - Instant text display   (offset 0xa3bf → \\xa8\\x03)
  - All enemies start with 0 HP so they die in one hit
  - Skip the battle-launch calls we have verified so far
"""
from __future__ import annotations

import shutil

from cheats import apply_pos_cheats
from rominfo import ENEMY_NAME_LOCATIONS, ORIGINAL_ROM_PATH, TARGET_ROM_PATH
from romtools.disk import Disk, Gamefile

PATH_IN_DISK = "PSSR\\"


def apply_cheats() -> None:
    print(f"Copying {ORIGINAL_ROM_PATH!r} → {TARGET_ROM_PATH!r}")
    shutil.copy2(ORIGINAL_ROM_PATH, TARGET_ROM_PATH)

    target = Disk(TARGET_ROM_PATH)
    pos = Gamefile("original/POS.EXE", dest_disk=target)

    apply_pos_cheats(pos, ENEMY_NAME_LOCATIONS)

    pos.write(path_in_disk=PATH_IN_DISK)
    print(f"Done. Cheats-only ROM written to {TARGET_ROM_PATH!r}")


if __name__ == "__main__":
    apply_cheats()
