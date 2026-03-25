from __future__ import annotations

import argparse
import configparser
import ctypes
import subprocess
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import win32con
import win32gui
import win32ui
from PIL import Image, ImageChops, ImageGrab

DEFAULT_WSL_DISTRO = "Ubuntu"
DEFAULT_FONT_PATH = Path(r"D:\libtas\font.rom")
DEFAULT_HDI_PATH = Path("patched") / "Possessioner.hdi"
DEFAULT_LIBTAS_PATH = "/usr/bin/libTAS"
DEFAULT_NP2KAI_PATH = "/usr/bin/sdlnp21kai"
DEFAULT_TIME_TRACK_THRESHOLD = 100
PC98_FPS_NUM = 1_000_000_000
PC98_FPS_DEN = 17_723_226
NP21KAI_CONFIG_SECTION = "NekoProject21kai"

VK_BY_NAME = {
    "ENTER": win32con.VK_RETURN,
    "SPACE": win32con.VK_SPACE,
    "DOWN": win32con.VK_DOWN,
    "UP": win32con.VK_UP,
    "LEFT": win32con.VK_LEFT,
    "RIGHT": win32con.VK_RIGHT,
    "TAB": win32con.VK_TAB,
    "PAUSE": win32con.VK_PAUSE,
    "V": ord("V"),
}

GAME_KEYSYM_BY_NAME = {
    "ENTER": "Return",
    "SPACE": "space",
    "DOWN": "Down",
    "UP": "Up",
    "LEFT": "Left",
    "RIGHT": "Right",
    "TAB": "Tab",
}


@dataclass
class FileBackup:
    path: Path
    existed: bool
    content: str | None


