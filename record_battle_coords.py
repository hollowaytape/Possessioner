"""Record battle-screen click coordinates for np2debug automation calibration.

Usage
-----
1. Start np2debug and load emulator save-state 1 (starts on a battle screen).
2. Run:  python record_battle_coords.py
3. Middle-click the emulator window to release np2debug's mouse capture.
4. Left-click each target in order as prompted:

       C button  char1 (top-left)
       Defend    char1  (3rd option in the command menu)
       C button  char2  (bottom-left)
       Defend    char2
       C button  char3  (top-right)
       Defend    char3
       C button  char4  (bottom-right)
       Defend    char4
       FIGHT button

5. Press Ctrl+C (or wait) — the script prints window-relative coords and
   ready-to-paste constants for experiment_emulator_route.py.

Why a low-level hook?
---------------------
np2debug locks the Windows cursor to the window centre while in mouse-capture
mode, so WM_MOUSEMOVE always reports centre coordinates.  WH_MOUSE_LL fires
at the OS level before the message reaches any window, so it captures the real
screen position of every physical click regardless of capture mode.
"""
from __future__ import annotations

import ctypes
import ctypes.wintypes
import sys
import time

import win32gui

from experiment_emulator_route import (
    _WC_CHROME_LEFT,
    _WC_CHROME_TOP,
    find_emulator_windows,
)

# ── Low-level mouse hook structures ──────────────────────────────────────────

WH_MOUSE_LL  = 14
WM_LBUTTONDOWN = 0x0201
HC_ACTION      = 0


class POINT(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]


class MSLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [
        ("pt",          POINT),
        ("mouseData",   ctypes.c_ulong),
        ("flags",       ctypes.c_ulong),
        ("time",        ctypes.c_ulong),
        ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
    ]


LowLevelMouseProc = ctypes.CFUNCTYPE(
    ctypes.c_long,
    ctypes.c_int,
    ctypes.c_uint,
    ctypes.POINTER(MSLLHOOKSTRUCT),
)

# ── Click labels ─────────────────────────────────────────────────────────────

_LABELS = [
    ("C1",     "C button  char1 (top-left)"),
    ("D1",     "Defend    char1  — 3rd option in command menu"),
    ("C2",     "C button  char2 (bottom-left)"),
    ("D2",     "Defend    char2"),
    ("C3",     "C button  char3 (top-right)"),
    ("D3",     "Defend    char3"),
    ("C4",     "C button  char4 (bottom-right)"),
    ("D4",     "Defend    char4"),
    ("FIGHT",  "FIGHT button"),
]

# ── Globals ───────────────────────────────────────────────────────────────────

_recorded:    list[tuple[str, int, int]] = []   # (key, win_x, win_y)
_hwnd:        int = 0
_hook_handle: int = 0


def _window_origin(hwnd: int) -> tuple[int, int]:
    rect = win32gui.GetWindowRect(hwnd)
    return rect[0], rect[1]


def _hook_proc(
    nCode: int,
    wParam: int,
    lParam: ctypes.POINTER(MSLLHOOKSTRUCT),  # type: ignore[type-arg]
) -> int:
    if nCode == HC_ACTION and wParam == WM_LBUTTONDOWN:
        sx, sy   = lParam.contents.pt.x, lParam.contents.pt.y
        wx0, wy0 = _window_origin(_hwnd)
        win_x, win_y = sx - wx0, sy - wy0

        idx = len(_recorded)
        if idx < len(_LABELS):
            key, desc = _LABELS[idx]
            _recorded.append((key, win_x, win_y))
            remaining = len(_LABELS) - idx - 1
            print(f"\n  [{idx + 1}/{len(_LABELS)}] {desc}")
            print(f"         screen=({sx},{sy})  window=({win_x},{win_y})"
                  f"  game≈({win_x - _WC_CHROME_LEFT},{win_y - _WC_CHROME_TOP})")
            if remaining > 0:
                next_key, next_desc = _LABELS[idx + 1]
                print(f"  Next: {next_desc}")
            else:
                print("\n  All clicks recorded — press Ctrl+C to finish.")
        else:
            print(f"  (extra click ignored: screen=({sx},{sy})  window=({win_x},{win_y}))")

    return ctypes.windll.user32.CallNextHookEx(_hook_handle, nCode, wParam, lParam)


