from __future__ import annotations

import argparse
import ctypes
import subprocess
import time
from collections.abc import Callable
from pathlib import Path

import win32con
import win32gui
import win32ui
from PIL import Image, ImageChops, ImageGrab

LOAD_STATE_COMMAND_BASE = 40251
DEFAULT_EMULATOR_PATH = Path(r"D:\Code\roms\romtools\np2debug\np21debug_x64.exe")
DEFAULT_HDI_PATH = Path("patched") / "Possessioner.hdi"
PREFERRED_PROCESS_ID: int | None = None


VK_BY_NAME = {
    "ENTER": win32con.VK_RETURN,
    "SPACE": win32con.VK_SPACE,
    "DOWN": win32con.VK_DOWN,
    "UP": win32con.VK_UP,
    "LEFT": win32con.VK_LEFT,
    "RIGHT": win32con.VK_RIGHT,
}


def post_key(hwnd: int, vk: int, hold: float = 0.05) -> None:
    hwnd = ensure_valid_window(hwnd)
    win32gui.PostMessage(hwnd, win32con.WM_KEYDOWN, vk, 0)
    time.sleep(hold)
    win32gui.PostMessage(hwnd, win32con.WM_KEYUP, vk, 0)


def window_process_id(hwnd: int) -> int:
    process_id = ctypes.c_ulong()
    ctypes.windll.user32.GetWindowThreadProcessId(hwnd, ctypes.byref(process_id))
    return int(process_id.value)


def find_emulator_windows(*, process_id: int | None = None) -> list[int]:
    matches: list[int] = []

    def callback(hwnd: int, _extra: object) -> None:
        if not win32gui.IsWindowVisible(hwnd):
            return
        title = win32gui.GetWindowText(hwnd).strip()
        if "Neko Project 21" in title:
            if process_id is not None and window_process_id(hwnd) != process_id:
                return
            matches.append(hwnd)

    win32gui.EnumWindows(callback, None)
    return matches


def find_main_window(timeout: float = 40.0, *, process_id: int | None = None) -> int:
    deadline = time.time() + timeout
    while time.time() < deadline:
        matches = find_emulator_windows(process_id=process_id)
        if matches:
            return matches[0]
        time.sleep(0.25)
    raise SystemExit("Timed out waiting for an emulator window")


def ensure_valid_window(hwnd: int, timeout: float = 60.0) -> int:
    if win32gui.IsWindow(hwnd):
        return hwnd
    return find_main_window(timeout=timeout, process_id=PREFERRED_PROCESS_ID)


def close_existing_emulator_windows() -> None:
    for hwnd in find_emulator_windows():
        win32gui.PostMessage(hwnd, win32con.WM_CLOSE, 0, 0)
    if find_emulator_windows():
        time.sleep(2.0)


def load_state_direct(hwnd: int, slot: int) -> None:
    if not 0 <= slot <= 9:
        raise SystemExit("--load-state must be between 0 and 9")
    hwnd = ensure_valid_window(hwnd)
    win32gui.SendMessage(hwnd, win32con.WM_COMMAND, LOAD_STATE_COMMAND_BASE + slot, 0)


def capture_window_image(hwnd: int) -> Image.Image:
    hwnd = ensure_valid_window(hwnd)
    left, top, right, bottom = win32gui.GetWindowRect(hwnd)
    width = right - left
    height = bottom - top
    hwnd_dc = win32gui.GetWindowDC(hwnd)
    src_dc = win32ui.CreateDCFromHandle(hwnd_dc)
    mem_dc = src_dc.CreateCompatibleDC()
    bitmap = win32ui.CreateBitmap()
    bitmap.CreateCompatibleBitmap(src_dc, width, height)
    old_bitmap = mem_dc.SelectObject(bitmap)

    image = None
    try:
        result = ctypes.windll.user32.PrintWindow(hwnd, mem_dc.GetSafeHdc(), 0)
        if result == 1:
            bmpinfo = bitmap.GetInfo()
            bmpbytes = bitmap.GetBitmapBits(True)
            image = Image.frombuffer(
                "RGB",
                (bmpinfo["bmWidth"], bmpinfo["bmHeight"]),
                bmpbytes,
                "raw",
                "BGRX",
                0,
                1,
            )
    finally:
        try:
            if old_bitmap:
                mem_dc.SelectObject(old_bitmap)
        except win32ui.error:
            pass
        try:
            win32gui.DeleteObject(bitmap.GetHandle())
        except win32gui.error:
            pass
        try:
            mem_dc.DeleteDC()
        except win32ui.error:
            pass
        try:
            src_dc.DeleteDC()
        except win32ui.error:
            pass
        win32gui.ReleaseDC(hwnd, hwnd_dc)

    if image is None:
        image = ImageGrab.grab(bbox=(left, top, right, bottom))
    return image


