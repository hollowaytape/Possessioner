from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path

import regex as re

from romtools.disk import Gamefile
from romtools.dump import DumpExcel
from msd_utils import normalize_msd_row_offset
from pointer_selection import (
    ALLOWED_MSD_PRECEDING_BYTES,
    PointerCandidate,
    add_candidate,
    choose_best_pointer_location,
    score_candidates_for_text,
)

from rominfo import (
    ARRIVAL_POINTERS,
    DUMP_XLS_PATH,
    EXTRA_POINTERS,
    FILES,
    FILES_TO_REINSERT,
    FILE_BLOCKS,
    MSD_POINTER_RANGES,
    POINTER_CONSTANT,
    POINTER_DISAMBIGUATION,
    POINTER_TABLES,
    POINTER_TABLE_SEPARATOR,
    SKIP_TARGET_AREAS,
)


POINTER_REGEX = r"\\xbe\\x([0-f][0-f])\\x([0-f][0-f])\\xe8"
POINTER_REGEX_2 = r"\\xbe\\x([0-f][0-f])\\x([0-f][0-f])\\xbf"
MSD_POINTER_REGEX = r"\\x02\\x([0-f][0-f])\\x([0-f][0-f])\\x([0-f][0-f])"
MSD_POINTER_REGEX_2 = r"\\xbe\\x([0-f][0-f])\\x([0-f][0-f])\\xb9"
TABLE_POINTER_REGEX = r"\\x([0-f][0-f])\\x([0-f][0-f])sep"

def unpack(s: str, t: str | None = None) -> int:
    if t is None:
        t = str(s)[2:]
        s = str(s)[:2]
    return (int(t, 16) * 0x100) + int(s, 16)


def location_from_pointer(pointer: tuple[str, str], constant: int) -> int:
    return unpack(pointer[0], pointer[1]) + constant


def capture_pointers_from_function(hx: str, pattern: str):
    return re.compile(pattern).finditer(hx, overlapped=True)


def to_hex_blob(data: bytes) -> str:
    return "".join(f"\\x{byte:02x}" for byte in data)


def build_target_locations(gamefile: str, dump: DumpExcel) -> tuple[list[int], list[int]]:
    if not gamefile.endswith(".MSD"):
        block_targets = []
        for start, end in FILE_BLOCKS[gamefile]:
            block_targets.extend(range(start, end + 1))
        return sorted(set(block_targets)), []

    all_targets = [t.location for t in dump.get_translations(gamefile, include_blank=True)]
    skipped = set(SKIP_TARGET_AREAS.get(gamefile, []))
    filtered_targets = [loc for loc in all_targets if loc not in skipped]
    important_targets = [
        t.location
        for t in dump.get_translations(gamefile, include_blank=True)
        if t.location > 0x0 and t.location not in skipped and t.command is not None and t.command != "?" and "unused" not in t.command
    ]
    return sorted(set(filtered_targets)), sorted(set(important_targets))


def build_disambiguation_maps() -> tuple[dict[tuple[str, int], int], set[tuple[str, int]]]:
    allowed: dict[tuple[str, int], int] = {}
    blocked: set[tuple[str, int]] = set()
    for filename, text_location, pointer_location in POINTER_DISAMBIGUATION:
        key = (filename, text_location)
        if pointer_location is None:
            blocked.add(key)
        else:
            allowed[key] = pointer_location
    return allowed, blocked