@dataclass
class LibtasSession:
    distro: str
    hdi_path: Path
    font_path: Path
    libtas_path: str
    np2kai_path: str
    movie_path: Path | None
    close_existing: bool
    time_track_threshold: int
    fast_forward: bool
    normal_speed_after_seconds: float | None = None
    process: subprocess.Popen[str] | None = None
    lua_linux_path: str | None = None
    movie_linux_path: str | None = None
    stderr_linux_path: str | None = None
    runtime_linux_dir: str | None = None
    runtime_np2kai_path: str | None = None
    backups: list[FileBackup] | None = None

    def wsl_unc_path(self, linux_path: str) -> Path:
        windows_linux_path = linux_path.replace("/", "\\")
        return Path(rf"\\wsl$\{self.distro}{windows_linux_path}")

    def run_wsl(
        self,
        args: list[str],
        *,
        check: bool = True,
        capture_output: bool = False,
    ) -> subprocess.CompletedProcess[str]:
        command = ["wsl", "-d", self.distro, "--exec", *args]
        return subprocess.run(
            command,
            check=check,
            capture_output=capture_output,
            text=True,
        )

    def run_wsl_shell(
        self,
        script: str,
        *,
        check: bool = True,
        capture_output: bool = False,
    ) -> subprocess.CompletedProcess[str]:
        command = ["wsl", "-d", self.distro, "--exec", "bash", "-lc", script]
        return subprocess.run(
            command,
            check=check,
            capture_output=capture_output,
            text=True,
        )

    def capture_wsl_shell(self, script: str) -> str:
        result = self.run_wsl_shell(script, capture_output=True)
        return result.stdout.strip()

    def windows_to_wsl_path(self, path: Path) -> str:
        quoted = sh_single_quote(str(path.resolve()))
        return self.capture_wsl_shell(f"wslpath -a {quoted}")

    def backup_file(self, path: Path) -> FileBackup:
        if path.exists():
            return FileBackup(path=path, existed=True, content=path.read_text(encoding="utf-8"))
        return FileBackup(path=path, existed=False, content=None)

    def restore_backups(self) -> None:
        if not self.backups:
            return
        for backup in self.backups:
            if backup.existed:
                backup.path.parent.mkdir(parents=True, exist_ok=True)
                backup.path.write_text(backup.content or "", encoding="utf-8")
            else:
                try:
                    backup.path.unlink()
                except FileNotFoundError:
                    pass

    def prepare_configs(self) -> None:
        home = self.capture_wsl_shell("printf %s \"$HOME\"")
        np2_cfg_path = self.wsl_unc_path(f"{home}/.config/sdlnp21kai/np21kai.cfg")
        libtas_cfg_path = self.wsl_unc_path(f"{home}/.config/libTAS/sdlnp21kai.ini")
        np2_cfg_path.parent.mkdir(parents=True, exist_ok=True)
        libtas_cfg_path.parent.mkdir(parents=True, exist_ok=True)

        self.backups = [
            self.backup_file(np2_cfg_path),
            self.backup_file(libtas_cfg_path),
        ]

        font_wsl = self.windows_to_wsl_path(self.font_path)
        hdi_wsl = self.windows_to_wsl_path(self.hdi_path)
        runtime_linux_dir = f"/tmp/possessioner-np2kai-{uuid.uuid4().hex}"
        runtime_np2kai_path = f"{runtime_linux_dir}/sdlnp21kai"
        quoted_runtime_dir = sh_single_quote(runtime_linux_dir)
        quoted_runtime_np2kai_path = sh_single_quote(runtime_np2kai_path)
        quoted_source_np2kai_path = sh_single_quote(self.np2kai_path)
        quoted_font_wsl = sh_single_quote(font_wsl)
        self.run_wsl_shell(
            " && ".join(
                [
                    f"mkdir -p {quoted_runtime_dir}",
                    f"ln -sf {quoted_source_np2kai_path} {quoted_runtime_np2kai_path}",
                    f"ln -sf {quoted_font_wsl} {quoted_runtime_dir}/font.rom",
                    f"ln -sf {quoted_font_wsl} {quoted_runtime_dir}/FONT.ROM",
                ]
            )
        )

        np2_config = configparser.RawConfigParser()
        np2_config.optionxform = str
        if np2_cfg_path.exists():
            try:
                np2_config.read(np2_cfg_path, encoding="utf-8")
            except configparser.Error:
                np2_config = configparser.RawConfigParser()
                np2_config.optionxform = str
        if not np2_config.has_section(NP21KAI_CONFIG_SECTION):
            np2_config.add_section(NP21KAI_CONFIG_SECTION)
        np2_config.set(NP21KAI_CONFIG_SECTION, "fontfile", font_wsl)
        np2_config.set(NP21KAI_CONFIG_SECTION, "biospath", runtime_linux_dir)
        np2_config.set(NP21KAI_CONFIG_SECTION, "HDD1FILE", hdi_wsl)
        with np2_cfg_path.open("w", encoding="utf-8") as handle:
            np2_config.write(handle)

        config = configparser.RawConfigParser()
        config.optionxform = str
        if libtas_cfg_path.exists():
            config.read(libtas_cfg_path, encoding="utf-8")
        if not config.has_section("General"):
            config.add_section("General")
        if not config.has_section("shared"):
            config.add_section("shared")

        movie_linux_path = (
            self.windows_to_wsl_path(self.movie_path) if self.movie_path else f"/tmp/possessioner-{uuid.uuid4().hex}.ltm"
        )
        stderr_linux_path = f"/tmp/possessioner-libtas-{uuid.uuid4().hex}.stderr"

        config.set("General", "gameargs", f"{hdi_wsl} ")
        config.set("General", "moviefile", movie_linux_path)
        config.set("shared", "framerate_num", str(PC98_FPS_NUM))
        config.set("shared", "framerate_den", str(PC98_FPS_DEN))

        for index in range(1, 11):
            config.set(
                "shared",
                f"main_gettimes_threshold\\{index}\\value",
                str(self.time_track_threshold),
            )

        with libtas_cfg_path.open("w", encoding="utf-8") as handle:
            config.write(handle)

        self.movie_linux_path = movie_linux_path
        self.stderr_linux_path = stderr_linux_path
        self.runtime_linux_dir = runtime_linux_dir
        self.runtime_np2kai_path = runtime_np2kai_path

    def write_lua_script(self) -> None:
        lua_linux_path = f"/tmp/possessioner-libtas-{uuid.uuid4().hex}.lua"
        lua_unc_path = self.wsl_unc_path(lua_linux_path)
        fast_forward_value = "1" if self.fast_forward else "0"
        normal_speed_after_frame = "nil"
        if self.normal_speed_after_seconds is not None:
            normal_speed_after_frame = str(
                max(
                    1,
                    round(self.normal_speed_after_seconds * PC98_FPS_NUM / PC98_FPS_DEN),
                )
            )
        lua_unc_path.write_text(
            "\n".join(
                [
                    f"local FAST_FORWARD = {fast_forward_value}",
                    f"local NORMAL_SPEED_AFTER_FRAME = {normal_speed_after_frame}",
                    "local restored_speed = false",
                    "",
                    "callback.onInput(function()",
                    f"  input.setFramerate({PC98_FPS_NUM}, {PC98_FPS_DEN})",
                    "end)",
                    "",
                    "callback.onFrame(function()",
                    "  if movie.currentFrame() == 1 and FAST_FORWARD ~= 0 then",
                    "    runtime.setFastForward(1)",
                    "  end",
                    "  if not restored_speed and NORMAL_SPEED_AFTER_FRAME ~= nil and movie.currentFrame() >= NORMAL_SPEED_AFTER_FRAME then",
                    "    runtime.setFastForward(0)",
                    "    restored_speed = true",
                    "  end",
                    "end)",
                    "",
                ]
            ),
            encoding="utf-8",
        )
        self.lua_linux_path = lua_linux_path

    def cleanup_processes(self) -> None:
        if self.process is not None and self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=5)
        self.run_wsl(["pkill", "-9", "-x", "sdlnp21kai"], check=False)
        self.run_wsl(["pkill", "-9", "-x", "libTAS"], check=False)

        for linux_path in (self.lua_linux_path, self.stderr_linux_path):
            if linux_path:
                try:
                    self.wsl_unc_path(linux_path).unlink()
                except FileNotFoundError:
                    pass
        if self.movie_path is None and self.movie_linux_path:
            try:
                self.wsl_unc_path(self.movie_linux_path).unlink()
            except FileNotFoundError:
                pass
        if self.runtime_linux_dir:
            self.run_wsl_shell(f"rm -rf {sh_single_quote(self.runtime_linux_dir)}", check=False)

    def launch(self) -> None:
        command = [
            "wsl",
            "-d",
            self.distro,
            "--exec",
            self.libtas_path,
            "--non-interactive",
            "-w",
            self.movie_linux_path or "/tmp/possessioner.ltm",
            "-l",
            self.lua_linux_path or "/tmp/possessioner.lua",
            self.runtime_np2kai_path or self.np2kai_path,
            self.windows_to_wsl_path(self.hdi_path),
        ]
        self.process = subprocess.Popen(
            command,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            text=True,
        )


