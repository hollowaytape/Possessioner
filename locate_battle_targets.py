"""Interactive battle-target locator — click on a screenshot to record coordinates.

Usage
-----
1. Start np2debug with a battle screen visible (emulator save-state 1).
2. Run:  python locate_battle_targets.py
3. A window opens showing the current battle screen (chrome stripped).
4. Click each target in order as prompted in the title bar:

       C button  char1 (top-left)
       Defend    char1  (3rd option in the command menu — open C menu first in game)
       C button  char2  (bottom-left)
       Defend    char2
       C button  char3  (top-right)
       Defend    char3
       C button  char4  (bottom-right)
       Defend    char4
       FIGHT button

5. Close the window (or press Escape) when done.
6. The script prints game-space coordinates and ready-to-paste constants.

Tip: if the C-menu isn't open for Defend positions, click the C button in the
actual game first to open the menu, then run this script / re-screenshot.
"""
from __future__ import annotations

import sys
import tkinter as tk
from pathlib import Path
from typing import Optional

from PIL import Image, ImageTk

from experiment_emulator_route import (
    _WC_CHROME_LEFT,
    _WC_CHROME_TOP,
    capture_window_image,
    find_emulator_windows,
)


_LABELS = [
    ("C1",    "C button  char1 (top-left)"),
    ("D1",    "Defend    char1  — 3rd option in command menu"),
    ("C2",    "C button  char2 (bottom-left)"),
    ("D2",    "Defend    char2"),
    ("C3",    "C button  char3 (top-right)"),
    ("D3",    "Defend    char3"),
    ("C4",    "C button  char4 (bottom-right)"),
    ("D4",    "Defend    char4"),
    ("FIGHT", "FIGHT button"),
]


def _crop_game_area(img: Image.Image) -> Image.Image:
    """Strip window chrome using the same offsets as experiment_emulator_route."""
    left = _WC_CHROME_LEFT
    top  = _WC_CHROME_TOP
    right  = img.width  - _WC_CHROME_LEFT
    bottom = img.height - 4   # thin bottom border
    return img.crop((left, top, right, bottom))


def _print_constants(recorded: list[tuple[str, int, int]]) -> None:
    if not recorded:
        print("No clicks recorded.")
        return

    by_key = {k: (x, y) for k, x, y in recorded}

    print("\n" + "=" * 64)
    print("Paste into experiment_emulator_route.py:")
    print("=" * 64)
    for i in range(1, 5):
        key = f"C{i}"
        if key in by_key:
            gx, gy = by_key[key]
            print(f"_WC_C_CHAR{i} = _game_to_win({gx}, {gy})")
    for i in range(1, 5):
        key = f"D{i}"
        if key in by_key:
            gx, gy = by_key[key]
            print(f"_WC_OPT3_CHAR{i} = _game_to_win({gx}, {gy})")
    if "FIGHT" in by_key:
        gx, gy = by_key["FIGHT"]
        print(f"_WC_FIGHT = _game_to_win({gx}, {gy})")
    print("=" * 64)

    # Also derive the Defend offset relative to each C button
    offsets = []
    for i in range(1, 5):
        c = by_key.get(f"C{i}")
        d = by_key.get(f"D{i}")
        if c and d:
            offsets.append((d[0] - c[0], d[1] - c[1]))
    if offsets:
        avg_dx = sum(o[0] for o in offsets) // len(offsets)
        avg_dy = sum(o[1] for o in offsets) // len(offsets)
        print(f"\nAverage Defend offset from C button: dx={avg_dx}, dy={avg_dy}")
        print(f"  _WC_DEFEND_DX = {avg_dx}")
        print(f"  _WC_DEFEND_DY = {avg_dy}")


def main() -> None:
    windows = find_emulator_windows()
    if not windows:
        print("ERROR: no emulator window found — start np2debug first.", file=sys.stderr)
        sys.exit(1)

    hwnd = windows[0]
    print("Capturing battle screen…")
    full_img  = capture_window_image(hwnd)
    game_img  = _crop_game_area(full_img)
    game_w, game_h = game_img.size
    print(f"Game area: {game_w}×{game_h}")

    recorded: list[tuple[str, int, int]] = []

    root = tk.Tk()
    root.resizable(False, False)

    photo = ImageTk.PhotoImage(game_img)
    canvas = tk.Canvas(root, width=game_w, height=game_h, cursor="crosshair")
    canvas.pack()
    canvas.create_image(0, 0, anchor="nw", image=photo)

    dots: list[int] = []   # canvas item IDs for recorded click markers

    def update_title() -> None:
        idx = len(recorded)
        if idx < len(_LABELS):
            _, desc = _LABELS[idx]
            root.title(f"[{idx + 1}/{len(_LABELS)}]  Click: {desc}")
        else:
            root.title("Done — close window or press Escape")

    def on_click(event: tk.Event) -> None:  # type: ignore[type-arg]
        idx = len(recorded)
        if idx >= len(_LABELS):
            return
        gx, gy = event.x, event.y
        key, desc = _LABELS[idx]
        recorded.append((key, gx, gy))
        print(f"  [{idx + 1}/{len(_LABELS)}] {desc}  → game ({gx},{gy})")

        # Draw a small crosshair marker
        r = 4
        color = "#00ff00" if key.startswith("C") else ("#ff8800" if key.startswith("D") else "#ff0000")
        dots.append(canvas.create_oval(gx - r, gy - r, gx + r, gy + r, outline=color, width=2))
        dots.append(canvas.create_text(gx + 6, gy - 8, text=key, fill=color, anchor="w",
                                       font=("Courier", 8, "bold")))
        update_title()

    canvas.bind("<Button-1>", on_click)
    root.bind("<Escape>", lambda _: root.destroy())

    update_title()
    root.mainloop()

    _print_constants(recorded)


if __name__ == "__main__":
    main()
