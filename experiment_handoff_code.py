from __future__ import annotations

import argparse
from pathlib import Path

from analyze_handoff_contexts import (
    SAVE_FORMAT_PATH,
    build_offset_to_rows,
    format_destination_label,
    load_dump_rows,
    load_map_names,
    scan_handoffs,
)
from experiment_text_arg import (
    apply_instant_text_hack,
    copy_disk_image,
    ensure_parent_dir,
    insert_pos_exe_into_disk,
    launch_emulator,
    send_keys_with_pywinauto,
    write_pos_exe,
)
from rominfo import DUMP_XLS_PATH, ORIGINAL_ROM_DIR, ORIGINAL_ROM_PATH

DEFAULT_PATCHED_HDI_PATH = Path("patched") / "Possessioner.hdi"
DEFAULT_SOURCE_POS_EXE = Path(ORIGINAL_ROM_DIR) / "POS.EXE"
DEFAULT_EMULATOR_PATH = Path(r"D:\Code\roms\romtools\np2debug\np21debug_x64.exe")


def parse_int(value: str) -> int:
    return int(str(value), 0)


def hex5(value: int) -> str:
    return f"0x{value:05x}"


def patch_handoff_code(
    pos_exe_bytes: bytes,
    handoff_location: int,
    new_kind: int | None,
    new_code: int | None,
) -> tuple[bytes, bytes]:
    if handoff_location < 0 or handoff_location + 3 >= len(pos_exe_bytes):
        raise SystemExit(f"Handoff location {hex5(handoff_location)} is out of range for POS.EXE")

    opcode = pos_exe_bytes[handoff_location : handoff_location + 4]
    if opcode[0] != 0x03 or opcode[2] != 0x00 or opcode[3] != 0x01:
        raise SystemExit(
            f"{hex5(handoff_location)} is not a 03 xx 00 01 handoff opcode "
            f"(found {opcode.hex(' ')})"
        )

    if new_kind is None and new_code is None:
        raise SystemExit("At least one of --new-kind or --new-code is required")
    if new_kind is not None and not 0 <= new_kind <= 0xFF:
        raise SystemExit(f"New handoff kind must fit in one byte, got {new_kind}")
    if new_code is not None and not 0 <= new_code <= 0xFF:
        raise SystemExit(f"New destination code must fit in one byte, got {new_code}")

    patched = bytearray(pos_exe_bytes)
    old_opcode = bytes(patched[handoff_location : handoff_location + 4])
    if new_kind is not None:
        patched[handoff_location] = new_kind
    if new_code is not None:
        patched[handoff_location + 1] = new_code
    return bytes(patched), old_opcode


def default_output_paths(root: Path, handoff_location: int, new_kind: int | None, new_code: int | None) -> tuple[Path, Path]:
    slug_bits = [f"handoff-{handoff_location:05x}"]
    if new_kind is not None:
        slug_bits.append(f"kind{new_kind:02x}")
    if new_code is not None:
        slug_bits.append(f"code{new_code:02x}")
    slug = "-".join(slug_bits)
    output_dir = root / "patched" / "handoff-experiments"
    return (
        output_dir / f"POS-{slug}.EXE",
        output_dir / f"Possessioner-{slug}.hdi",
    )


def list_handoff_destinations(root: Path, source_pos_exe: Path) -> None:
    rows_by_file_offset = load_dump_rows(root / DUMP_XLS_PATH)
    offset_to_rows = build_offset_to_rows(rows_by_file_offset)
    map_names = load_map_names(SAVE_FORMAT_PATH)
    results = scan_handoffs(source_pos_exe.read_bytes(), offset_to_rows, map_names)

    counts: dict[int, int] = {}
    for item in results:
        counts[item["arg1"]] = counts.get(item["arg1"], 0) + 1

    for arg1 in sorted(counts):
        print(f"0x{arg1:02x} | {format_destination_label(arg1, map_names.get(arg1))} | occurrences={counts[arg1]}")


def load_handoffs(root: Path, source_pos_exe: Path) -> list[dict[str, object]]:
    rows_by_file_offset = load_dump_rows(root / DUMP_XLS_PATH)
    offset_to_rows = build_offset_to_rows(rows_by_file_offset)
    map_names = load_map_names(SAVE_FORMAT_PATH)
    return scan_handoffs(source_pos_exe.read_bytes(), offset_to_rows, map_names)


def describe_handoff_location(root: Path, source_pos_exe: Path, handoff_location: int) -> dict[str, object] | None:
    for item in load_handoffs(root, source_pos_exe):
        if item["location"] == handoff_location:
            return item
    return None