def content_region(image: Image.Image) -> Image.Image:
    top_crop = 36
    bottom_crop = 0
    if image.height <= top_crop + bottom_crop:
        return image
    return image.crop((0, top_crop, image.width, image.height - bottom_crop))


def images_different(first: Image.Image, second: Image.Image) -> bool:
    return ImageChops.difference(content_region(first), content_region(second)).getbbox() is not None


def wait_for_content_change(hwnd: int, baseline: Image.Image, timeout: float = 15.0, poll: float = 0.25) -> Image.Image:
    deadline = time.time() + timeout
    latest = baseline
    while time.time() < deadline:
        latest = capture_window_image(hwnd)
        if images_different(baseline, latest):
            return latest
        time.sleep(poll)
    return latest


def wait_for_content_stable(
    hwnd: int,
    timeout: float = 15.0,
    poll: float = 0.25,
    stable_period: float = 1.0,
) -> Image.Image:
    deadline = time.time() + timeout
    previous = capture_window_image(hwnd)
    stable_since = None

    while time.time() < deadline:
        time.sleep(poll)
        current = capture_window_image(hwnd)
        if images_different(previous, current):
            previous = current
            stable_since = None
            continue
        if stable_since is None:
            stable_since = time.time()
        elif time.time() - stable_since >= stable_period:
            return current
        previous = current
    return previous


def press_and_wait(
    hwnd: int,
    vk: int,
    change_timeout: float = 10.0,
    stable_timeout: float = 10.0,
    stable_period: float = 1.0,
    wait_for_stable: bool = True,
) -> None:
    baseline = capture_window_image(hwnd)
    post_key(hwnd, vk)
    changed = wait_for_content_change(hwnd, baseline, timeout=change_timeout)
    if not images_different(baseline, changed):
        return
    if not wait_for_stable:
        time.sleep(0.15)
        return
    wait_for_content_stable(hwnd, timeout=stable_timeout, stable_period=stable_period)


def send_foreground_key(hwnd: int, vk: int, hold: float = 0.05) -> None:
    hwnd = ensure_valid_window(hwnd)
    ctypes.windll.user32.ShowWindow(hwnd, win32con.SW_RESTORE)
    ctypes.windll.user32.SetForegroundWindow(hwnd)
    time.sleep(0.1)
    ctypes.windll.user32.keybd_event(vk, 0, 0, 0)
    time.sleep(hold)
    ctypes.windll.user32.keybd_event(vk, 0, win32con.KEYEVENTF_KEYUP, 0)


def press_and_wait_with_fallback(
    hwnd: int,
    vk: int,
    change_timeout: float = 10.0,
    stable_timeout: float = 10.0,
    stable_period: float = 1.0,
) -> None:
    baseline = capture_window_image(hwnd)
    post_key(hwnd, vk)
    changed = wait_for_content_change(hwnd, baseline, timeout=change_timeout)
    if not images_different(baseline, changed):
        send_foreground_key(hwnd, vk)
        changed = wait_for_content_change(hwnd, baseline, timeout=change_timeout)
        if not images_different(baseline, changed):
            return
    wait_for_content_stable(hwnd, timeout=stable_timeout, stable_period=stable_period)


def click_window_point(
    hwnd: int,
    x: int,
    y: int,
    down_flag: int = win32con.MOUSEEVENTF_LEFTDOWN,
    up_flag: int = win32con.MOUSEEVENTF_LEFTUP,
) -> None:
    hwnd = ensure_valid_window(hwnd)
    left, top, _, _ = win32gui.GetWindowRect(hwnd)
    ctypes.windll.user32.ShowWindow(hwnd, win32con.SW_RESTORE)
    ctypes.windll.user32.SetForegroundWindow(hwnd)
    time.sleep(0.1)
    ctypes.windll.user32.SetCursorPos(left + x, top + y)
    time.sleep(0.05)
    ctypes.windll.user32.mouse_event(down_flag, 0, 0, 0, 0)
    time.sleep(0.05)
    ctypes.windll.user32.mouse_event(up_flag, 0, 0, 0, 0)


def middle_click_window_point(hwnd: int, x: int, y: int) -> None:
    click_window_point(
        hwnd,
        x,
        y,
        down_flag=win32con.MOUSEEVENTF_MIDDLEDOWN,
        up_flag=win32con.MOUSEEVENTF_MIDDLEUP,
    )