def scan_candidates(gamefile: str, dump: DumpExcel) -> dict[str, object]:
    is_msd = gamefile.endswith(".MSD")
    pointer_file_path = Path("original") / gamefile
    text_file_path = Path("original") / gamefile
    if is_msd:
        pointer_file_path = Path("original") / "POS.EXE"

    pointer_constant = POINTER_CONSTANT[gamefile]
    pointer_gamefile = Gamefile(str(pointer_file_path), pointer_constant=pointer_constant)
    text_gamefile = Gamefile(str(text_file_path), pointer_constant=pointer_constant)
    pointer_bytes = pointer_file_path.read_bytes()
    only_hex = to_hex_blob(pointer_bytes)
    target_locations, important_targets = build_target_locations(gamefile, dump)
    target_set = set(target_locations)
    important_set = set(important_targets)

    disambiguated_allowed, disambiguated_blocked = build_disambiguation_maps()
    candidate_map: dict[int, dict[int, PointerCandidate]] = {}
    reason_counts = Counter()

    def candidate_dicts_for(
        text_location: int,
        candidates: list[PointerCandidate],
        *,
        allowed_pointer_locations: set[int] | None = None,
    ) -> list[dict[str, object]]:
        score_entries = score_candidates_for_text(
            text_location,
            candidate_map,
            allowed_pointer_locations=allowed_pointer_locations,
        )
        scores_by_pointer = {
            entry["pointer_location"]: entry
            for entry in score_entries
        }
        candidate_dicts = []
        for candidate in sorted(candidates, key=lambda item: item.pointer_location):
            candidate_dict = candidate.to_dict()
            score_entry = scores_by_pointer.get(candidate.pointer_location)
            if score_entry is not None:
                candidate_dict["auto_score"] = score_entry["score"]
                candidate_dict["auto_score_reasons"] = score_entry["reasons"]
                candidate_dict["pointer_neighbors"] = score_entry["pointer_neighbors"]
                candidate_dict["coherent_neighbors"] = score_entry["coherent_neighbors"]
                candidate_dict["incoherent_neighbors"] = score_entry["incoherent_neighbors"]
                candidate_dict["exact_pointer_reuse"] = score_entry["exact_pointer_reuse"]
            candidate_dicts.append(candidate_dict)
        return candidate_dicts

    def add(
        *,
        text_location: int,
        pointer_location: int,
        family: str,
        chain_length: int | None = None,
        preceding_byte: int | None = None,
    ) -> None:
        if is_msd:
            text_location = normalize_msd_row_offset(text_location, target_set, text_gamefile.filestring)
        within_targets = text_location in target_set
        if not within_targets:
            reason_counts["outside_target_set"] += 1
            return

        in_msd_range: bool | None = None
        before_be_prefix = pointer_location > 0 and pointer_bytes[pointer_location - 1] == 0xBE
        preceding_byte_allowed: bool | None = None
        if family == "msd-regex" and gamefile in MSD_POINTER_RANGES:
            in_msd_range = any(start <= pointer_location <= end for start, end in MSD_POINTER_RANGES[gamefile])
            preceding_byte_allowed = preceding_byte in ALLOWED_MSD_PRECEDING_BYTES if preceding_byte is not None else None

        add_candidate(
            candidate_map,
            text_location=text_location,
            pointer_location=pointer_location,
            family=family,
            chain_length=chain_length,
            within_targets=within_targets,
            in_msd_range=in_msd_range,
            before_be_prefix=before_be_prefix,
            preceding_byte=preceding_byte,
            preceding_byte_allowed=preceding_byte_allowed,
        )

    for start, stop in POINTER_TABLES.get(gamefile, []):
        cursor = start
        while cursor <= stop:
            text_location = (pointer_gamefile.filestring[cursor + 1] * 0x100) + pointer_gamefile.filestring[cursor] + pointer_constant
            add(text_location=text_location, pointer_location=cursor, family="plain-table")
            cursor += 2

    table_regex = None
    separator = POINTER_TABLE_SEPARATOR.get(gamefile)
    if separator:
        table_regex = TABLE_POINTER_REGEX.replace("sep", separator)

    regex_families: list[tuple[str, str | None]] = [
        ("borland-e8", POINTER_REGEX),
        ("borland-bf", POINTER_REGEX_2),
        ("msd-regex", MSD_POINTER_REGEX if gamefile.endswith(".MSD") else None),
        ("msd-be-b9", MSD_POINTER_REGEX_2 if gamefile.endswith(".MSD") else None),
        ("separated-table", table_regex),
    ]

    for family, pattern in regex_families:
        if pattern is None:
            continue
        for match in capture_pointers_from_function(only_hex, pattern):
            if family == "separated-table":
                pointer_location = match.start() // 4
            else:
                pointer_location = match.start() // 4 + 1
            text_location = location_from_pointer((match.group(1), match.group(2)), pointer_constant)
            chain_length = int(match.group(3), 16) if family == "msd-regex" else None
            preceding_byte = pointer_bytes[pointer_location - 1] if pointer_location > 0 else None
            add(
                text_location=text_location,
                pointer_location=pointer_location,
                family=family,
                chain_length=chain_length,
                preceding_byte=preceding_byte,
            )

    selected_by_text: dict[int, list[dict[str, object]]] = {}
    unresolved_due_to_disambiguation: list[str] = []
    filtered_reason_counts = Counter()
    shared_pointer_offsets: dict[int, list[int]] = defaultdict(list)
    unresolved_command_details: dict[str, dict[str, object]] = {}

    for text_location, by_pointer in sorted(candidate_map.items()):
        key = (gamefile, text_location)
        if key in disambiguated_blocked:
            unresolved_due_to_disambiguation.append(f"0x{text_location:05x}")
            filtered_reason_counts["blocked_by_disambiguation"] += 1
            continue

        candidates = list(by_pointer.values())
        if gamefile in MSD_POINTER_RANGES:
            filtered = [
                candidate
                for candidate in candidates
                if candidate.in_msd_range or candidate.before_be_prefix or "plain-table" in candidate.families or "separated-table" in candidate.families
            ]
            if filtered:
                candidates = filtered
            else:
                filtered_reason_counts["rejected_by_range_filter"] += 1
                continue

        if key in disambiguated_allowed:
            allowed_pointer = disambiguated_allowed[key]
            candidates = [candidate for candidate in candidates if candidate.pointer_location == allowed_pointer]
            if not candidates:
                filtered_reason_counts["missing_disambiguated_pointer"] += 1
                continue
        elif is_msd and len(candidates) > 1:
            auto_selected_pointer, _score_entries = choose_best_pointer_location(
                text_location,
                candidate_map,
                allowed_pointer_locations={candidate.pointer_location for candidate in candidates},
            )
            if auto_selected_pointer is not None:
                candidates = [candidate for candidate in candidates if candidate.pointer_location == auto_selected_pointer]
                filtered_reason_counts["auto_disambiguated"] += 1

        selected = []
        selected.extend(
            candidate_dicts_for(
                text_location,
                candidates,
                allowed_pointer_locations={candidate.pointer_location for candidate in candidates},
            )
        )
        for candidate in candidates:
            shared_pointer_offsets[candidate.pointer_location].append(text_location)
        if selected:
            selected_by_text[text_location] = selected

    for text_location, pointer_location in EXTRA_POINTERS.get(gamefile, []):
        selected_by_text.setdefault(text_location, []).append(
            {
                "pointer_location": f"0x{pointer_location:05x}",
                "text_location": f"0x{text_location:05x}",
                "families": ["extra-pointer"],
                "chain_lengths": [],
                "within_targets": True,
                "in_msd_range": None,
                "before_be_prefix": False,
                "preceding_byte": None,
                "preceding_byte_allowed": None,
                "sources": [{"family": "extra-pointer", "chain_length": None, "preceding_byte": None, "preceding_byte_allowed": None, "in_msd_range": None, "before_be_prefix": False}],
            }
        )

    for text_location, pointer_location in ARRIVAL_POINTERS.get(gamefile, []):
        selected_by_text.setdefault(text_location, []).append(
            {
                "pointer_location": f"0x{pointer_location:05x}",
                "text_location": f"0x{text_location:05x}",
                "families": ["arrival-pointer"],
                "chain_lengths": [],
                "within_targets": True,
                "in_msd_range": None,
                "before_be_prefix": False,
                "preceding_byte": None,
                "preceding_byte_allowed": None,
                "sources": [{"family": "arrival-pointer", "chain_length": None, "preceding_byte": None, "preceding_byte_allowed": None, "in_msd_range": None, "before_be_prefix": False}],
            }
        )

    selected_target_locations = set(selected_by_text.keys())
    unresolved_targets = sorted(target_set - selected_target_locations - {0x0}) if is_msd else []
    unresolved_important = sorted(important_set - selected_target_locations) if is_msd else []
    range_rejected_pointer_locations: list[int] = []
    for text_location in unresolved_important:
        key = (gamefile, text_location)
        detail: dict[str, object] = {"reason": "no-candidates", "candidates": []}
        if key in disambiguated_blocked:
            detail["reason"] = "blocked-by-disambiguation"
        elif text_location in candidate_map:
            candidates = candidate_dicts_for(
                text_location,
                list(candidate_map[text_location].values()),
            )
            detail["candidates"] = candidates
            if gamefile in MSD_POINTER_RANGES:
                if any(
                    candidate.in_msd_range or candidate.before_be_prefix or "plain-table" in candidate.families or "separated-table" in candidate.families
                    for candidate in candidate_map[text_location].values()
                ):
                    detail["reason"] = "unselected-after-filtering"
                else:
                    detail["reason"] = "rejected-by-range-filter"
                    range_rejected_pointer_locations.extend(candidate.pointer_location for candidate in candidate_map[text_location].values())
            else:
                detail["reason"] = "unselected-after-filtering"
        unresolved_command_details[f"0x{text_location:05x}"] = detail

    summary = {
        "is_msd": is_msd,
        "target_count": len(target_set) if is_msd else 0,
        "command_target_count": len(important_set) if is_msd else 0,
        "candidate_text_locations": len(candidate_map),
        "selected_text_locations": len(selected_by_text),
        "selected_pointer_count": sum(len(values) for values in selected_by_text.values()),
        "unresolved_target_count": len(unresolved_targets),
        "unresolved_command_target_count": len(unresolved_important),
        "blocked_by_disambiguation_count": len(unresolved_due_to_disambiguation),
        "auto_disambiguated_count": filtered_reason_counts["auto_disambiguated"],
        "raw_skip_counts": dict(reason_counts),
        "filtered_reason_counts": dict(filtered_reason_counts),
    }

    return {
        "summary": summary,
        "selected": {
            f"0x{text_location:05x}": pointers
            for text_location, pointers in sorted(selected_by_text.items())
        },
        "unresolved_targets": [f"0x{loc:05x}" for loc in unresolved_targets],
        "unresolved_command_targets": [f"0x{loc:05x}" for loc in unresolved_important],
        "blocked_by_disambiguation": unresolved_due_to_disambiguation,
        "unresolved_command_details": unresolved_command_details,
        "suggested_range_extensions": cluster_pointer_locations(range_rejected_pointer_locations) if is_msd else [],
        "shared_pointer_offsets": {
            f"0x{pointer_location:05x}": [f"0x{text_location:05x}" for text_location in sorted(text_locations)]
            for pointer_location, text_locations in sorted(shared_pointer_offsets.items())
            if len(text_locations) > 1
        },
    }