def sh_single_quote(value: str) -> str:
    return "'" + value.replace("'", "'\"'\"'") + "'"


def window_process_id(hwnd: int) -> int:
    process_id = ctypes.c_ulong()
    ctypes.windll.user32.GetWindowThreadProcessId(hwnd, ctypes.byref(process_id))
    return int(process_id.value)


def live_game_window(hwnd: int | None = None, timeout: float = 10.0) -> int:
    if hwnd and win32gui.IsWindow(hwnd):
        return hwnd
    return find_game_window(timeout=timeout)


def focus_window(hwnd: int) -> None:
    hwnd = live_game_window(hwnd)
    ctypes.windll.user32.ShowWindow(hwnd, win32con.SW_RESTORE)
    ctypes.windll.user32.SetForegroundWindow(hwnd)
    time.sleep(0.1)


def send_foreground_key(hwnd: int, vk: int, hold: float = 0.05) -> None:
    focus_window(hwnd)
    ctypes.windll.user32.keybd_event(vk, 0, 0, 0)
    time.sleep(hold)
    ctypes.windll.user32.keybd_event(vk, 0, win32con.KEYEVENTF_KEYUP, 0)


def send_game_key(hwnd: int, keysym_name: str, *, wsl_distro: str = DEFAULT_WSL_DISTRO, hold: float = 0.05) -> None:
    focus_window(hwnd)
    wsl_code = "\n".join(
        [
            "import ctypes",
            "import time",
            "from ctypes import c_char_p, c_int, c_uint, c_ulong, c_void_p",
            "",
            "libX11 = ctypes.cdll.LoadLibrary('libX11.so.6')",
            "libXtst = ctypes.cdll.LoadLibrary('libXtst.so.6')",
            "",
            "libX11.XOpenDisplay.argtypes = [c_char_p]",
            "libX11.XOpenDisplay.restype = c_void_p",
            "libX11.XStringToKeysym.argtypes = [c_char_p]",
            "libX11.XStringToKeysym.restype = c_ulong",
            "libX11.XKeysymToKeycode.argtypes = [c_void_p, c_ulong]",
            "libX11.XKeysymToKeycode.restype = c_uint",
            "libX11.XFlush.argtypes = [c_void_p]",
            "libX11.XFlush.restype = c_int",
            "libX11.XSync.argtypes = [c_void_p, c_int]",
            "libX11.XSync.restype = c_int",
            "libXtst.XTestFakeKeyEvent.argtypes = [c_void_p, c_uint, c_int, c_ulong]",
            "libXtst.XTestFakeKeyEvent.restype = c_int",
            "",
            "display = libX11.XOpenDisplay(None)",
            "if not display:",
            "    raise SystemExit('Unable to open X display from WSL')",
            f"keysym = libX11.XStringToKeysym({keysym_name!r}.encode())",
            "if not keysym:",
            f"    raise SystemExit('Unknown X11 keysym: {keysym_name}')",
            "keycode = libX11.XKeysymToKeycode(display, keysym)",
            "if not keycode:",
            f"    raise SystemExit('Unable to map X11 keysym to keycode: {keysym_name}')",
            "libXtst.XTestFakeKeyEvent(display, keycode, 1, 0)",
            "libX11.XFlush(display)",
            "libX11.XSync(display, 0)",
            f"time.sleep({hold!r})",
            "libXtst.XTestFakeKeyEvent(display, keycode, 0, 0)",
            "libX11.XFlush(display)",
            "libX11.XSync(display, 0)",
        ]
    )
    subprocess.run(
        ["wsl", "-d", wsl_distro, "--exec", "python3", "-c", wsl_code],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=True,
    )