def _print_constants() -> None:
    if not _recorded:
        print("\nNo clicks recorded.")
        return

    by_key = {key: (x, y) for key, x, y in _recorded}

    c_buttons = [by_key[k] for k in ("C1", "C2", "C3", "C4") if k in by_key]
    defends   = [by_key[k] for k in ("D1", "D2", "D3", "D4") if k in by_key]
    fight     = by_key.get("FIGHT")

    print("\n" + "=" * 64)
    print("Paste into experiment_emulator_route.py (replaces _WC_C_* etc.):")
    print("=" * 64)

    if c_buttons:
        labels = ["char1 top-left", "char2 bot-left", "char3 top-right", "char4 bot-right"]
        for i, (x, y) in enumerate(c_buttons):
            lbl = labels[i] if i < len(labels) else f"char{i+1}"
            gx, gy = x - _WC_CHROME_LEFT, y - _WC_CHROME_TOP
            print(f"_WC_C_CHAR{i+1} = ({x}, {y})  # game ({gx},{gy})")

    if defends:
        for i, (x, y) in enumerate(defends):
            gx, gy = x - _WC_CHROME_LEFT, y - _WC_CHROME_TOP
            print(f"_WC_OPT3_CHAR{i+1} = ({x}, {y})  # game ({gx},{gy})")

    if fight:
        fx, fy = fight
        gx, gy = fx - _WC_CHROME_LEFT, fy - _WC_CHROME_TOP
        print(f"_WC_FIGHT = ({fx}, {fy})  # game ({gx},{gy})")

    print("=" * 64)

    # Also show as _game_to_win() calls for easy drop-in
    print("\nOr using _game_to_win():")
    if c_buttons:
        for i, (x, y) in enumerate(c_buttons):
            gx, gy = x - _WC_CHROME_LEFT, y - _WC_CHROME_TOP
            print(f"_WC_C_CHAR{i+1} = _game_to_win({gx}, {gy})")
    if defends:
        for i, (x, y) in enumerate(defends):
            gx, gy = x - _WC_CHROME_LEFT, y - _WC_CHROME_TOP
            print(f"_WC_OPT3_CHAR{i+1} = _game_to_win({gx}, {gy})")
    if fight:
        gx, gy = fight[0] - _WC_CHROME_LEFT, fight[1] - _WC_CHROME_TOP
        print(f"_WC_FIGHT = _game_to_win({gx}, {gy})")


def main() -> None:
    global _hwnd, _hook_handle

    windows = find_emulator_windows()
    if not windows:
        print("ERROR: no emulator window found — start np2debug first.", file=sys.stderr)
        sys.exit(1)
    _hwnd = windows[0]
    title = win32gui.GetWindowText(_hwnd)
    rect  = win32gui.GetWindowRect(_hwnd)
    print(f"Found emulator: {title!r}  hwnd=0x{_hwnd:08x}")
    print(f"Window rect: left={rect[0]} top={rect[1]} right={rect[2]} bottom={rect[3]}")
    print(f"Chrome offsets in use: left={_WC_CHROME_LEFT} top={_WC_CHROME_TOP}")
    print()
    print("Steps:")
    print("  1. Make sure the battle screen is visible (load emulator save-state 1).")
    print("  2. Middle-click the emulator window to release mouse capture.")
    print("  3. Left-click each target below in order:\n")
    for i, (key, desc) in enumerate(_LABELS, 1):
        print(f"     {i:2d}. {desc}")
    print()
    print("Press Ctrl+C when done (or after all clicks are recorded).")
    print()
    print(f"  Next: {_LABELS[0][1]}")

    proc = LowLevelMouseProc(_hook_proc)

    _hook_handle = ctypes.windll.user32.SetWindowsHookExW(
        WH_MOUSE_LL,
        proc,
        None,
        0,
    )
    if not _hook_handle:
        print("ERROR: could not install mouse hook.", file=sys.stderr)
        sys.exit(1)

    msg = ctypes.wintypes.MSG()
    try:
        while len(_recorded) < len(_LABELS):
            ret = ctypes.windll.user32.GetMessageW(ctypes.byref(msg), None, 0, 0)
            if ret <= 0:
                break
            ctypes.windll.user32.TranslateMessage(ctypes.byref(msg))
            ctypes.windll.user32.DispatchMessageW(ctypes.byref(msg))
    except KeyboardInterrupt:
        pass
    finally:
        ctypes.windll.user32.UnhookWindowsHookEx(_hook_handle)
        _print_constants()


if __name__ == "__main__":
    main()
