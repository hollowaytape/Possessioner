from __future__ import annotations

import argparse
import shutil
import subprocess
import time
from pathlib import Path
from typing import Iterable

from analyze_msd_context import load_pointer_rows
from rominfo import ORIGINAL_ROM_DIR, ORIGINAL_ROM_PATH, POINTER_DUMP_XLS_PATH
from romtools.disk import Disk

DEFAULT_EMULATOR_PATH = Path(r"D:\Code\roms\romtools\np2debug\np21debug_x64.exe")
DEFAULT_PATCHED_HDI_PATH = Path("patched") / "Possessioner.hdi"
DEFAULT_SOURCE_POS_EXE = Path(ORIGINAL_ROM_DIR) / "POS.EXE"


def parse_int(value: str) -> int:
    return int(str(value), 0)


def hex5(value: int) -> str:
    return f"0x{value:05x}"


def find_pointer_matches(
    pointer_rows: dict[str, dict[int, list[dict[str, object]]]],
    file_name: str,
    text_offset: int,
) -> list[dict[str, object]]:
    try:
        return pointer_rows[file_name][text_offset]
    except KeyError as exc:
        raise SystemExit(f"No pointer rows found for {file_name} {hex5(text_offset)}") from exc


def collect_arg_samples(
    root: Path,
    pointer_rows: dict[str, dict[int, list[dict[str, object]]]],
    limit: int,
) -> list[dict[str, object]]:
    pos_exe = (root / ORIGINAL_ROM_DIR / "POS.EXE").read_bytes()
    results: list[dict[str, object]] = []

    for file_name, text_rows in pointer_rows.items():
        for text_offset, entries in text_rows.items():
            for pointer_index, entry in enumerate(entries):
                ptr_loc = int(entry["pointer_location_int"])
                if ptr_loc <= 0 or ptr_loc + 2 >= len(pos_exe):
                    continue
                if pos_exe[ptr_loc - 1] != 0x02:
                    continue
                command = pos_exe[ptr_loc - 1 : ptr_loc + 3]
                results.append(
                    {
                        "file": file_name,
                        "text_offset": text_offset,
                        "pointer_index": pointer_index,
                        "pointer_location": ptr_loc,
                        "arg": command[3],
                        "command_bytes": command.hex(" "),
                    }
                )
    results.sort(key=lambda row: (row["arg"], row["file"], row["text_offset"], row["pointer_index"]))
    return results[:limit]


def patch_text_arg(
    pos_exe_bytes: bytes,
    pointer_location: int,
    expected_text_offset: int | None,
    new_arg: int,
    skip_text_check: bool = False,
) -> tuple[bytes, int]:
    if pointer_location <= 0 or pointer_location + 2 >= len(pos_exe_bytes):
        raise SystemExit(f"Pointer location {hex5(pointer_location)} is out of range for POS.EXE")

    opcode_offset = pointer_location - 1
    if pos_exe_bytes[opcode_offset] != 0x02:
        actual = pos_exe_bytes[opcode_offset]
        raise SystemExit(
            f"Pointer location {hex5(pointer_location)} is not preceded by opcode 0x02 (found 0x{actual:02x})"
        )

    current_text_offset = pos_exe_bytes[pointer_location] | (pos_exe_bytes[pointer_location + 1] << 8)
    if not skip_text_check and expected_text_offset is not None and current_text_offset != expected_text_offset:
        raise SystemExit(
            "Pointer/text mismatch: "
            f"{hex5(pointer_location)} points to {hex5(current_text_offset)}, expected {hex5(expected_text_offset)}"
        )

    old_arg = pos_exe_bytes[pointer_location + 2]
    if not 0 <= new_arg <= 0xFF:
        raise SystemExit(f"New arg must fit in one byte, got {new_arg}")

    patched = bytearray(pos_exe_bytes)
    patched[pointer_location + 2] = new_arg
    return bytes(patched), old_arg


