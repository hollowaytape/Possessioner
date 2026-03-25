from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path

from PIL import Image

from experiment_emulator_route import DEFAULT_EMULATOR_PATH, DEFAULT_HDI_PATH, content_region
from romtools.disk import Disk

DEFAULT_SAVE_PATH = Path("patched") / "DATA1.SLD"
DEFAULT_MAPS_PATH = Path("docs") / "save_format.txt"
DEFAULT_ASSET_ROOT = Path("script_viewer") / "assets"
AUTOEXEC_CONTENT = "@ECHO OFF\r\nCD \\PSSR\r\nPOSSTART\r\n"

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
    lines = save_format_path.read_text(encoding="utf-8").splitlines()
    entries: list[MapEntry] = []
    map_line = re.compile(r"^\s*\*\s*([0-9a-fA-F]{2}):\s*(.+?)\s*$")
    for line in lines:
        if line.startswith("02-100?"):
            break
        match = map_line.match(line)
        if not match:
            continue
        map_id = int(match.group(1), 16)
        label = match.group(2)
        lowered = label.lower()
        unsafe = any(marker in lowered for marker in UNSAFE_MARKERS)
        entries.append(MapEntry(map_id=map_id, label=label, slug=slugify(label), unsafe=unsafe))
    return entries


def patch_save_map(save_path: Path, map_id: int, output_path: Path, clear_flags: bool = False) -> None:
    data = bytearray(save_path.read_bytes())
    data[0] = map_id & 0xFF
    if clear_flags and len(data) >= 0x100:
        data[0x02:0x100] = b"\x00" * (0x100 - 0x02)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(data)


def copy_disk_image(source_hdi: Path, output_hdi: Path) -> None:
    output_hdi.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source_hdi, output_hdi)


def insert_file_into_disk(output_hdi: Path, source_path: Path, disk_name: str, path_in_disk: str = "PSSR\\") -> None:
    disk = Disk(str(output_hdi))
    staged_path = source_path
    cleanup = False
    if source_path.name.upper() != disk_name.upper():
        staged_path = source_path.with_name(disk_name)
        shutil.copy2(source_path, staged_path)
        cleanup = True
    try:
        disk.insert(str(staged_path), path_in_disk=path_in_disk)
    finally:
        if cleanup and staged_path.exists():
            staged_path.unlink()


def prepare_autoexec(scratch_root: Path, scratch_hdi: Path) -> None:
    autoexec_path = scratch_root / "AUTOEXEC.BAT"
    autoexec_path.write_text(AUTOEXEC_CONTENT, encoding="ascii")
    insert_file_into_disk(scratch_hdi, autoexec_path, "AUTOEXEC.BAT", path_in_disk="")


def partition_entries(entries: list[MapEntry], workers: int) -> list[list[MapEntry]]:
    if workers <= 1:
        return [entries]
    chunk_count = min(workers, len(entries))
    return [entries[index::chunk_count] for index in range(chunk_count)]


def collect_source_saves(source_save: Path, patch_all_saves: bool) -> list[Path]:
    if not patch_all_saves:
        return [source_save]
    if not re.fullmatch(r"DATA\d+\.SLD", source_save.name, flags=re.IGNORECASE):
        return [source_save]
    matches = sorted(source_save.parent.glob("DATA*.SLD"))
    return matches or [source_save]


def relative_path(path: Path, root: Path) -> str:
    return str(path.relative_to(root)).replace("\\", "/")


def run_capture(
    *,
    repo_root: Path,
    emulator_path: Path,
    scratch_hdi: Path,
    file_index: int,
    load_state: int | None,
    startup_delay: float,
    post_enter_count: int,
    post_space_count: int,
    post_focus_left_click_count: int,
    raw_output: Path,
    close_existing: bool,
) -> None:
    command = [
        sys.executable,
        str(repo_root / "experiment_emulator_route.py"),
        "--emulator",
        str(emulator_path),
        "--hdi",
        str(scratch_hdi),
        "--route",
        "load-only",
        "--file-index",
        str(file_index),
        "--output",
        str(raw_output),
        "--close",
    ]
    if load_state is not None:
        command.extend(["--load-state", str(load_state)])
    command.extend(["--startup-delay", str(startup_delay)])
    if post_enter_count:
        command.extend(["--post-enter-count", str(post_enter_count)])
    if post_space_count:
        command.extend(["--post-space-count", str(post_space_count)])
    if post_focus_left_click_count:
        command.extend(["--post-focus-left-click-count", str(post_focus_left_click_count)])
    if close_existing:
        command.append("--close-existing")
    subprocess.run(command, cwd=str(repo_root), check=True)