def find_windows_by_title(substring: str) -> list[int]:
    matches: list[int] = []

    def callback(hwnd: int, _extra: object) -> None:
        if not win32gui.IsWindowVisible(hwnd):
            return
        title = win32gui.GetWindowText(hwnd).strip()
        if substring in title:
            matches.append(hwnd)

    win32gui.EnumWindows(callback, None)
    return matches


def find_game_window(timeout: float = 40.0) -> int:
    deadline = time.time() + timeout
    while time.time() < deadline:
        matches = find_windows_by_title("Neko Project II kai")
        if matches:
            return matches[0]
        time.sleep(0.25)
    raise SystemExit("Timed out waiting for a NP2kai window")


def capture_window_image(hwnd: int) -> Image.Image:
    hwnd = live_game_window(hwnd)
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


def screenshot_window(hwnd: int, output_path: Path) -> Path:
    image = capture_window_image(hwnd)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    image.save(output_path)
    return output_path


def content_region(image: Image.Image) -> Image.Image:
    top_crop = 36
    if image.height <= top_crop:
        return image
    region = image.crop((0, top_crop, image.width, image.height)).copy()
    region.paste((0, 0, 0), (0, 0, min(120, region.width), min(80, region.height)))
    if region.height > 50:
        region.paste((0, 0, 0), (0, region.height - 50, min(170, region.width), region.height))
    return region


def images_different(first: Image.Image, second: Image.Image) -> bool:
    return ImageChops.difference(content_region(first), content_region(second)).getbbox() is not None


def images_different_ignoring_title_menu(first: Image.Image, second: Image.Image) -> bool:
    first_region = content_region(first).copy()
    second_region = content_region(second).copy()
    left = min(250, first_region.width)
    top = min(80, first_region.height)
    right = min(470, first_region.width)
    bottom = min(230, first_region.height)
    if left < right and top < bottom:
        box = (left, top, right, bottom)
        first_region.paste((0, 0, 0), box)
        second_region.paste((0, 0, 0), box)
    return ImageChops.difference(first_region, second_region).getbbox() is not None


def title_menu_visible(image: Image.Image) -> bool:
    if image.width < 420 or image.height < 260:
        return False
    box = image.crop((270, 110, 430, 245)).convert("RGB")
    red_pixels = 0
    bright_pixels = 0
    dark_pixels = 0
    for r, g, b in box.getdata():
        if r >= 140 and r >= g + 40 and r >= b + 40:
            red_pixels += 1
        if r >= 180 and g >= 180 and b >= 180:
            bright_pixels += 1
        if r <= 40 and g <= 40 and b <= 40:
            dark_pixels += 1
    total_pixels = box.width * box.height
    return red_pixels >= 1000 and bright_pixels >= 2000 and dark_pixels >= 5000


def startup_sequence_active(image: Image.Image) -> bool:
    if title_menu_visible(image):
        return True
    dark_pixels = 0
    total_pixels = image.width * image.height
    for r, g, b in image.convert("RGB").getdata():
        if r <= 40 and g <= 40 and b <= 40:
            dark_pixels += 1
    return (dark_pixels / total_pixels) >= 0.78


def wait_for_title_menu(
    hwnd: int,
    timeout: float = 45.0,
    poll: float = 0.25,
    stable_period: float = 1.0,
) -> Image.Image:
    deadline = time.time() + timeout
    latest = capture_window_image(hwnd)
    visible_since = None
    while time.time() < deadline:
        latest = capture_window_image(hwnd)
        if title_menu_visible(latest):
            if visible_since is None:
                visible_since = time.time()
            elif time.time() - visible_since >= stable_period:
                return latest
        else:
            visible_since = None
        time.sleep(poll)
    if not title_menu_visible(latest):
        raise SystemExit("Timed out waiting for the title menu before loading a save")
    return latest


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
    keysym_name: str,
    *,
    wsl_distro: str = DEFAULT_WSL_DISTRO,
    change_timeout: float = 10.0,
    stable_timeout: float = 10.0,
    stable_period: float = 1.0,
    wait_for_stable: bool = True,
) -> None:
    baseline = capture_window_image(hwnd)
    send_game_key(hwnd, keysym_name, wsl_distro=wsl_distro)
    changed = wait_for_content_change(hwnd, baseline, timeout=change_timeout)
    if not images_different(baseline, changed):
        return
    if not wait_for_stable:
        time.sleep(0.15)
        return
    wait_for_content_stable(hwnd, timeout=stable_timeout, stable_period=stable_period)


def click_window_point(
    hwnd: int,
    x: int,
    y: int,
    down_flag: int = win32con.MOUSEEVENTF_LEFTDOWN,
    up_flag: int = win32con.MOUSEEVENTF_LEFTUP,
) -> None:
    hwnd = live_game_window(hwnd)
    focus_window(hwnd)
    left, top, _, _ = win32gui.GetWindowRect(hwnd)
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


