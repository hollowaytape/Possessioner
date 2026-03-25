from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from experiment_text_arg import apply_instant_text_hack
from romtools.disk import Disk

DEFAULT_HDI_PATH = Path("patched") / "Possessioner.hdi"
DEFAULT_POS_EXE_PATH = Path("patched") / "POS.EXE"
DEFAULT_MAPS_PATH = Path("docs") / "save_format.txt"
DEFAULT_ASSET_ROOT = Path("script_viewer") / "assets"
MOVE_PATCH_OFFSETS = (0x0F3DE, 0x10039)
UNSAFE_MARKERS = ("freeze", "crash", "glitch")


@dataclass(frozen=True)
class MapEntry:
    map_id: int
    label: str
    slug: str
    unsafe: bool


def slugify(value: str) -> str:
    lowered = value.lower()
    lowered = lowered.replace('"', "")
    lowered = lowered.replace("'", "")
    lowered = re.sub(r"[^a-z0-9]+", "-", lowered)
    return lowered.strip("-") or "map"


def parse_maps(save_format_path: Path) -> list[MapEntry]:
    entries: list[MapEntry] = []
    line_re = re.compile(r"^\s*\*\s*([0-9a-fA-F]{2}):\s*(.+?)\s*$")
    for line in save_format_path.read_text(encoding="utf-8").splitlines():
        if line.startswith("02-100?"):
            break
        match = line_re.match(line)
        if not match:
            continue
        map_id = int(match.group(1), 16)
        label = match.group(2)
        lowered = label.lower()
        entries.append(
            MapEntry(
                map_id=map_id,
                label=label,
                slug=slugify(label),
                unsafe=any(marker in lowered for marker in UNSAFE_MARKERS),
            )
        )
    return entries


def parse_int(value: str) -> int:
    return int(str(value), 0)


def select_entries(entries: list[MapEntry], requested_maps: list[int] | None, include_unsafe: bool) -> list[MapEntry]:
    selected = entries
    if requested_maps:
        wanted = set(requested_maps)
        selected = [entry for entry in entries if entry.map_id in wanted]
    if not include_unsafe:
        selected = [entry for entry in selected if not entry.unsafe]
    return selected


def patch_move_redirect(pos_exe_bytes: bytes, map_id: int) -> bytes:
    patched = bytearray(apply_instant_text_hack(pos_exe_bytes))
    opcode = bytes((0x01, map_id & 0xFF, 0x00, 0xFF))
    for offset in MOVE_PATCH_OFFSETS:
        patched[offset : offset + 4] = opcode
    return bytes(patched)


def insert_pos_exe_into_hdi(hdi_path: Path, pos_exe_path: Path) -> None:
    disk = Disk(str(hdi_path))
    staged_path = pos_exe_path
    cleanup = False
    if pos_exe_path.name.upper() != "POS.EXE":
        staged_path = pos_exe_path.with_name("POS.EXE")
        shutil.copy2(pos_exe_path, staged_path)
        cleanup = True
    try:
        disk.insert(str(staged_path), path_in_disk="PSSR\\")
    finally:
        if cleanup and staged_path.exists():
            staged_path.unlink()