def crop_capture(raw_output: Path, final_output: Path) -> tuple[int, int]:
    with Image.open(raw_output) as image:
        cropped = content_region(image)
        final_output.parent.mkdir(parents=True, exist_ok=True)
        cropped.save(final_output)
        return cropped.size


def capture_chunk(
    *,
    worker_index: int,
    entries: list[MapEntry],
    repo_root: Path,
    source_hdi: Path,
    source_saves: list[Path],
    file_index: int,
    load_state: int | None,
    startup_delay: float,
    post_enter_count: int,
    post_space_count: int,
    post_focus_left_click_count: int,
    clear_flags: bool,
    asset_root: Path,
    close_existing: bool,
    keep_raw: bool,
    emulator_path: Path,
) -> list[dict[str, object]]:
    scratch_root = repo_root / "patched" / "viewer-assets" / f"worker-{worker_index:02d}"
    scratch_hdi = scratch_root / "Possessioner.hdi"
    raw_dir = scratch_root / "raw"
    final_dir = asset_root / "locations"

    copy_disk_image(source_hdi, scratch_hdi)
    prepare_autoexec(scratch_root, scratch_hdi)
    results: list[dict[str, object]] = []

    for entry in entries:
        raw_output = raw_dir / f"{entry.map_id:02x}-{entry.slug}.png"
        final_output = final_dir / f"{entry.map_id:02x}-{entry.slug}.png"
        patched_save_names: list[str] = []
        for source_save in source_saves:
            working_save = scratch_root / source_save.name
            patch_save_map(source_save, entry.map_id, working_save, clear_flags=clear_flags)
            insert_file_into_disk(scratch_hdi, working_save, source_save.name.upper())
            patched_save_names.append(source_save.name)
        run_capture(
            repo_root=repo_root,
            emulator_path=emulator_path,
            scratch_hdi=scratch_hdi,
            file_index=file_index,
            load_state=load_state,
            startup_delay=startup_delay,
            post_enter_count=post_enter_count,
            post_space_count=post_space_count,
            post_focus_left_click_count=post_focus_left_click_count,
            raw_output=raw_output,
            close_existing=close_existing and not results,
        )
        cropped_size = crop_capture(raw_output, final_output)
        if not keep_raw and raw_output.exists():
            raw_output.unlink()
        results.append(
            {
                "map_id": entry.map_id,
                "map_hex": f"0x{entry.map_id:02x}",
                "label": entry.label,
                "slug": entry.slug,
                "unsafe": entry.unsafe,
                "image": relative_path(final_output, repo_root),
                "size": {"width": cropped_size[0], "height": cropped_size[1]},
                "save_files": patched_save_names,
                "file_index": file_index,
                "load_state": load_state,
                "startup_delay": startup_delay,
                "post_enter_count": post_enter_count,
                "post_space_count": post_space_count,
                "post_focus_left_click_count": post_focus_left_click_count,
                "clear_flags": clear_flags,
            }
        )
    return results


def select_entries(entries: list[MapEntry], requested_maps: list[int] | None, include_unsafe: bool) -> list[MapEntry]:
    selected = entries
    if requested_maps:
        requested = set(requested_maps)
        selected = [entry for entry in entries if entry.map_id in requested]
    if not include_unsafe:
        selected = [entry for entry in selected if not entry.unsafe]
    return selected


def parse_int(value: str) -> int:
    return int(str(value), 0)