def build_inventory() -> dict[str, object]:
    dump = DumpExcel(DUMP_XLS_PATH)
    files = [filename for filename in FILES_TO_REINSERT if filename in FILES and not filename.endswith((".SEL", ".CGX"))]
    results = {}
    global_summary = {
        "files_scanned": 0,
        "selected_text_locations": 0,
        "selected_pointer_count": 0,
        "unresolved_target_count": 0,
        "unresolved_command_target_count": 0,
        "blocked_by_disambiguation_count": 0,
        "auto_disambiguated_count": 0,
    }

    for gamefile in files:
        file_result = scan_candidates(gamefile, dump)
        results[gamefile] = file_result
        summary = file_result["summary"]
        global_summary["files_scanned"] += 1
        global_summary["selected_text_locations"] += summary["selected_text_locations"]
        global_summary["selected_pointer_count"] += summary["selected_pointer_count"]
        global_summary["unresolved_target_count"] += summary["unresolved_target_count"]
        global_summary["unresolved_command_target_count"] += summary["unresolved_command_target_count"]
        global_summary["blocked_by_disambiguation_count"] += summary["blocked_by_disambiguation_count"]
        global_summary["auto_disambiguated_count"] += summary.get("auto_disambiguated_count", 0)

    return {
        "summary": global_summary,
        "files": results,
    }