def press_until_change(
    hwnd: int,
    vk: int,
    attempts: int = 3,
    change_timeout: float = 3.0,
    stable_timeout: float = 12.0,
    stable_period: float = 1.0,
    retry_delay: float = 0.25,
) -> None:
    baseline = capture_window_image(hwnd)
    for _ in range(attempts):
        post_key(hwnd, vk)
        changed = wait_for_content_change(hwnd, baseline, timeout=change_timeout)
        if images_different(baseline, changed):
            wait_for_content_stable(hwnd, timeout=stable_timeout, stable_period=stable_period)
            return
        time.sleep(retry_delay)


def screenshot_window(hwnd: int, output_path: Path) -> Path:
    image = capture_window_image(hwnd)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    image.save(output_path)
    return output_path


def load_file_from_main_menu(hwnd: int, file_index: int = 0) -> None:
    if file_index < 0:
        raise SystemExit("--file-index must be 0 or greater")
    send_foreground_key(hwnd, VK_BY_NAME["DOWN"])
    time.sleep(1.0)
    send_foreground_key(hwnd, VK_BY_NAME["ENTER"])
    time.sleep(1.5)
    for _ in range(file_index + 1):
        send_foreground_key(hwnd, VK_BY_NAME["DOWN"])
        time.sleep(0.5)
    send_foreground_key(hwnd, VK_BY_NAME["ENTER"])
    time.sleep(6.0)
    wait_for_content_stable(hwnd, timeout=20.0, stable_period=1.5)


def parse_step(spec: str) -> tuple[int, int, int]:
    try:
        parts = spec.split(":")
    except ValueError as exc:
        raise SystemExit(f"Step must be ACTION:TARGET, got {spec!r}") from exc
    if len(parts) not in (2, 3):
        raise SystemExit(f"Step must be ACTION:TARGET or ACTION:TARGET:CLICKS, got {spec!r}")
    action_text, target_text = parts[0], parts[1]
    advance_count = int(parts[2]) if len(parts) == 3 else 0
    if advance_count < 0:
        raise SystemExit(f"Step advance count must be 0 or greater, got {spec!r}")
    return int(action_text), int(target_text), advance_count


def choose_menu_target(hwnd: int, action_index: int, target_index: int) -> None:
    middle_click_window_point(hwnd, 320, 220)
    time.sleep(0.3)

    for _ in range(action_index):
        press_and_wait(hwnd, VK_BY_NAME["DOWN"], change_timeout=3.0, wait_for_stable=False)
    press_and_wait(hwnd, VK_BY_NAME["ENTER"], change_timeout=5.0, stable_timeout=10.0, stable_period=0.75)
    time.sleep(0.5)
    for _ in range(target_index):
        press_and_wait(hwnd, VK_BY_NAME["DOWN"], change_timeout=3.0, wait_for_stable=False)
    time.sleep(0.3)
    press_and_wait_with_fallback(hwnd, VK_BY_NAME["ENTER"], change_timeout=12.0, stable_timeout=16.0, stable_period=1.5)


def save_trace_frame(trace_dir: Path | None, name: str, hwnd: int) -> None:
    if trace_dir is None:
        return
    screenshot_window(hwnd, trace_dir / name)