def run_route(repo_root: Path, hdi_path: Path, output_path: Path, trace_dir: Path | None, close_existing: bool) -> None:
    command = [
        sys.executable,
        str(repo_root / "experiment_emulator_route.py"),
        "--hdi",
        str(hdi_path),
        "--load-state",
        "0",
        "--file-index",
        "2",
        "--step",
        "0:0:1",
        "--output",
        str(output_path),
        "--close",
    ]
    if trace_dir is not None:
        command.extend(["--trace-dir", str(trace_dir)])
    if close_existing:
        command.append("--close-existing")
    subprocess.run(command, cwd=str(repo_root), check=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="Capture location scenes by redirecting the validated P_HON1 move route.")
    parser.add_argument("--hdi", type=Path, default=DEFAULT_HDI_PATH)
    parser.add_argument("--pos-exe", type=Path, default=DEFAULT_POS_EXE_PATH)
    parser.add_argument("--maps-file", type=Path, default=DEFAULT_MAPS_PATH)
    parser.add_argument("--asset-root", type=Path, default=DEFAULT_ASSET_ROOT)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_ASSET_ROOT / "locations" / "phon1-manifest.json")
    parser.add_argument("--map", dest="maps", action="append", type=parse_int, help="Specific map id(s) to capture, e.g. --map 0x50")
    parser.add_argument("--include-unsafe", action="store_true", help="Include freeze/crash/glitch rows from docs\\save_format.txt")
    parser.add_argument("--trace-root", type=Path, help="Optional trace directory root for intermediate route screenshots")
    parser.add_argument("--close-existing", action="store_true", help="Close existing emulator windows before the first run")
    parser.add_argument("--continue-on-error", action="store_true", help="Record failed destinations and continue batching")
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parent
    hdi_path = args.hdi if args.hdi.is_absolute() else repo_root / args.hdi
    pos_exe_path = args.pos_exe if args.pos_exe.is_absolute() else repo_root / args.pos_exe
    maps_path = args.maps_file if args.maps_file.is_absolute() else repo_root / args.maps_file
    asset_root = args.asset_root if args.asset_root.is_absolute() else repo_root / args.asset_root
    manifest_path = args.manifest if args.manifest.is_absolute() else repo_root / args.manifest
    trace_root = None if args.trace_root is None else (args.trace_root if args.trace_root.is_absolute() else repo_root / args.trace_root)

    entries = select_entries(parse_maps(maps_path), args.maps, args.include_unsafe)
    if not entries:
        raise SystemExit("No maps selected for capture")

    original_pos_bytes = pos_exe_path.read_bytes()
    temp_pos_path = repo_root / "patched" / "viewer-assets" / "redirected-POS.EXE"
    temp_pos_path.parent.mkdir(parents=True, exist_ok=True)

    results: list[dict[str, object]] = []
    failures: list[dict[str, object]] = []
    first_run = True
    try:
        for entry in entries:
            patched_bytes = patch_move_redirect(original_pos_bytes, entry.map_id)
            temp_pos_path.write_bytes(patched_bytes)
            insert_pos_exe_into_hdi(hdi_path, temp_pos_path)

            output_path = asset_root / "locations" / f"{entry.map_id:02x}-{entry.slug}-phon1.png"
            trace_dir = None if trace_root is None else trace_root / f"{entry.map_id:02x}-{entry.slug}"
            try:
                run_route(
                    repo_root,
                    hdi_path,
                    output_path,
                    trace_dir,
                    close_existing=args.close_existing and first_run,
                )
                results.append(
                    {
                        "map_id": entry.map_id,
                        "map_hex": f"0x{entry.map_id:02x}",
                        "label": entry.label,
                        "slug": entry.slug,
                        "unsafe": entry.unsafe,
                        "image": str(output_path.relative_to(repo_root)).replace("\\", "/"),
                        "route": {
                            "file_index": 2,
                            "step": "0:0:1",
                            "patch_offsets": [f"0x{offset:05x}" for offset in MOVE_PATCH_OFFSETS],
                        },
                    }
                )
            except subprocess.CalledProcessError as exc:
                failure = {
                    "map_id": entry.map_id,
                    "map_hex": f"0x{entry.map_id:02x}",
                    "label": entry.label,
                    "slug": entry.slug,
                    "unsafe": entry.unsafe,
                    "error": str(exc),
                }
                failures.append(failure)
                if not args.continue_on_error:
                    raise
            finally:
                first_run = False
    finally:
        pos_exe_path.write_bytes(original_pos_bytes)
        insert_pos_exe_into_hdi(hdi_path, pos_exe_path)

    manifest = {
        "method": "phon1-move-redirect",
        "captured_count": len(results),
        "failed_count": len(failures),
        "locations": results,
        "failures": failures,
    }
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"Captured {len(results)} redirected location scenes")
    if failures:
        print(f"Failed {len(failures)} redirected location scenes")
    print(f"Manifest: {manifest_path}")


if __name__ == "__main__":
    main()
import shutil