def cluster_pointer_locations(pointer_locations: list[int], gap_limit: int = 0x40) -> list[dict[str, object]]:
    if not pointer_locations:
        return []
    sorted_locations = sorted(set(pointer_locations))
    groups: list[list[int]] = [[sorted_locations[0]]]
    for pointer_location in sorted_locations[1:]:
        if pointer_location - groups[-1][-1] <= gap_limit:
            groups[-1].append(pointer_location)
        else:
            groups.append([pointer_location])
    return [
        {
            "start": f"0x{group[0]:05x}",
            "end": f"0x{group[-1]:05x}",
            "count": len(group),
            "members": [f"0x{pointer_location:05x}" for pointer_location in group],
        }
        for group in groups
    ]


def print_summary(inventory: dict[str, object]) -> None:
    print("Pointer inventory summary")
    print(json.dumps(inventory["summary"], indent=2))
    print("")
    print("Files with unresolved command targets:")
    for filename, file_result in inventory["files"].items():
        unresolved = file_result["summary"]["unresolved_command_target_count"]
        if unresolved:
            print(f"  {filename}: {unresolved}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit pointer coverage and unresolved MSD text locations.")
    parser.add_argument("--output", type=Path, help="Optional JSON output path")
    args = parser.parse_args()

    inventory = build_inventory()
    if args.output:
        args.output.write_text(json.dumps(inventory, indent=2), encoding="utf-8")
        print(f"Wrote pointer inventory to {args.output}")
    print_summary(inventory)


if __name__ == "__main__":
    main()
