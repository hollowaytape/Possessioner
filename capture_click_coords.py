from __future__ import annotations

import argparse
import ctypes
import time

import win32con
import win32gui

from experiment_emulator_route import find_main_window

_VK_BY_LABEL = {
    "left": win32con.VK_LBUTTON,
    "right": win32con.VK_RBUTTON,
    "middle": win32con.VK_MBUTTON,
}


class POINT(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]


def cursor_pos() -> tuple[int, int]:
    point = POINT()
    if not ctypes.windll.user32.GetCursorPos(ctypes.byref(point)):
        raise OSError("GetCursorPos failed")
    return int(point.x), int(point.y)


def button_down(vk: int) -> bool:
    return bool(ctypes.windll.user32.GetAsyncKeyState(vk) & 0x8000)


def main() -> None:
    parser = argparse.ArgumentParser(description="Print emulator-relative mouse coordinates as you click.")
    parser.add_argument("--chrome-left", type=int, default=4, help="Window chrome width at the left edge")
    parser.add_argument("--chrome-top", type=int, default=60, help="Window chrome height above the 640x400 game area")
    parser.add_argument("--poll", type=float, default=0.01, help="Polling interval in seconds")
    args = parser.parse_args()

    hwnd = find_main_window()
    title = win32gui.GetWindowText(hwnd).strip()
    left, top, right, bottom = win32gui.GetWindowRect(hwnd)

    print(f"Tracking clicks for HWND=0x{hwnd:08x}  title={title!r}")
    print(f"Window rect: left={left} top={top} right={right} bottom={bottom}")
    print(f"Game offset: chrome_left={args.chrome_left} chrome_top={args.chrome_top}")
    print("Click inside the emulator window. Press Ctrl+C to stop.\n")

    previous = {label: False for label in _VK_BY_LABEL}
    while True:
        left, top, right, bottom = win32gui.GetWindowRect(hwnd)
        mx, my = cursor_pos()
        in_window = left <= mx < right and top <= my < bottom

        for label, vk in _VK_BY_LABEL.items():
            current = button_down(vk)
            if current and not previous[label]:
                win_x = mx - left
                win_y = my - top
                game_x = win_x - args.chrome_left
                game_y = win_y - args.chrome_top
                location = "inside" if in_window else "outside"
                print(
                    f"{label.upper():6s} abs=({mx:4d},{my:4d}) "
                    f"win=({win_x:3d},{win_y:3d}) "
                    f"game=({game_x:3d},{game_y:3d}) "
                    f"[{location}]"
                )
            previous[label] = current

        time.sleep(args.poll)


if __name__ == "__main__":
    main()