def run_menu_target_route(
    hwnd: int,
    load_state: int | None,
    action_index: int,
    target_index: int,
    file_index: int = 0,
    steps: list[tuple[int, int, int]] | None = None,
    trace_dir: Path | None = None,
    post_enter_count: int = 0,
    post_space_count: int = 0,
    post_focus_left_click_count: int = 0,
    startup_delay: float = 4.0,
) -> None:
    time.sleep(startup_delay)
    if load_state is not None:
        load_state_direct(hwnd, load_state)
        wait_for_content_stable(hwnd, timeout=8.0, stable_period=0.5)
    save_trace_frame(trace_dir, "00-after-load-state.png", hwnd)

    load_file_from_main_menu(hwnd, file_index=file_index)
    save_trace_frame(trace_dir, "01-after-file-load.png", hwnd)

    planned_steps = steps or [(action_index, target_index, 0)]
    frame_index = 2
    for index, (step_action, step_target, step_advance_count) in enumerate(planned_steps, start=1):
        choose_menu_target(hwnd, step_action, step_target)
        save_trace_frame(trace_dir, f"{frame_index:02d}-after-step-{index}.png", hwnd)
        frame_index += 1
        for advance_index in range(step_advance_count):
            press_and_wait_with_fallback(
                hwnd,
                VK_BY_NAME["SPACE"],
                change_timeout=12.0,
                stable_timeout=20.0,
                stable_period=1.5,
            )
            save_trace_frame(
                trace_dir,
                f"{frame_index:02d}-after-step-{index}-space-{advance_index + 1}.png",
                hwnd,
            )
            frame_index += 1

    for enter_index in range(post_enter_count):
        press_and_wait_with_fallback(hwnd, VK_BY_NAME["ENTER"], change_timeout=12.0, stable_timeout=20.0, stable_period=1.5)
        save_trace_frame(trace_dir, f"{frame_index:02d}-after-enter-{enter_index + 1}.png", hwnd)
        frame_index += 1

    for space_index in range(post_space_count):
        press_and_wait_with_fallback(
            hwnd,
            VK_BY_NAME["SPACE"],
            change_timeout=12.0,
            stable_timeout=20.0,
            stable_period=1.5,
        )
        save_trace_frame(trace_dir, f"{frame_index:02d}-after-space-{space_index + 1}.png", hwnd)
        frame_index += 1

    for click_index in range(post_focus_left_click_count):
        middle_click_window_point(hwnd, 320, 220)
        time.sleep(0.2)
        baseline = capture_window_image(hwnd)
        click_window_point(hwnd, 320, 220)
        changed = wait_for_content_change(hwnd, baseline, timeout=12.0)
        if images_different(baseline, changed):
            wait_for_content_stable(hwnd, timeout=20.0, stable_period=1.5)
        save_trace_frame(trace_dir, f"{frame_index:02d}-after-focus-left-{click_index + 1}.png", hwnd)
        frame_index += 1


def run_load_only_route(
    hwnd: int,
    load_state: int | None,
    file_index: int = 0,
    trace_dir: Path | None = None,
    post_enter_count: int = 0,
    post_space_count: int = 0,
    post_focus_left_click_count: int = 0,
    startup_delay: float = 4.0,
) -> None:
    time.sleep(startup_delay)
    if load_state is not None:
        load_state_direct(hwnd, load_state)
        wait_for_content_stable(hwnd, timeout=8.0, stable_period=0.5)
    save_trace_frame(trace_dir, "00-after-load-state.png", hwnd)

    load_file_from_main_menu(hwnd, file_index=file_index)
    save_trace_frame(trace_dir, "01-after-file-load.png", hwnd)

    frame_index = 2
    for enter_index in range(post_enter_count):
        press_and_wait_with_fallback(hwnd, VK_BY_NAME["ENTER"], change_timeout=12.0, stable_timeout=20.0, stable_period=1.5)
        save_trace_frame(trace_dir, f"{frame_index:02d}-after-enter-{enter_index + 1}.png", hwnd)
        frame_index += 1

    for space_index in range(post_space_count):
        press_and_wait_with_fallback(
            hwnd,
            VK_BY_NAME["SPACE"],
            change_timeout=12.0,
            stable_timeout=20.0,
            stable_period=1.5,
        )
        save_trace_frame(trace_dir, f"{frame_index:02d}-after-space-{space_index + 1}.png", hwnd)
        frame_index += 1

    for click_index in range(post_focus_left_click_count):
        middle_click_window_point(hwnd, 320, 220)
        time.sleep(0.2)
        baseline = capture_window_image(hwnd)
        click_window_point(hwnd, 320, 220)
        changed = wait_for_content_change(hwnd, baseline, timeout=12.0)
        if images_different(baseline, changed):
            wait_for_content_stable(hwnd, timeout=20.0, stable_period=1.5)
        save_trace_frame(trace_dir, f"{frame_index:02d}-after-focus-left-{click_index + 1}.png", hwnd)
        frame_index += 1


def advance_to_menu(
    hwnd: int,
    classify_fn: Callable[[Image.Image], str],
    max_presses: int = 100,
    space_change_timeout: float = 3.0,
    stable_timeout: float = 12.0,
    stable_period: float = 1.0,
) -> str:
    """Press SPACE until the screen reaches the action_menu state (or gives up).

    Uses *classify_fn* (a callable matching screen_state.classify_screen_state's
    signature) to decide whether to keep advancing or stop.

    Returns the final classified state.
    """
    for _ in range(max_presses):
        image = capture_window_image(hwnd)
        state = classify_fn(image)
        if state == "action_menu":
            return state
        if state in ("loading", "battle"):
            # Wait for things to settle rather than mashing SPACE
            wait_for_content_stable(hwnd, timeout=stable_timeout, stable_period=stable_period)
            continue
        # dialogue, cutscene, or unknown — try pressing SPACE
        baseline = image
        post_key(hwnd, VK_BY_NAME["SPACE"])
        changed = wait_for_content_change(hwnd, baseline, timeout=space_change_timeout)
        if not images_different(baseline, changed):
            # SPACE had no effect — likely already at menu or fully stable
            state = classify_fn(changed)
            return state
        wait_for_content_stable(hwnd, timeout=stable_timeout, stable_period=stable_period)
    return classify_fn(capture_window_image(hwnd))


