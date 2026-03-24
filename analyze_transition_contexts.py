from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any

from analyze_handoff_contexts import (
    SAVE_FORMAT_PATH,
    build_offset_to_rows,
    format_destination_label,
    load_dump_rows,
    load_map_names,
)
from rominfo import DUMP_XLS_PATH, MSD_POINTER_RANGES, ORIGINAL_ROM_DIR


def hex5(value: int | None) -> str | None:
    if value is None:
        return None
    return f"0x{value:05x}"


def find_preceding_text_opcode(
    data: bytes,
    transition_location: int,
    offset_to_rows: dict[int, list[dict[str, Any]]],
    max_distance: int = 8,
) -> dict[str, int] | None:
    candidates: list[dict[str, int]] = []
    for start in range(transition_location - 1, max(-1, transition_location - max_distance - 1), -1):
        if start < 0 or start + 3 >= len(data):
            continue
        if data[start] == 0x02 and data[start + 1] != 0xFF and start + 4 <= transition_location:
            candidates.append(
                {
                    "opcode_location": start,
                    "text_offset": data[start + 1] | (data[start + 2] << 8),
                    "arg": data[start + 3],
                    "delta": transition_location - start,
                }
            )

    if not candidates:
        return None

    candidates.sort(
        key=lambda item: (
            0 if item["text_offset"] in offset_to_rows else 1,
            item["delta"],
        )
    )
    return candidates[0]


def scan_transitions(
    data: bytes,
    offset_to_rows: dict[int, list[dict[str, Any]]],
    map_names: dict[int, str],
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    seen_locations: set[int] = set()
    for filename, ranges in MSD_POINTER_RANGES.items():
        for start, stop in ranges:
            for location in range(max(0, start), min(stop, len(data) - 4) + 1):
                if location in seen_locations:
                    continue
                if data[location] != 0x01 or data[location + 2] != 0x00 or data[location + 3] != 0xFF:
                    continue
                if data[location + 1] not in map_names:
                    continue

                preceding_text = find_preceding_text_opcode(data, location, offset_to_rows)
                row_matches = (
                    [
                        row
                        for row in offset_to_rows.get(preceding_text["text_offset"], [])
                        if row["file"] == filename
                    ]
                    if preceding_text
                    else []
                )
                results.append(
                    {
                        "file": filename,
                        "location": location,
                        "arg1": data[location + 1],
                        "destination_name": map_names.get(data[location + 1]),
                        "destination_label": format_destination_label(data[location + 1], map_names.get(data[location + 1])),
                        "preceding_text": preceding_text,
                        "row_matches": row_matches,
                        "window": data[max(0, location - 16) : min(len(data), location + 24)].hex(" "),
                    }
                )
                seen_locations.add(location)
    return results


def human_report(results: list[dict[str, Any]]) -> str:
    lines: list[str] = []
    lines.append(f"Total 01 xx 00 ff occurrences: {len(results)}")
    lines.append("")

    arg_counts = Counter(item["arg1"] for item in results)
    lines.append("Arg1 distribution:")
    for arg1, count in sorted(arg_counts.items()):
        lines.append(f"  0x{arg1:02x}: {count}")
    lines.append("")

    lines.append("Occurrences:")
    for item in results:
        lines.append(f"{item['file']} {hex5(item['location'])}: 01 0x{item['arg1']:02x} 00 ff")
        lines.append(f"  Destination: {item['destination_label']}")
        preceding_text = item["preceding_text"]
        if preceding_text is not None:
            lines.append(
                f"  Preceding text: {hex5(preceding_text['opcode_location'])} -> "
                f"{hex5(preceding_text['text_offset'])} arg={preceding_text['arg']} "
                f"(delta={preceding_text['delta']})"
            )
        else:
            lines.append("  Preceding text: none within scan window")

        if item["row_matches"]:
            for match in item["row_matches"]:
                label = match["block_command"] or match["command"] or "(no command)"
                lines.append(f"  Workbook: {match['file']} {hex5(match['offset'])} -> {label}")
                if match["english"]:
                    lines.append(f"    English: {match['english']}")
        else:
            lines.append("  Workbook: no resolved row")
        lines.append(f"  Raw window: {item['window']}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def json_ready(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    payload = []
    for item in results:
        entry = {
            "file": item["file"],
            "location": hex5(item["location"]),
            "arg1": f"0x{item['arg1']:02x}",
            "destination_name": item["destination_name"],
            "destination_label": item["destination_label"],
            "row_matches": [
                {
                    "file": match["file"],
                    "offset": hex5(match["offset"]),
                    "command": match["command"],
                    "block_command": match["block_command"],
                    "english": match["english"],
                }
                for match in item["row_matches"]
            ],
            "window": item["window"],
        }
        if item["preceding_text"] is not None:
            entry["preceding_text"] = {
                "opcode_location": hex5(item["preceding_text"]["opcode_location"]),
                "text_offset": hex5(item["preceding_text"]["text_offset"]),
                "arg": item["preceding_text"]["arg"],
                "delta": item["preceding_text"]["delta"],
            }
        payload.append(entry)
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description="Analyze the 01 xx 00 ff room-transition opcode family.")
    parser.add_argument("--json", action="store_true", help="Emit JSON instead of human-readable output")
    args = parser.parse_args()

    rows_by_file_offset = load_dump_rows(Path(DUMP_XLS_PATH))
    offset_to_rows = build_offset_to_rows(rows_by_file_offset)
    map_names = load_map_names(SAVE_FORMAT_PATH)
    pos_exe = (Path(ORIGINAL_ROM_DIR) / "POS.EXE").read_bytes()
    results = scan_transitions(pos_exe, offset_to_rows, map_names)

    if args.json:
        print(json.dumps(json_ready(results), indent=2))
    else:
        print(human_report(results))


if __name__ == "__main__":
    main()