def ensure_parent_dir(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def apply_instant_text_hack(pos_exe_bytes: bytes) -> bytes:
    patched = bytearray(pos_exe_bytes)
    patched[0xA3BF : 0xA3C1] = b"\xA8\x03"
    return bytes(patched)


def write_pos_exe(root: Path, output_pos_exe: Path, patched_bytes: bytes) -> None:
    ensure_parent_dir(output_pos_exe)
    output_pos_exe.write_bytes(patched_bytes)


def copy_disk_image(source_hdi: Path, output_hdi: Path) -> None:
    ensure_parent_dir(output_hdi)
    shutil.copy2(source_hdi, output_hdi)


def insert_pos_exe_into_disk(output_hdi: Path, output_pos_exe: Path) -> None:
    disk = Disk(str(output_hdi))
    staged_path = output_pos_exe
    cleanup = False
    if output_pos_exe.name.upper() != "POS.EXE":
        staged_path = output_pos_exe.with_name("POS.EXE")
        shutil.copy2(output_pos_exe, staged_path)
        cleanup = True
    try:
        disk.insert(str(staged_path), path_in_disk="PSSR\\")
    finally:
        if cleanup and staged_path.exists():
            staged_path.unlink()


def launch_emulator(emulator_path: Path, hdi_path: Path) -> subprocess.Popen[bytes]:
    return subprocess.Popen([str(emulator_path), str(hdi_path)], cwd=str(emulator_path.parent))


def send_keys_with_pywinauto(process: subprocess.Popen[bytes], keys: str, delay: float) -> None:
    try:
        from pywinauto import Application
        from pywinauto.keyboard import send_keys
    except ImportError as exc:
        raise SystemExit("pywinauto is not installed, so --keys cannot be used") from exc

    time.sleep(delay)
    app = Application(backend="win32").connect(process=process.pid)
    window = app.top_window()
    window.set_focus()
    send_keys(keys)


def default_output_paths(root: Path, file_name: str, text_offset: int, new_arg: int) -> tuple[Path, Path]:
    slug = f"{Path(file_name).stem.lower()}-{text_offset:05x}-arg{new_arg:02x}"
    output_dir = root / "patched" / "arg-experiments"
    return (
        output_dir / f"POS-{slug}.EXE",
        output_dir / f"Possessioner-{slug}.hdi",
    )


def iter_pointer_targets(
    matches: list[dict[str, object]],
    pointer_index: int | None,
    patch_all: bool,
) -> Iterable[dict[str, object]]:
    if patch_all:
        return matches
    if pointer_index is None:
        return [matches[0]]
    if pointer_index < 0 or pointer_index >= len(matches):
        raise SystemExit(f"--pointer-index {pointer_index} is out of range (0..{len(matches) - 1})")
    return [matches[pointer_index]]


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Patch one POS.EXE 0x02 <ptr> <arg> text-command arg and build a scratch HDI for testing."
    )
    parser.add_argument("--file", help="MSD file name, e.g. POS1.MSD")
    parser.add_argument("--text-offset", type=parse_int, help="MSD text offset, e.g. 0x0008a")
    parser.add_argument("--ptr-loc", type=parse_int, help="Explicit pointer location in POS.EXE, e.g. 0x0eb48")
    parser.add_argument("--pointer-index", type=int, help="Which pointer row to use when file+offset has multiple matches")
    parser.add_argument("--patch-all", action="store_true", help="Patch every pointer row for the selected file+offset")
    parser.add_argument("--new-arg", type=parse_int, help="New 1-byte arg value, e.g. 0x03")
    parser.add_argument("--output-pos-exe", type=Path, help="Where to write the patched POS.EXE")
    parser.add_argument("--output-hdi", type=Path, help="Where to write the scratch HDI")
    parser.add_argument("--source-hdi", type=Path, default=Path(ORIGINAL_ROM_PATH), help="Clean source HDI to copy")
    parser.add_argument(
        "--source-pos-exe",
        type=Path,
        default=DEFAULT_SOURCE_POS_EXE,
        help=f"POS.EXE to patch before inserting (default: {DEFAULT_SOURCE_POS_EXE})",
    )
    parser.add_argument(
        "--in-place-hdi",
        action="store_true",
        help="Patch the target HDI in place instead of copying source-hdi to a scratch image first",
    )
    parser.add_argument(
        "--emulator",
        type=Path,
        default=DEFAULT_EMULATOR_PATH,
        help=f"Path to np2debug / np21debug_x64.exe (default: {DEFAULT_EMULATOR_PATH})",
    )
    parser.add_argument("--launch", action="store_true", help="Launch the emulator with the scratch HDI")
    parser.add_argument("--keys", help="Optional pywinauto send_keys string to send after launch")
    parser.add_argument("--launch-delay", type=float, default=2.0, help="Seconds to wait before sending keys")
    parser.add_argument("--write-pos-only", action="store_true", help="Patch POS.EXE only; skip scratch HDI creation")
    parser.add_argument(
        "--skip-text-check",
        action="store_true",
        help="Patch the arg byte even if the source POS.EXE no longer points at the original dump offset",
    )
    parser.add_argument("--dry-run", action="store_true", help="Resolve the case and print the plan without writing files")
    parser.add_argument("--list-samples", action="store_true", help="Print sample pointer cases and exit")
    parser.add_argument("--limit", type=int, default=20, help="How many sample cases to print for --list-samples")
    args = parser.parse_args()

    root = Path(__file__).resolve().parent
    pointer_rows = load_pointer_rows(root / POINTER_DUMP_XLS_PATH)

    if args.list_samples:
        for sample in collect_arg_samples(root, pointer_rows, args.limit):
            print(
                f"{sample['file']} {hex5(int(sample['text_offset']))} "
                f"ptr[{sample['pointer_index']}]={hex5(int(sample['pointer_location']))} "
                f"arg=0x{int(sample['arg']):02x} bytes={sample['command_bytes']}"
            )
        return

    if args.new_arg is None:
        raise SystemExit("--new-arg is required unless --list-samples is used")

    explicit_pointer_location = args.ptr_loc
    expected_text_offset = None
    case_file = args.file

    if explicit_pointer_location is None:
        if not args.file or args.text_offset is None:
            raise SystemExit("Use either --ptr-loc or the combination of --file and --text-offset")
        matches = find_pointer_matches(pointer_rows, args.file, args.text_offset)
        targets = list(iter_pointer_targets(matches, args.pointer_index, args.patch_all))
        pointer_locations = [int(target["pointer_location_int"]) for target in targets]
        expected_text_offset = args.text_offset
    else:
        pointer_locations = [explicit_pointer_location]
        if args.text_offset is not None:
            expected_text_offset = args.text_offset

    pos_exe_path = args.source_pos_exe
    if not pos_exe_path.is_absolute():
        pos_exe_path = root / pos_exe_path
    pos_exe_bytes = pos_exe_path.read_bytes()

    patched_bytes = pos_exe_bytes
    old_args: list[tuple[int, int]] = []
    for pointer_location in pointer_locations:
        patched_bytes, old_arg = patch_text_arg(
            patched_bytes,
            pointer_location,
            expected_text_offset,
            args.new_arg,
            skip_text_check=args.skip_text_check,
        )
        old_args.append((pointer_location, old_arg))

    patched_bytes = apply_instant_text_hack(patched_bytes)

    if case_file is None:
        case_file = "POS"
    if expected_text_offset is None:
        expected_text_offset = pointer_locations[0]

    default_pos_exe, default_hdi = default_output_paths(root, case_file, expected_text_offset, args.new_arg)
    output_pos_exe = args.output_pos_exe or default_pos_exe
    if args.in_place_hdi:
        output_hdi = args.output_hdi or DEFAULT_PATCHED_HDI_PATH
    else:
        output_hdi = args.output_hdi or default_hdi

    print("Selected experiment:")
    for pointer_location, old_arg in old_args:
        print(f"  ptr={hex5(pointer_location)} old_arg=0x{old_arg:02x} new_arg=0x{args.new_arg:02x}")
    if args.file and args.text_offset is not None:
        print(f"  target={args.file} {hex5(args.text_offset)}")
    print("  extra_patch=instant text hack at 0x0a3bf")
    print(f"  output_pos_exe={output_pos_exe}")
    if not args.write_pos_only:
        print(f"  output_hdi={output_hdi}")

    if args.dry_run:
        return

    write_pos_exe(root, output_pos_exe, patched_bytes)

    if not args.write_pos_only:
        if not args.in_place_hdi:
            copy_disk_image(args.source_hdi, output_hdi)
        insert_pos_exe_into_disk(output_hdi, output_pos_exe)

    if args.launch:
        if args.write_pos_only:
            raise SystemExit("--launch requires scratch HDI output; remove --write-pos-only")
        process = launch_emulator(args.emulator, output_hdi)
        print(f"Launched emulator PID {process.pid}")
        if args.keys:
            send_keys_with_pywinauto(process, args.keys, args.launch_delay)


if __name__ == "__main__":
    main()
