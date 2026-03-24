from __future__ import annotations

import argparse
from pathlib import Path

from experiment_text_arg import (
    apply_instant_text_hack,
    copy_disk_image,
    ensure_parent_dir,
    insert_pos_exe_into_disk,
    launch_emulator,
    send_keys_with_pywinauto,
    write_pos_exe,
)
from rominfo import ORIGINAL_ROM_DIR, ORIGINAL_ROM_PATH

DEFAULT_SOURCE_POS_EXE = Path(ORIGINAL_ROM_DIR) / "POS.EXE"
DEFAULT_EMULATOR_PATH = Path(r"D:\Code\roms\romtools\np2debug\np21debug_x64.exe")


def parse_int(value: str) -> int:
    return int(str(value), 0)


def hex5(value: int) -> str:
    return f"0x{value:05x}"


def parse_patch(spec: str) -> tuple[int, bytes]:
    try:
        offset_text, byte_text = spec.split(":", 1)
    except ValueError as exc:
        raise SystemExit(f"Patch must be OFFSET:HEXBYTES, got {spec!r}") from exc

    offset = parse_int(offset_text)
    cleaned = byte_text.replace(" ", "").replace(",", "").replace("_", "")
    if cleaned.startswith("0x"):
        cleaned = cleaned[2:]
    if len(cleaned) == 0 or len(cleaned) % 2 != 0:
        raise SystemExit(f"Patch bytes must contain an even number of hex digits, got {byte_text!r}")
    try:
        patch_bytes = bytes.fromhex(cleaned)
    except ValueError as exc:
        raise SystemExit(f"Invalid patch byte string {byte_text!r}") from exc
    return offset, patch_bytes


def apply_patches(pos_exe_bytes: bytes, patches: list[tuple[int, bytes]]) -> tuple[bytes, list[tuple[int, bytes, bytes]]]:
    patched = bytearray(pos_exe_bytes)
    summaries: list[tuple[int, bytes, bytes]] = []
    for offset, patch_bytes in patches:
        end = offset + len(patch_bytes)
        if offset < 0 or end > len(patched):
            raise SystemExit(f"Patch {hex5(offset)} length {len(patch_bytes)} is out of range for POS.EXE")
        old_bytes = bytes(patched[offset:end])
        patched[offset:end] = patch_bytes
        summaries.append((offset, old_bytes, patch_bytes))
    return bytes(patched), summaries


def default_output_paths(root: Path, patches: list[tuple[int, bytes]]) -> tuple[Path, Path]:
    slug_bits = ["pos-bytes"]
    for offset, patch_bytes in patches[:3]:
        slug_bits.append(f"{offset:05x}-{patch_bytes.hex()}")
    slug = "-".join(slug_bits)
    output_dir = root / "patched" / "byte-experiments"
    return (
        output_dir / f"POS-{slug}.EXE",
        output_dir / f"Possessioner-{slug}.hdi",
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Patch arbitrary POS.EXE bytes into a scratch HDI for emulator testing."
    )
    parser.add_argument(
        "--patch",
        action="append",
        required=True,
        help="Patch specification OFFSET:HEXBYTES, e.g. 0x0f06d:01020304",
    )
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
    args = parser.parse_args()

    root = Path(__file__).resolve().parent
    pos_exe_path = args.source_pos_exe
    if not pos_exe_path.is_absolute():
        pos_exe_path = root / pos_exe_path
    source_hdi = args.source_hdi
    if not source_hdi.is_absolute():
        source_hdi = root / source_hdi
    emulator_path = args.emulator
    if not emulator_path.is_absolute():
        emulator_path = root / emulator_path

    patches = [parse_patch(spec) for spec in args.patch]
    pos_exe_bytes = pos_exe_path.read_bytes()
    patched_bytes, summaries = apply_patches(pos_exe_bytes, patches)
    patched_bytes = apply_instant_text_hack(patched_bytes)

    output_pos_exe = args.output_pos_exe
    output_hdi = args.output_hdi
    if output_pos_exe is None or output_hdi is None:
        default_pos_exe, default_hdi = default_output_paths(root, patches)
        if output_pos_exe is None:
            output_pos_exe = default_pos_exe
        if output_hdi is None:
            output_hdi = default_hdi

    if not output_pos_exe.is_absolute():
        output_pos_exe = root / output_pos_exe
    if not output_hdi.is_absolute():
        output_hdi = root / output_hdi

    print(f"Source POS.EXE: {pos_exe_path}")
    print("Extra patch: instant text hack applied at 0x0a3bf")
    print("Byte patches:")
    for offset, old_bytes, new_bytes in summaries:
        print(f"  {hex5(offset)}: {old_bytes.hex(' ')} -> {new_bytes.hex(' ')}")
    print(f"Output POS.EXE: {output_pos_exe}")
    if not args.write_pos_only:
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