def list_handoff_occurrences(root: Path, source_pos_exe: Path) -> None:
    results = load_handoffs(root, source_pos_exe)

    for item in results:
        print(f"{hex5(item['location'])} | 03 {item['arg1']:02x} 00 01 | {item['destination_label']}")
        if item["row_matches"]:
            for match in item["row_matches"]:
                label = match["block_command"] or match["command"] or "(no command)"
                print(f"  {match['file']} {hex5(match['offset'])} | {label}")
        else:
            print("  (no resolved workbook row)")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Patch one POS.EXE 03 xx 00 01 handoff opcode and build a scratch HDI for testing."
    )
    parser.add_argument("--handoff-loc", type=parse_int, help="Opcode location in POS.EXE, e.g. 0x1eafb")
    parser.add_argument("--new-kind", type=parse_int, help="New first opcode byte, e.g. 0x01")
    parser.add_argument("--new-code", type=parse_int, help="New 1-byte destination code, e.g. 0x0f")
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
    parser.add_argument("--dry-run", action="store_true", help="Print the patch plan without writing files")
    parser.add_argument("--list-destinations", action="store_true", help="List unique 03 xx 00 01 destination bytes and exit")
    parser.add_argument("--list-occurrences", action="store_true", help="List every 03 xx 00 01 handoff site and exit")
    parser.add_argument("--describe-loc", type=parse_int, help="Describe one existing handoff location and exit")
    args = parser.parse_args()

    root = Path(__file__).resolve().parent

    pos_exe_path = args.source_pos_exe
    if not pos_exe_path.is_absolute():
        pos_exe_path = root / pos_exe_path

    if args.list_destinations:
        list_handoff_destinations(root, pos_exe_path)
        return
    if args.list_occurrences:
        list_handoff_occurrences(root, pos_exe_path)
        return
    if args.describe_loc is not None:
        item = describe_handoff_location(root, pos_exe_path, args.describe_loc)
        if item is None:
            raise SystemExit(f"No 03 xx 00 01 handoff found at {hex5(args.describe_loc)}")
        print(f"{hex5(item['location'])} | 03 {item['arg1']:02x} 00 01 | {item['destination_label']}")
        if item["row_matches"]:
            for match in item["row_matches"]:
                label = match["block_command"] or match["command"] or "(no command)"
                print(f"  {match['file']} {hex5(match['offset'])} | {label}")
        else:
            print("  (no resolved workbook row)")
        return

    if args.handoff_loc is None or (args.new_kind is None and args.new_code is None):
        raise SystemExit("--handoff-loc and at least one of --new-kind/--new-code are required unless a list mode is used")

    pos_exe_bytes = pos_exe_path.read_bytes()

    patched_bytes, old_opcode = patch_handoff_code(pos_exe_bytes, args.handoff_loc, args.new_kind, args.new_code)
    patched_bytes = apply_instant_text_hack(patched_bytes)
    new_opcode = bytearray(old_opcode)
    if args.new_kind is not None:
        new_opcode[0] = args.new_kind
    if args.new_code is not None:
        new_opcode[1] = args.new_code

    output_pos_exe = args.output_pos_exe
    output_hdi = args.output_hdi
    if output_pos_exe is None or output_hdi is None:
        default_pos_exe, default_hdi = default_output_paths(root, args.handoff_loc, args.new_kind, args.new_code)
        if output_pos_exe is None:
            output_pos_exe = default_pos_exe
        if output_hdi is None:
            output_hdi = default_hdi

    if not output_pos_exe.is_absolute():
        output_pos_exe = root / output_pos_exe
    if not output_hdi.is_absolute():
        output_hdi = root / output_hdi

    source_hdi = args.source_hdi
    if not source_hdi.is_absolute():
        source_hdi = root / source_hdi
    emulator_path = args.emulator
    if not emulator_path.is_absolute():
        emulator_path = root / emulator_path

    print(
        f"Patching handoff at {hex5(args.handoff_loc)}: "
        f"{old_opcode.hex(' ')} -> {bytes(new_opcode).hex(' ')}"
    )
    existing = describe_handoff_location(root, pos_exe_path, args.handoff_loc)
    if existing is not None:
        print(f"Current destination: {existing['destination_label']}")
        if existing["row_matches"]:
            for match in existing["row_matches"]:
                label = match["block_command"] or match["command"] or "(no command)"
                print(f"Owner: {match['file']} {hex5(match['offset'])} | {label}")
    print(f"Source POS.EXE: {pos_exe_path}")
    print("Extra patch: instant text hack applied at 0x0a3bf")
    print(f"Output POS.EXE: {output_pos_exe}")

    if args.write_pos_only:
        print("Mode: write-pos-only")
    else:
        print(f"Source HDI: {source_hdi}")
        print(f"Output HDI: {output_hdi}")
        print("Mode: in-place-hdi" if args.in_place_hdi else "Mode: copy source-hdi to scratch HDI")
        print(
            "Note: do not load old emulator save states while testing this scratch HDI. "
            "Save states restore full machine RAM and can mix data from a different build."
        )

    if args.dry_run:
        return

    ensure_parent_dir(output_pos_exe)
    write_pos_exe(root, output_pos_exe, patched_bytes)
    print(f"Wrote patched POS.EXE to {output_pos_exe}")

    if not args.write_pos_only:
        if args.in_place_hdi:
            ensure_parent_dir(output_hdi)
            if output_hdi != source_hdi and not output_hdi.exists():
                copy_disk_image(source_hdi, output_hdi)
        else:
            copy_disk_image(source_hdi, output_hdi)
        insert_pos_exe_into_disk(output_hdi, output_pos_exe)
        print(f"Inserted patched POS.EXE into {output_hdi}")

        if args.launch:
            process = launch_emulator(emulator_path, output_hdi)
            print(f"Launched emulator PID={process.pid}")
            if args.keys:
                send_keys_with_pywinauto(process, args.keys, args.launch_delay)


if __name__ == "__main__":
    main()