def compare_images(first: Path, second: Path) -> tuple[bool, tuple[int, int, int, int] | None]:
    img1 = Image.open(first)
    img2 = Image.open(second)
    diff = ImageChops.difference(img1, img2)
    bbox = diff.getbbox()
    return bbox is None, bbox


def main() -> None:
    global PREFERRED_PROCESS_ID
    parser = argparse.ArgumentParser(description="Launch np2debug, run a scripted route, and capture the window.")
    parser.add_argument(
        "--emulator",
        type=Path,
        default=DEFAULT_EMULATOR_PATH,
        help=f"Path to np2debug executable (default: {DEFAULT_EMULATOR_PATH})",
    )
    parser.add_argument(
        "--hdi",
        type=Path,
        default=DEFAULT_HDI_PATH,
        help=f"Path to HDI image to boot (default: {DEFAULT_HDI_PATH})",
    )
    parser.add_argument("--output", type=Path, required=True, help="Output screenshot path")
    parser.add_argument("--route", choices=["menu-target", "load-only"], default="menu-target")
    parser.add_argument("--file-index", type=int, default=0, help="Zero-based save file index on the load-game menu")
    parser.add_argument("--action-index", type=int, default=0, help="Zero-based main action index after loading File 1")
    parser.add_argument("--target-index", type=int, default=0, help="Zero-based submenu target index for the chosen action")
    parser.add_argument(
        "--step",
        action="append",
        help="Repeatable ACTION:TARGET[:ADVANCES] step, e.g. --step 1:2 --step 1:2:1 for Talk/Friends twice then press Space once",
    )
    parser.add_argument("--trace-dir", type=Path, help="Optional directory to save intermediate route screenshots")
    parser.add_argument("--post-enter-count", type=int, default=0, help="Press Enter this many times after all steps")
    parser.add_argument("--post-space-count", type=int, default=0, help="Press Space this many times after all steps")
    parser.add_argument(
        "--post-focus-left-click-count",
        type=int,
        default=0,
        help="Fallback: after all steps, middle-click to focus and then left-click this many times",
    )
    parser.add_argument("--close", action="store_true", help="Close the emulator after capture")
    parser.add_argument("--close-existing", action="store_true", help="Close any existing emulator windows before launch")
    parser.add_argument("--load-state", type=int, help="Load state slot 0-9 via emulator menu command before the route")
    parser.add_argument("--startup-delay", type=float, default=4.0, help="Seconds to wait after emulator launch before routing")
    args = parser.parse_args()

    if args.close_existing:
        close_existing_emulator_windows()

    process = subprocess.Popen([str(args.emulator), str(args.hdi)], cwd=str(args.emulator.parent))
    PREFERRED_PROCESS_ID = process.pid
    hwnd = find_main_window(process_id=process.pid)
    print(f"PID={process.pid} HWND=0x{hwnd:08x}")

    if args.route == "menu-target":
        steps = [parse_step(spec) for spec in args.step] if args.step else None
        run_menu_target_route(
            hwnd,
            args.load_state,
            args.action_index,
            args.target_index,
            file_index=args.file_index,
            steps=steps,
            trace_dir=args.trace_dir,
            post_enter_count=args.post_enter_count,
            post_space_count=args.post_space_count,
            post_focus_left_click_count=args.post_focus_left_click_count,
            startup_delay=args.startup_delay,
        )
    elif args.route == "load-only":
        run_load_only_route(
            hwnd,
            args.load_state,
            file_index=args.file_index,
            trace_dir=args.trace_dir,
            post_enter_count=args.post_enter_count,
            post_space_count=args.post_space_count,
            post_focus_left_click_count=args.post_focus_left_click_count,
            startup_delay=args.startup_delay,
        )

    screenshot_path = screenshot_window(hwnd, args.output)
    print(f"Saved screenshot to {screenshot_path}")

    if args.close:
        win32gui.PostMessage(hwnd, win32con.WM_CLOSE, 0, 0)


if __name__ == "__main__":
    main()