def press_and_wait_with_fallback(
    hwnd: int,
    keysym_name: str,
    *,
    wsl_distro: str = DEFAULT_WSL_DISTRO,
    change_timeout: float = 10.0,
    stable_timeout: float = 10.0,
    stable_period: float = 1.0,
) -> None:
    baseline = capture_window_image(hwnd)
    send_game_key(hwnd, keysym_name, wsl_distro=wsl_distro)
    changed = wait_for_content_change(hwnd, baseline, timeout=change_timeout)
    if not images_different(baseline, changed):
        return
    wait_for_content_stable(hwnd, timeout=stable_timeout, stable_period=stable_period)


def advance_to_menu(
    hwnd: int,
    classify_fn: Callable[[Image.Image], str],
    *,
    wsl_distro: str = DEFAULT_WSL_DISTRO,
    max_presses: int = 100,
    space_change_timeout: float = 3.0,
    stable_timeout: float = 12.0,
    stable_period: float = 1.0,
) -> str:
    """Press SPACE until the vision classifier sees an action_menu.

    Returns the final classified state string.  Handles dialogue, cutscene,
    loading, and battle states gracefully.  Uses the libTAS send_game_key path
    so that key events are injected via WSL X11 (same as the rest of the route).
    """
    for _ in range(max_presses):
        image = capture_window_image(hwnd)
        state = classify_fn(image)
        if state == "action_menu":
            return state
        if state in ("loading", "battle"):
            wait_for_content_stable(hwnd, timeout=stable_timeout, stable_period=stable_period)
            continue
        baseline = image
        send_game_key(hwnd, GAME_KEYSYM_BY_NAME["SPACE"], wsl_distro=wsl_distro)
        changed = wait_for_content_change(hwnd, baseline, timeout=space_change_timeout)
        if not images_different(baseline, changed):
            # Screen didn't move after SPACE — assume we've arrived at the menu
            state = classify_fn(changed)
            return state
        wait_for_content_stable(hwnd, timeout=stable_timeout, stable_period=stable_period)
    return classify_fn(capture_window_image(hwnd))


def load_file_from_main_menu(hwnd: int, file_index: int = 0, *, wsl_distro: str = DEFAULT_WSL_DISTRO) -> None:
    if file_index < 0:
        raise SystemExit("--file-index must be 0 or greater")
    wait_for_title_menu(hwnd)
    send_game_key(hwnd, GAME_KEYSYM_BY_NAME["DOWN"], wsl_distro=wsl_distro)
    time.sleep(0.5)
    send_game_key(hwnd, GAME_KEYSYM_BY_NAME["ENTER"], wsl_distro=wsl_distro)
    time.sleep(1.5)
    for _ in range(file_index + 1):
        send_game_key(hwnd, GAME_KEYSYM_BY_NAME["DOWN"], wsl_distro=wsl_distro)
        time.sleep(0.3)
    send_game_key(hwnd, GAME_KEYSYM_BY_NAME["ENTER"], wsl_distro=wsl_distro)
    time.sleep(4.0)
    wait_for_content_stable(hwnd, timeout=20.0, stable_period=1.5)


def start_new_game_from_main_menu(
    hwnd: int,
    settle_delay: float = 20.0,
    *,
    wsl_distro: str = DEFAULT_WSL_DISTRO,
) -> None:
    title_press_deadline = time.time() + 35.0
    while time.time() < title_press_deadline:
        send_game_key(hwnd, GAME_KEYSYM_BY_NAME["ENTER"], wsl_distro=wsl_distro)
        time.sleep(1.0)
    if settle_delay:
        time.sleep(settle_delay)
    wait_for_content_stable(hwnd, timeout=20.0, stable_period=1.5)


def parse_step(spec: str) -> tuple[int, int, int]:
    parts = spec.split(":")
    if len(parts) not in (2, 3):
        raise SystemExit(f"Step must be ACTION:TARGET or ACTION:TARGET:ADVANCES, got {spec!r}")
    action_text, target_text = parts[0], parts[1]
    advance_count = int(parts[2]) if len(parts) == 3 else 0
    if advance_count < 0:
        raise SystemExit(f"Step advance count must be 0 or greater, got {spec!r}")
    return int(action_text), int(target_text), advance_count