def main() -> None:
    parser = argparse.ArgumentParser(description="Capture location screenshots for the script viewer by patching DATA*.SLD map bytes.")
    parser.add_argument("--emulator", type=Path, default=DEFAULT_EMULATOR_PATH)
    parser.add_argument("--source-hdi", type=Path, default=DEFAULT_HDI_PATH)
    parser.add_argument("--source-save", type=Path, default=DEFAULT_SAVE_PATH)
    parser.add_argument("--patch-all-saves", action="store_true", help="Patch every sibling DATA*.SLD save alongside --source-save")
    parser.add_argument("--clear-flags", action="store_true", help="Zero the save event-flag block (0x02-0xFF) after setting the map byte")
    parser.add_argument("--maps-file", type=Path, default=DEFAULT_MAPS_PATH)
    parser.add_argument("--asset-root", type=Path, default=DEFAULT_ASSET_ROOT)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_ASSET_ROOT / "locations" / "manifest.json")
    parser.add_argument("--file-index", type=int, default=0, help="Zero-based save slot index on the load menu")
    parser.add_argument("--load-state", type=int, help="Optional emulator save-state slot to load before opening the in-game load menu")
    parser.add_argument("--startup-delay", type=float, default=22.0, help="Seconds to wait for the scratch HDI to boot into the game")
    parser.add_argument("--post-enter-count", type=int, default=0, help="Press Enter this many times after loading the save")
    parser.add_argument("--post-space-count", type=int, default=0, help="Press Space this many times after loading the save")
    parser.add_argument(
        "--post-focus-left-click-count",
        type=int,
        default=0,
        help="Middle-click to focus and left-click this many times after loading the save",
    )
    parser.add_argument("--map", dest="maps", action="append", type=parse_int, help="Specific map id(s) to capture, e.g. --map 0x11")
    parser.add_argument("--include-unsafe", action="store_true", help="Include maps labeled freeze/crash/glitch in docs\\save_format.txt")
    parser.add_argument("--workers", type=int, default=1, help="Parallel emulator workers; each gets its own scratch HDI")
    parser.add_argument("--keep-raw", action="store_true", help="Keep uncropped emulator window screenshots in patched\\viewer-assets")
    parser.add_argument("--close-existing", action="store_true", help="Close existing emulator windows before each capture worker launches")
    args = parser.parse_args()

    if args.workers < 1:
        raise SystemExit("--workers must be 1 or greater")
    if args.close_existing and args.workers > 1:
        raise SystemExit("--close-existing is only safe with --workers 1")

    repo_root = Path(__file__).resolve().parent
    source_hdi = args.source_hdi if args.source_hdi.is_absolute() else repo_root / args.source_hdi
    source_save = args.source_save if args.source_save.is_absolute() else repo_root / args.source_save
    source_saves = collect_source_saves(source_save, args.patch_all_saves)
    maps_file = args.maps_file if args.maps_file.is_absolute() else repo_root / args.maps_file
    asset_root = args.asset_root if args.asset_root.is_absolute() else repo_root / args.asset_root
    manifest_path = args.manifest if args.manifest.is_absolute() else repo_root / args.manifest
    emulator_path = args.emulator if args.emulator.is_absolute() else repo_root / args.emulator

    entries = parse_maps(maps_file)
    selected = select_entries(entries, args.maps, args.include_unsafe)
    if not selected:
        raise SystemExit("No maps selected for capture")

    chunks = partition_entries(selected, min(args.workers, len(selected)))
    results: list[dict[str, object]] = []

    with ThreadPoolExecutor(max_workers=len(chunks)) as executor:
        futures = [
            executor.submit(
                capture_chunk,
                worker_index=index,
                entries=chunk,
                repo_root=repo_root,
                source_hdi=source_hdi,
                source_saves=source_saves,
                file_index=args.file_index,
                load_state=args.load_state,
                startup_delay=args.startup_delay,
                post_enter_count=args.post_enter_count,
                post_space_count=args.post_space_count,
                post_focus_left_click_count=args.post_focus_left_click_count,
                clear_flags=args.clear_flags,
                asset_root=asset_root,
                close_existing=args.close_existing,
                keep_raw=args.keep_raw,
                emulator_path=emulator_path,
            )
            for index, chunk in enumerate(chunks, start=1)
            if chunk
        ]
        for future in as_completed(futures):
            results.extend(future.result())

    results.sort(key=lambda row: int(row["map_id"]))
    manifest = {
        "save_files": [path.name for path in source_saves],
        "file_index": args.file_index,
        "workers": len(chunks),
        "captured_count": len(results),
        "clear_flags": args.clear_flags,
        "locations": results,
    }
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    print(f"Captured {len(results)} location assets")
    print(f"Manifest: {manifest_path}")


if __name__ == "__main__":
    main()