def choose_menu_target(hwnd: int, action_index: int, target_index: int, *, wsl_distro: str = DEFAULT_WSL_DISTRO) -> None:
    focus_window(hwnd)
    time.sleep(0.2)
    for _ in range(8):
        send_game_key(hwnd, GAME_KEYSYM_BY_NAME["UP"], wsl_distro=wsl_distro)
        time.sleep(0.05)
    for _ in range(action_index):
        press_and_wait(
            hwnd,
            GAME_KEYSYM_BY_NAME["DOWN"],
            wsl_distro=wsl_distro,
            change_timeout=3.0,
            wait_for_stable=False,
        )
    press_and_wait(
        hwnd,
        GAME_KEYSYM_BY_NAME["ENTER"],
        wsl_distro=wsl_distro,
        change_timeout=5.0,
        stable_timeout=10.0,
        stable_period=0.75,
    )
    time.sleep(0.5)
    for _ in range(8):
        send_game_key(hwnd, GAME_KEYSYM_BY_NAME["UP"], wsl_distro=wsl_distro)
        time.sleep(0.05)
    for _ in range(target_index):
        press_and_wait(
            hwnd,
            GAME_KEYSYM_BY_NAME["DOWN"],
            wsl_distro=wsl_distro,
            change_timeout=3.0,
            wait_for_stable=False,
        )
    time.sleep(0.3)
    press_and_wait_with_fallback(
        hwnd,
        GAME_KEYSYM_BY_NAME["ENTER"],
        wsl_distro=wsl_distro,
        change_timeout=12.0,
        stable_timeout=16.0,
        stable_period=1.5,
    )


def save_trace_frame(trace_dir: Path | None, name: str, hwnd: int) -> None:
    if trace_dir is None:
        return
    screenshot_window(hwnd, trace_dir / name)


def run_timed_startup_spaces(
    hwnd: int,
    *,
    duration_seconds: float,
    interval_seconds: float,
    wsl_distro: str = DEFAULT_WSL_DISTRO,
    trace_dir: Path | None = None,
    frame_index: int = 0,
) -> int:
    if duration_seconds <= 0:
        return frame_index
    if interval_seconds <= 0:
        raise SystemExit("--startup-space-interval must be greater than 0 when timed startup spaces are enabled")
    deadline = time.time() + duration_seconds
    next_press = time.time()
    press_index = 0
    while True:
        now = time.time()
        if now >= deadline:
            break
        if now < next_press:
            time.sleep(min(0.1, next_press - now))
            continue
        send_game_key(hwnd, GAME_KEYSYM_BY_NAME["SPACE"], wsl_distro=wsl_distro)
        press_index += 1
        if trace_dir is not None:
            save_trace_frame(trace_dir, f"{frame_index:02d}-after-startup-space-{press_index}.png", hwnd)
            frame_index += 1
        next_press += interval_seconds
    return frame_index


def run_menu_target_route(
    hwnd: int,
    action_index: int,
    target_index: int,
    *,
    wsl_distro: str = DEFAULT_WSL_DISTRO,
    start_mode: str = "load-game",
    file_index: int = 0,
    steps: list[tuple[int, int, int]] | None = None,
    trace_dir: Path | None = None,
    startup_space_duration: float = 0.0,
    startup_space_interval: float = 0.0,
    pre_space_count: int = 0,
    post_enter_count: int = 0,
    post_space_count: int = 0,
    post_focus_left_click_count: int = 0,
    startup_delay: float = 4.0,
    new_game_delay: float = 20.0,
) -> None:
    time.sleep(startup_delay)
    save_trace_frame(trace_dir, "00-startup.png", hwnd)
    if start_mode == "new-game":
        start_new_game_from_main_menu(hwnd, settle_delay=new_game_delay, wsl_distro=wsl_distro)
    else:
        load_file_from_main_menu(hwnd, file_index=file_index, wsl_distro=wsl_distro)
    save_trace_frame(trace_dir, "01-after-file-load.png", hwnd)

    frame_index = 2
    frame_index = run_timed_startup_spaces(
        hwnd,
        duration_seconds=startup_space_duration,
        interval_seconds=startup_space_interval,
        wsl_distro=wsl_distro,
        trace_dir=trace_dir,
        frame_index=frame_index,
    )
    for space_index in range(pre_space_count):
        press_and_wait_with_fallback(
            hwnd,
            GAME_KEYSYM_BY_NAME["SPACE"],
            wsl_distro=wsl_distro,
            change_timeout=12.0,
            stable_timeout=20.0,
            stable_period=1.5,
        )
        save_trace_frame(trace_dir, f"{frame_index:02d}-after-pre-space-{space_index + 1}.png", hwnd)
        frame_index += 1

    planned_steps = steps or [(action_index, target_index, 0)]
    for index, (step_action, step_target, step_advance_count) in enumerate(planned_steps, start=1):
        choose_menu_target(hwnd, step_action, step_target, wsl_distro=wsl_distro)
        save_trace_frame(trace_dir, f"{frame_index:02d}-after-step-{index}.png", hwnd)
        frame_index += 1
        for advance_index in range(step_advance_count):
            press_and_wait_with_fallback(
                hwnd,
                GAME_KEYSYM_BY_NAME["SPACE"],
                wsl_distro=wsl_distro,
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
        press_and_wait_with_fallback(
            hwnd,
            GAME_KEYSYM_BY_NAME["ENTER"],
            wsl_distro=wsl_distro,
            change_timeout=12.0,
            stable_timeout=20.0,
            stable_period=1.5,
        )
        save_trace_frame(trace_dir, f"{frame_index:02d}-after-enter-{enter_index + 1}.png", hwnd)
        frame_index += 1

    for space_index in range(post_space_count):
        press_and_wait_with_fallback(
            hwnd,
            GAME_KEYSYM_BY_NAME["SPACE"],
            wsl_distro=wsl_distro,
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
    *,
    wsl_distro: str = DEFAULT_WSL_DISTRO,
    start_mode: str = "load-game",
    file_index: int = 0,
    trace_dir: Path | None = None,
    startup_space_duration: float = 0.0,
    startup_space_interval: float = 0.0,
    pre_space_count: int = 0,
    post_enter_count: int = 0,
    post_space_count: int = 0,
    post_focus_left_click_count: int = 0,
    startup_delay: float = 4.0,
    new_game_delay: float = 20.0,
) -> None:
    time.sleep(startup_delay)
    save_trace_frame(trace_dir, "00-startup.png", hwnd)
    if start_mode == "new-game":
        start_new_game_from_main_menu(hwnd, settle_delay=new_game_delay, wsl_distro=wsl_distro)
    else:
        load_file_from_main_menu(hwnd, file_index=file_index, wsl_distro=wsl_distro)
    save_trace_frame(trace_dir, "01-after-file-load.png", hwnd)

    frame_index = 2
    frame_index = run_timed_startup_spaces(
        hwnd,
        duration_seconds=startup_space_duration,
        interval_seconds=startup_space_interval,
        wsl_distro=wsl_distro,
        trace_dir=trace_dir,
        frame_index=frame_index,
    )
    for space_index in range(pre_space_count):
        press_and_wait_with_fallback(
            hwnd,
            GAME_KEYSYM_BY_NAME["SPACE"],
            wsl_distro=wsl_distro,
            change_timeout=12.0,
            stable_timeout=20.0,
            stable_period=1.5,
        )
        save_trace_frame(trace_dir, f"{frame_index:02d}-after-pre-space-{space_index + 1}.png", hwnd)
        frame_index += 1

    for enter_index in range(post_enter_count):
        press_and_wait_with_fallback(
            hwnd,
            GAME_KEYSYM_BY_NAME["ENTER"],
            wsl_distro=wsl_distro,
            change_timeout=12.0,
            stable_timeout=20.0,
            stable_period=1.5,
        )
        save_trace_frame(trace_dir, f"{frame_index:02d}-after-enter-{enter_index + 1}.png", hwnd)
        frame_index += 1

    for space_index in range(post_space_count):
        press_and_wait_with_fallback(
            hwnd,
            GAME_KEYSYM_BY_NAME["SPACE"],
            wsl_distro=wsl_distro,
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


def main() -> None:
    parser = argparse.ArgumentParser(description="Launch NP2kai through libTAS in WSL, run a route, and capture a screenshot.")
    parser.add_argument("--wsl-distro", default=DEFAULT_WSL_DISTRO, help=f"WSL distro name (default: {DEFAULT_WSL_DISTRO})")
    parser.add_argument("--font", type=Path, default=DEFAULT_FONT_PATH, help=f"PC-98 font ROM path (default: {DEFAULT_FONT_PATH})")
    parser.add_argument("--hdi", type=Path, default=DEFAULT_HDI_PATH, help=f"HDI image path (default: {DEFAULT_HDI_PATH})")
    parser.add_argument("--output", type=Path, required=True, help="Output screenshot path")
    parser.add_argument("--movie", type=Path, help="Optional path to keep the recorded libTAS movie (.ltm)")
    parser.add_argument("--trace-dir", type=Path, help="Optional directory to save intermediate route screenshots")
    parser.add_argument("--route", choices=["menu-target", "load-only"], default="menu-target")
    parser.add_argument("--start-mode", choices=["load-game", "new-game"], default="load-game", help="How to begin from the title screen")
    parser.add_argument("--file-index", type=int, default=0, help="Zero-based save file index on the load-game menu")
    parser.add_argument("--startup-space-duration", type=float, default=0.0, help="After loading, auto-press Space for this many seconds before route steps")
    parser.add_argument("--startup-space-interval", type=float, default=0.0, help="Interval in seconds between automatic startup Space presses")
    parser.add_argument("--pre-space-count", type=int, default=0, help="Press Space this many times after loading and before any menu steps")
    parser.add_argument("--action-index", type=int, default=0, help="Zero-based main action index after loading")
    parser.add_argument("--target-index", type=int, default=0, help="Zero-based submenu target index for the chosen action")
    parser.add_argument(
        "--step",
        action="append",
        help="Repeatable ACTION:TARGET[:ADVANCES] step, e.g. --step 1:1 --step 1:1:1",
    )
    parser.add_argument("--post-enter-count", type=int, default=0, help="Press Enter this many times after all steps")
    parser.add_argument("--post-space-count", type=int, default=0, help="Press Space this many times after all steps")
    parser.add_argument(
        "--post-focus-left-click-count",
        type=int,
        default=0,
        help="Fallback: middle-click to focus and then left-click this many times after all steps",
    )
    parser.add_argument("--pause-before-capture", action="store_true", help="Send libTAS Pause before the final screenshot")
    parser.add_argument("--frame-advance-count", type=int, default=0, help="After pausing, press libTAS frame-advance (V) this many times")
    parser.add_argument("--startup-delay", type=float, default=0.0, help="Seconds to wait after launch before routing")
    parser.add_argument("--new-game-delay", type=float, default=20.0, help="Seconds to let the intro/autoplay settle after starting a new game")
    parser.add_argument("--close-existing", action="store_true", help="Kill any existing WSL libTAS/NP2kai processes before launch")
    parser.add_argument("--time-track-threshold", type=int, default=DEFAULT_TIME_TRACK_THRESHOLD, help="Value to apply to libTAS main_gettimes_threshold slots")
    parser.add_argument("--no-fast-forward", action="store_true", help="Do not enable libTAS fast-forward on frame 1")
    parser.add_argument("--normal-speed-after-seconds", type=float, help="If set, disable fast-forward after this many in-game seconds")
    args = parser.parse_args()

    if args.frame_advance_count < 0:
        raise SystemExit("--frame-advance-count must be 0 or greater")
    if args.normal_speed_after_seconds is not None and args.normal_speed_after_seconds < 0:
        raise SystemExit("--normal-speed-after-seconds must be 0 or greater")
    if args.startup_space_duration < 0:
        raise SystemExit("--startup-space-duration must be 0 or greater")
    if args.startup_space_interval < 0:
        raise SystemExit("--startup-space-interval must be 0 or greater")
    if args.startup_space_duration > 0 and args.startup_space_interval <= 0:
        raise SystemExit("--startup-space-interval must be greater than 0 when --startup-space-duration is used")

    session = LibtasSession(
        distro=args.wsl_distro,
        hdi_path=args.hdi,
        font_path=args.font,
        libtas_path=DEFAULT_LIBTAS_PATH,
        np2kai_path=DEFAULT_NP2KAI_PATH,
        movie_path=args.movie,
        close_existing=args.close_existing,
        time_track_threshold=args.time_track_threshold,
        fast_forward=not args.no_fast_forward,
        normal_speed_after_seconds=args.normal_speed_after_seconds,
    )

    if session.close_existing:
        session.cleanup_processes()

    hwnd = None
    try:
        session.prepare_configs()
        session.write_lua_script()
        session.launch()
        hwnd = find_game_window()
        print(f"HWND=0x{hwnd:08x} PID={window_process_id(hwnd)}")

        if args.route == "menu-target":
            steps = [parse_step(spec) for spec in args.step] if args.step else None
            run_menu_target_route(
                hwnd,
                args.action_index,
                args.target_index,
                wsl_distro=args.wsl_distro,
                start_mode=args.start_mode,
                file_index=args.file_index,
                steps=steps,
                trace_dir=args.trace_dir,
                startup_space_duration=args.startup_space_duration,
                startup_space_interval=args.startup_space_interval,
                pre_space_count=args.pre_space_count,
                post_enter_count=args.post_enter_count,
                post_space_count=args.post_space_count,
                post_focus_left_click_count=args.post_focus_left_click_count,
                startup_delay=args.startup_delay,
                new_game_delay=args.new_game_delay,
            )
        else:
            run_load_only_route(
                hwnd,
                wsl_distro=args.wsl_distro,
                start_mode=args.start_mode,
                file_index=args.file_index,
                trace_dir=args.trace_dir,
                startup_space_duration=args.startup_space_duration,
                startup_space_interval=args.startup_space_interval,
                pre_space_count=args.pre_space_count,
                post_enter_count=args.post_enter_count,
                post_space_count=args.post_space_count,
                post_focus_left_click_count=args.post_focus_left_click_count,
                startup_delay=args.startup_delay,
                new_game_delay=args.new_game_delay,
            )

        if args.pause_before_capture:
            send_foreground_key(hwnd, VK_BY_NAME["PAUSE"])
            time.sleep(0.2)

        for _ in range(args.frame_advance_count):
            send_foreground_key(hwnd, VK_BY_NAME["V"])
            time.sleep(0.05)
        if args.pause_before_capture or args.frame_advance_count:
            wait_for_content_stable(hwnd, timeout=10.0, stable_period=0.5)

        screenshot_path = screenshot_window(hwnd, args.output)
        print(f"Saved screenshot to {screenshot_path}")
    finally:
        session.cleanup_processes()
        session.restore_backups()


if __name__ == "__main__":
    main()
