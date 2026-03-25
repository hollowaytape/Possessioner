from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from analyze_dispatch_contexts import (
    json_ready as dispatch_json_ready,
    load_dump_rows as load_dispatch_dump_rows,
    scan_dispatch_headers,
)
from analyze_flag_contexts import (
    json_ready as flag_json_ready,
    load_dump_rows as load_flag_dump_rows,
    scan_file_flags,
)
from analyze_handoff_contexts import (
    SAVE_FORMAT_PATH,
    build_offset_to_rows,
    json_ready as handoff_json_ready,
    load_dump_rows as load_handoff_dump_rows,
    load_map_names,
    scan_handoffs,
)
from analyze_msd_context import build_records, load_dump_rows, load_pointer_rows
from analyze_transition_contexts import json_ready as transition_json_ready, scan_transitions
from analyze_walkthrough_progression import build_report as build_walkthrough_report
from analyze_walkthrough_progression import parse_command as parse_walkthrough_command
from analyze_walkthrough_progression import step_matches_command
from build_command_matrix import build_command_matrix
from build_state_graph import build_graph
from build_trigger_model import (
    build_dispatch_lookup,
    build_flag_lookup,
    build_model,
    build_target_lookup,
    load_workbook_rows,
)
from build_walkthrough_acceptance import build_acceptance_outline
from rominfo import DUMP_XLS_PATH, MSD_POINTER_RANGES, ORIGINAL_ROM_DIR, POINTER_DUMP_XLS_PATH

VERB_ALIASES = {
    "TALK": "TALKED_TO",
    "LOOK": "LOOKED_AT",
    "EXAMINE": "EXAMINED",
    "THINK": "THOUGHT_ABOUT",
    "MOVE": "MOVED_TO",
    "TOUCH": "TOUCHED",
    "CARESS": "CARESSED",
    "PINCH": "PINCHED",
    "LICK": "LICKED",
    "KISS": "KISSED",
    "RUB": "RUBBED",
    "OPEN": "OPENED",
    "CHECK": "CHECKED",
    "USE": "USED",
}


def normalize_preview_text(text: str) -> str:
    lines = text.replace("[LN]", "\n").replace("[BLANK]", "\n").split("\n")
    return "\n".join(line.rstrip() for line in lines)


def render_preview_text(record: dict[str, Any], mode: str) -> str:
    if mode == "japanese":
        text = record.get("japanese") or ""
    elif mode == "english":
        text = record.get("english") or record.get("japanese") or ""
    elif mode == "draft":
        text = record.get("english_typeset") or record.get("english") or record.get("japanese") or ""
    else:
        text = record.get("english_typeset") or record.get("english") or record.get("japanese") or ""

    return normalize_preview_text(text)


def is_typeset_continuation(record: dict[str, Any]) -> bool:
    return bool(record.get("englishTypeset")) and not record.get("english") and not record.get("command")


def is_typeset_lead(record: dict[str, Any]) -> bool:
    return bool(record.get("englishTypeset")) and not is_typeset_continuation(record)


def compose_typeset_window(records: list[dict[str, Any]]) -> str:
    chunks = [normalize_preview_text(record.get("englishTypeset", "")) for record in records if record.get("englishTypeset")]
    return "\n".join(chunks)


def first_nonempty(records: list[dict[str, Any]], field: str) -> str:
    for record in records:
        value = (record.get(field) or "").strip()
        if value:
            return value
    return ""


def attach_typeset_windows(viewer_records: list[dict[str, Any]]) -> None:
    def assign_group(group: list[dict[str, Any]]) -> None:
        if not group:
            return

        window_record_ids = [record["id"] for record in group]
        window_offsets = [record["offset"] for record in group]
        window_text_typeset = compose_typeset_window(group)
        window_text_english = first_nonempty(group, "english")
        window_text_japanese = "\n".join(
            normalize_preview_text(record.get("japanese", ""))
            for record in group
            if record.get("japanese")
        )

        for record in group:
            record["windowRecordIds"] = window_record_ids
            record["windowOffsets"] = window_offsets
            record["windowLeadId"] = group[0]["id"]
            record["windowLeadOffset"] = group[0]["offset"]
            record["windowTextTypeset"] = window_text_typeset
            record["windowTextEnglish"] = window_text_english
            record["windowTextJapanese"] = window_text_japanese

    current_group: list[dict[str, Any]] = []
    current_file: str | None = None

    for record in viewer_records:
        if record["file"] != current_file:
            assign_group(current_group)
            current_group = []
            current_file = record["file"]

        if is_typeset_lead(record):
            assign_group(current_group)
            current_group = [record]
            continue

        if current_group and is_typeset_continuation(record):
            current_group.append(record)
            continue

        assign_group(current_group)
        current_group = []

        if record.get("englishTypeset"):
            assign_group([record])

    assign_group(current_group)

    for record in viewer_records:
        if "windowRecordIds" in record:
            continue

        fallback = render_preview_text(
            {
                "english_typeset": record.get("englishTypeset"),
                "english": record.get("english"),
                "japanese": record.get("japanese"),
            },
            "typeset",
        )
        record["windowRecordIds"] = [record["id"]]
        record["windowOffsets"] = [record["offset"]]
        record["windowLeadId"] = record["id"]
        record["windowLeadOffset"] = record["offset"]
        record["windowTextTypeset"] = fallback
        record["windowTextEnglish"] = record.get("english") or ""
        record["windowTextJapanese"] = render_preview_text(
            {
                "english_typeset": record.get("englishTypeset"),
                "english": record.get("english"),
                "japanese": record.get("japanese"),
            },
            "japanese",
        )


def summarize_context(pointer_contexts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result = []
    for pointer_context in pointer_contexts:
        context = pointer_context["context"]
        result.append(
            {
                "pointer_location": pointer_context["pointer_location"],
                "comments": pointer_context.get("comments"),
                "heuristics": pointer_context.get("heuristics", {}),
                "current_command": context.get("current_command"),
                "recognized_ops": [op for op in context.get("preceding_ops", []) if op["kind"] != "unknown"][-6:],
                "raw_window": context.get("window_bytes"),
            }
        )
    return result


def build_viewer_payload(root: Path) -> dict[str, Any]:
    dump_rows = load_dump_rows(root / DUMP_XLS_PATH)
    pointer_rows = load_pointer_rows(root / POINTER_DUMP_XLS_PATH)
    pos_exe_bytes = (root / ORIGINAL_ROM_DIR / "POS.EXE").read_bytes()
    records = build_records(dump_rows, pointer_rows, pos_exe_bytes)

    viewer_records = []
    files: set[str] = set()
    commands: set[str] = set()
    speakers: set[str] = set()
    labels: set[str] = set()

    for idx, record in enumerate(records):
        metadata = record.get("dialogue_metadata", {})
        file_name = record["file"]
        command = record.get("command") or ""
        speaker = metadata.get("speaker") or ""
        files.add(file_name)
        if command:
            commands.add(command)
        if speaker:
            speakers.add(speaker)
        labels.update(record.get("labels", []))

        viewer_records.append(
            {
                "id": idx,
                "file": file_name,
                "offset": record["offset"],
                "command": command,
                "ctrlCodes": record.get("ctrl_codes") or "",
                "labels": record.get("labels", []),
                "dialogueMetadata": metadata,
                "japanese": record.get("japanese") or "",
                "english": record.get("english") or "",
                "englishTypeset": record.get("english_typeset") or "",
                "previewText": render_preview_text(record, "typeset"),
                "comments": record.get("comments") or "",
                "pointerCount": record.get("pointer_count", 0),
                "pointerContexts": summarize_context(record.get("pointer_contexts", [])),
            }
        )

    attach_typeset_windows(viewer_records)
    ordered_files = [sheet_name for sheet_name in dump_rows.keys() if sheet_name in files]
    default_file = "POS1.MSD" if "POS1.MSD" in files else ordered_files[0]

    return {
        "meta": {
            "recordCount": len(viewer_records),
            "files": ordered_files,
            "commands": sorted(commands),
            "speakers": sorted(speakers),
            "labels": sorted(labels),
            "defaultFile": default_file,
            "screen": {
                "width": 640,
                "height": 400,
                "typesetCharsPerLine": 39,
            },
        },
        "records": viewer_records,
        "graph": build_graph_payload(root, pos_exe_bytes),
    }


def build_graph_payload(root: Path, pos_exe_bytes: bytes) -> dict[str, Any]:
    dump_path = root / DUMP_XLS_PATH
    file_filter = set(MSD_POINTER_RANGES.keys())

    dispatch_dump_rows = load_dispatch_dump_rows(dump_path, file_filter)
    dispatch_results = {
        filename: scan_dispatch_headers(filename, pos_exe_bytes, dispatch_dump_rows.get(filename, []))
        for filename in sorted(file_filter)
    }
    dispatch_payload = dispatch_json_ready(dispatch_results)

    flag_dump_rows = load_flag_dump_rows(dump_path, file_filter)
    flag_results = {
        filename: scan_file_flags(filename, pos_exe_bytes, flag_dump_rows.get(filename, []))
        for filename in sorted(file_filter)
    }
    flag_payload = flag_json_ready(flag_results)

    handoff_rows_by_file_offset = load_handoff_dump_rows(dump_path)
    offset_to_rows = build_offset_to_rows(handoff_rows_by_file_offset)
    map_names = load_map_names(SAVE_FORMAT_PATH)
    handoff_payload = handoff_json_ready(scan_handoffs(pos_exe_bytes, offset_to_rows, map_names))
    transition_payload = transition_json_ready(scan_transitions(pos_exe_bytes, offset_to_rows, map_names))

    workbook_rows = load_workbook_rows(dump_path)
    trigger_model = build_model(
        workbook_rows,
        build_dispatch_lookup(dispatch_payload),
        build_target_lookup(handoff_payload, location_key="location", extra_keys=["arg1"]),
        build_target_lookup(transition_payload, location_key="location", extra_keys=["arg1"]),
        build_flag_lookup(flag_payload),
        True,
    )
    state_graph = build_graph(trigger_model)
    acceptance = build_acceptance_outline(state_graph)
    command_matrix = build_command_matrix(state_graph)
    flag_aliases = build_flag_aliases(flag_payload)
    annotate_graph_with_flag_aliases(state_graph, flag_aliases)
    annotate_command_matrix_with_flag_aliases(command_matrix, flag_aliases)
    walkthrough_report = build_walkthrough_report(root / "docs" / "walkthrough.htm", root / DUMP_XLS_PATH)
    annotate_graph_with_walkthrough_hints(state_graph, walkthrough_report)
    acceptance = build_acceptance_outline(state_graph)
    location_captures = load_location_captures(root)

    return {
        "stateGraph": state_graph,
        "walkthroughAcceptance": acceptance,
        "commandMatrix": command_matrix,
        "flagAliases": flag_aliases,
        "walkthroughHints": walkthrough_report,
        "locationCaptures": location_captures,
    }


def load_location_captures(root: Path) -> dict[str, Any]:
    manifest_path = root / "script_viewer" / "assets" / "locations" / "phon1-manifest.json"
    if not manifest_path.exists():
        return {"byDestinationLabel": {}, "byFile": {}, "byFileRanges": {}, "items": []}

    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    items = payload.get("locations", [])
    by_destination_label: dict[str, dict[str, Any]] = {}
    by_map_hex: dict[str, dict[str, Any]] = {}
    by_slug: dict[str, dict[str, Any]] = {}
    by_label: dict[str, dict[str, Any]] = {}
    by_label_normalized: dict[str, dict[str, Any]] = {}
    manual_by_map_hex: dict[str, dict[str, Any]] = {}
    manual_by_slug: dict[str, dict[str, Any]] = {}
    manual_by_label: dict[str, dict[str, Any]] = {}
    manual_by_label_normalized: dict[str, dict[str, Any]] = {}
    normalized_items: list[dict[str, Any]] = []

    for item in items:
        map_hex = str(item.get("map_hex") or "").strip()
        label = str(item.get("label") or "").strip()
        destination_label = f'{map_hex} "{label}"' if map_hex and label else ""
        entry = {
            "map_id": item.get("map_id"),
            "map_hex": map_hex,
            "label": label,
            "slug": item.get("slug"),
            "image": item.get("viewer_image") or item.get("image"),
            "route": item.get("route", {}),
            "viewer_usable": bool(item.get("viewer_usable", True)),
            "viewer_crop": item.get("viewer_crop"),
            "viewer_size": item.get("viewer_size"),
            "scene_image": item.get("viewer_scene_image") or item.get("viewer_image") or item.get("image"),
            "scene_size": item.get("viewer_scene_size") or item.get("viewer_size"),
            "full_image": item.get("viewer_full_image") or item.get("viewer_image") or item.get("image"),
            "full_size": item.get("viewer_full_size") or item.get("viewer_size"),
        }
        normalized_items.append(entry)
        if map_hex and entry["image"]:
            manual_by_map_hex[map_hex.lower()] = entry
        if entry["slug"] and entry["image"]:
            manual_by_slug[str(entry["slug"]).lower()] = entry
        if label and entry["image"]:
            manual_by_label[label.lower()] = entry
            normalized_label = normalize_scene_ref(label)
            if normalized_label:
                manual_by_label_normalized[normalized_label] = entry
        if entry["viewer_usable"] and entry["image"]:
            if map_hex:
                by_map_hex[map_hex.lower()] = entry
            if entry["slug"]:
                by_slug[str(entry["slug"]).lower()] = entry
            if label:
                by_label[label.lower()] = entry
                normalized_label = normalize_scene_ref(label)
                if normalized_label:
                    by_label_normalized[normalized_label] = entry
            by_destination_label[destination_label] = entry

    by_file = infer_file_scene_map(
        by_destination_label=by_destination_label,
        by_map_hex=by_map_hex,
        by_slug=by_slug,
        by_label=by_label,
        by_label_normalized=by_label_normalized,
    )
    by_file_ranges: dict[str, list[dict[str, Any]]] = {}

    manual_file_map, manual_file_ranges = load_file_scene_map(
        root,
        by_destination_label=by_destination_label,
        by_map_hex=manual_by_map_hex,
        by_slug=manual_by_slug,
        by_label=manual_by_label,
        by_label_normalized=manual_by_label_normalized,
    )
    by_file.update(manual_file_map)
    by_file_ranges.update(manual_file_ranges)

    return {
        "byDestinationLabel": by_destination_label,
        "byFile": by_file,
        "byFileRanges": by_file_ranges,
        "items": normalized_items,
    }


def infer_file_scene_map(
    *,
    by_destination_label: dict[str, dict[str, Any]],
    by_map_hex: dict[str, dict[str, Any]],
    by_slug: dict[str, dict[str, Any]],
    by_label: dict[str, dict[str, Any]],
    by_label_normalized: dict[str, dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    aliases = {
        "DOCTOR.MSD": '0x11 "Doctor scene"',
        "HONHOA.MSD": '0x0f "Honghua scene"',
        "AYAKA.MSD": '0x0a "Ayaka scene"',
        "MAI.MSD": '0x0c "May scene"',
        "MINS.MSD": '0x0d "Minsky scene"',
        "MERYL.MSD": '0x0e "Shower/Meryl scene"',
        "NEDRA1.MSD": '0x10 "Nedra scene"',
        "NEDRA2.MSD": '0x10 "Nedra scene"',
        "PLYM.MSD": '0x09 "Prim scene"',
        "ARISA.MSD": '0x14 "Machine/Alisa scene"',
        "TINA.MSD": '0x12 "Tina scene (21? lines)"',
        "P_SW1.MSD": '0x08 "Shower"',
        "P_CITY.MSD": '0x17 "Old City"',
        "P_SUTE.MSD": '0x18 "Abandoned Zone"',
        "P_BYO.MSD": '0x50 "Medical ward"',
        "P_ENT2.MSD": '0x51 "Entrance again?"',
        "P_BOX.MSD": '0x54 "Nedra in the box (3 lines)"',
        "P_SIRYO.MSD": '0x55 "Nedra possessioner in the archives (3 lines)"',
    }

    result: dict[str, dict[str, Any]] = {}
    for file_name, ref in aliases.items():
        entry = resolve_scene_capture_reference(
            ref,
            by_destination_label=by_destination_label,
            by_map_hex=by_map_hex,
            by_slug=by_slug,
            by_label=by_label,
            by_label_normalized=by_label_normalized,
        )
        if entry:
            result[file_name] = entry
    return result


def load_file_scene_map(
    root: Path,
    *,
    by_destination_label: dict[str, dict[str, Any]],
    by_map_hex: dict[str, dict[str, Any]],
    by_slug: dict[str, dict[str, Any]],
    by_label: dict[str, dict[str, Any]],
    by_label_normalized: dict[str, dict[str, Any]],
) -> tuple[dict[str, dict[str, Any]], dict[str, list[dict[str, Any]]]]:
    mapping_path = root / "script_viewer" / "assets" / "locations" / "file-scene-map.json"
    if not mapping_path.exists():
        return {}, {}

    payload = load_loose_json(mapping_path)
    result: dict[str, dict[str, Any]] = {}
    ranges: dict[str, list[dict[str, Any]]] = {}

    for file_name, ref in payload.items():
        if str(file_name).startswith("__"):
            continue
        if isinstance(ref, dict) and "ranges" in ref:
            rules = []
            for rule in ref.get("ranges", []):
                entry = resolve_scene_capture_reference(
                    rule.get("ref"),
                    by_destination_label=by_destination_label,
                    by_map_hex=by_map_hex,
                    by_slug=by_slug,
                    by_label=by_label,
                    by_label_normalized=by_label_normalized,
                )
                if not entry:
                    continue
                rules.append(
                    {
                        "start": parse_scene_offset(rule.get("start")),
                        "end": parse_scene_offset(rule.get("end")),
                        "capture": apply_capture_crop(entry, rule.get("crop")),
                    }
                )
            if rules:
                ranges[str(file_name)] = rules
            default_ref = ref.get("default")
            if default_ref is None:
                continue
            ref = default_ref
        entry = resolve_scene_capture_reference(
            ref,
            by_destination_label=by_destination_label,
            by_map_hex=by_map_hex,
            by_slug=by_slug,
            by_label=by_label,
            by_label_normalized=by_label_normalized,
        )
        if entry:
            result[str(file_name)] = apply_capture_crop(entry, ref.get("crop") if isinstance(ref, dict) else None)

    return result, ranges


def parse_scene_offset(value: object) -> int | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    return int(text, 16) if text.lower().startswith("0x") else int(text)


def load_loose_json(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        sanitized = re.sub(r",(\s*[}\]])", r"\1", text)
        return json.loads(sanitized)


def resolve_scene_capture_reference(
    ref: object,
    *,
    by_destination_label: dict[str, dict[str, Any]],
    by_map_hex: dict[str, dict[str, Any]],
    by_slug: dict[str, dict[str, Any]],
    by_label: dict[str, dict[str, Any]],
    by_label_normalized: dict[str, dict[str, Any]],
) -> dict[str, Any] | None:
    if isinstance(ref, dict):
        for key in ("destination_label", "map_hex", "slug", "label"):
            if key in ref:
                return resolve_scene_capture_reference(
                    ref[key],
                    by_destination_label=by_destination_label,
                    by_map_hex=by_map_hex,
                    by_slug=by_slug,
                    by_label=by_label,
                    by_label_normalized=by_label_normalized,
                )
        return None

    text = str(ref or "").strip()
    if not text:
        return None
    if text in by_destination_label:
        return by_destination_label[text]

    lowered = text.lower()
    if lowered in by_map_hex:
        return by_map_hex[lowered]
    if lowered in by_slug:
        return by_slug[lowered]
    if lowered in by_label:
        return by_label[lowered]
    normalized = normalize_scene_ref(text)
    if normalized in by_label_normalized:
        return by_label_normalized[normalized]
    for key, entry in by_label_normalized.items():
        if normalized and (key.startswith(normalized) or normalized.startswith(key)):
            return entry

    if lowered.startswith("0x") and lowered in by_map_hex:
        return by_map_hex[lowered]

    return None


def normalize_scene_ref(text: str) -> str:
    value = str(text or "").lower().strip()
    value = re.sub(r"\([^)]*\)", " ", value)
    value = re.sub(r"[^a-z0-9]+", " ", value)
    return " ".join(part for part in value.split() if part)


def apply_capture_crop(entry: dict[str, Any], crop: object) -> dict[str, Any]:
    mode = str(crop or "").strip().lower()
    if mode not in {"scene-panel", "full-frame"}:
        return entry
    clone = dict(entry)
    if mode == "scene-panel":
        clone["image"] = entry.get("scene_image") or entry.get("image")
        clone["viewer_crop"] = "scene-panel"
        clone["viewer_size"] = entry.get("scene_size") or entry.get("viewer_size")
    else:
        clone["image"] = entry.get("full_image") or entry.get("image")
        clone["viewer_crop"] = "full-frame"
        clone["viewer_size"] = entry.get("full_size") or entry.get("viewer_size")
    return clone


def normalize_flag_value(value: object) -> int:
    if isinstance(value, int):
        return value
    text = str(value).strip()
    return int(text, 16) if text.startswith("0x") else int(text)


def command_to_alias_phrase(command: str) -> str:
    text = (command or "").strip()
    if not text:
        return ""
    if text == "(Arrive)":
        return "ARRIVED"
    if text == "(End of scene)":
        return "SCENE_COMPLETE"

    cleaned = re.sub(r"\([^)]*\)", "", text)
    cleaned = cleaned.replace("-", " ")
    words = [word for word in re.findall(r"[A-Za-z0-9]+", cleaned.upper()) if not word.isdigit()]
    if not words:
        return ""

    verb = words[0]
    rest = words[1:]
    if verb in VERB_ALIASES and rest:
        return f"{VERB_ALIASES[verb]}_{'_'.join(rest)}"
    if verb in VERB_ALIASES:
        return VERB_ALIASES[verb]
    return "_".join(words)


def build_flag_alias_table(grouped: dict[tuple[int, int], dict[str, Any]]) -> dict[str, dict[str, Any]]:
    aliases: dict[str, dict[str, Any]] = {}
    for (arg1, arg2), group in grouped.items():
        set_phrases = [command_to_alias_phrase(command) for command in group["set_targets"] if command_to_alias_phrase(command)]
        check_phrases = [command_to_alias_phrase(command) for command in group["check_targets"] if command_to_alias_phrase(command)]
        clear_phrases = [command_to_alias_phrase(command) for command in group["clear_targets"] if command_to_alias_phrase(command)]

        if set_phrases:
            top_phrase, top_count = Counter(set_phrases).most_common(1)[0]
            friendly_name = top_phrase
            confidence = "high" if top_count == len(set_phrases) else "medium"
        elif check_phrases:
            top_phrase, top_count = Counter(check_phrases).most_common(1)[0]
            friendly_name = f"STATE_FOR_{top_phrase}"
            confidence = "medium" if top_count == len(check_phrases) else "low"
        elif clear_phrases:
            top_phrase, top_count = Counter(clear_phrases).most_common(1)[0]
            friendly_name = f"RESET_{top_phrase}"
            confidence = "low" if top_count != len(clear_phrases) else "medium"
        else:
            friendly_name = f"FLAG_{arg1:02X}_{arg2:02d}"
            confidence = "low"

        aliases[f"{arg1}:{arg2}"] = {
            "friendly_name": friendly_name,
            "confidence": confidence,
            "files": sorted(group["files"]),
            "set_targets": sorted(set(group["set_targets"])),
            "check_targets": sorted(set(group["check_targets"])),
            "clear_targets": sorted(set(group["clear_targets"])),
            "evidence_summary": "; ".join(
                part
                for part in (
                    f"set by {', '.join(sorted(set(group['set_targets']))[:3])}" if group["set_targets"] else "",
                    f"checked by {', '.join(sorted(set(group['check_targets']))[:3])}" if group["check_targets"] else "",
                    f"cleared by {', '.join(sorted(set(group['clear_targets']))[:3])}" if group["clear_targets"] else "",
                )
                if part
            ),
        }

    return aliases


def build_flag_aliases(flag_payload: dict[str, Any]) -> dict[str, Any]:
    global_grouped: dict[tuple[int, int], dict[str, Any]] = defaultdict(
        lambda: {
            "set_targets": [],
            "check_targets": [],
            "clear_targets": [],
            "files": set(),
        }
    )

    grouped_by_file: dict[str, dict[tuple[int, int], dict[str, Any]]] = defaultdict(
        lambda: defaultdict(
            lambda: {
                "set_targets": [],
                "check_targets": [],
                "clear_targets": [],
                "files": set(),
            }
        )
    )

    for filename, payload in flag_payload.items():
        for operation in payload.get("operations", []):
            arg1 = normalize_flag_value(operation["arg1"])
            arg2 = normalize_flag_value(operation["arg2"])
            key = (arg1, arg2)
            global_grouped[key]["files"].add(filename)
            grouped_by_file[filename][key]["files"].add(filename)
            target = operation.get("target_block_command") or operation.get("target_command") or ""
            bucket_name = {
                "set_flag": "set_targets",
                "check_flag": "check_targets",
                "clear_flag": "clear_targets",
            }[operation["kind"]]
            if target:
                global_grouped[key][bucket_name].append(target)
                grouped_by_file[filename][key][bucket_name].append(target)

    return {
        "global": build_flag_alias_table(global_grouped),
        "byFile": {filename: build_flag_alias_table(grouped) for filename, grouped in grouped_by_file.items()},
    }


def resolve_flag_alias(flag_aliases: dict[str, Any], filename: str, arg1: int, arg2: int) -> dict[str, Any] | None:
    key = f"{arg1}:{arg2}"
    file_alias = flag_aliases.get("byFile", {}).get(filename, {}).get(key)
    if file_alias is not None:
        return file_alias
    return flag_aliases.get("global", {}).get(key)


def annotate_graph_with_flag_aliases(state_graph: dict[str, Any], flag_aliases: dict[str, Any]) -> None:
    for filename, payload in state_graph.get("files", {}).items():
        for node in payload.get("nodes", []):
            for flag in node.get("flag_gates", []):
                alias = resolve_flag_alias(flag_aliases, filename, flag["arg1"], flag["arg2"])
                if alias is None:
                    continue
                flag["friendly_name"] = alias["friendly_name"]
                flag["confidence"] = alias["confidence"]
                flag["evidence_summary"] = alias["evidence_summary"]


def annotate_command_matrix_with_flag_aliases(command_matrix: dict[str, Any], flag_aliases: dict[str, Any]) -> None:
    for filename, payload in command_matrix.items():
        for action_bucket in payload.get("actions", {}).values():
            for target_bucket in action_bucket.values():
                for flag in target_bucket.get("flags", []):
                    alias = resolve_flag_alias(flag_aliases, filename, flag["arg1"], flag["arg2"])
                    if alias is None:
                        continue
                    flag["friendly_name"] = alias["friendly_name"]
                    flag["confidence"] = alias["confidence"]


def is_h_scene_file(filename: str) -> bool:
    return not filename.startswith(("P_", "POS1", "RASU", "END"))


def choose_walkthrough_candidate(section: dict[str, Any]) -> dict[str, Any] | None:
    candidates = section.get("candidate_sheets", [])
    if not candidates:
        return None
    best = candidates[0]
    if is_h_scene_file(best["sheet"]):
        return None
    coverage = best["matched_step_count"] / max(best["step_count"], 1)
    if coverage < 0.75:
        return None
    second = candidates[1] if len(candidates) > 1 else None
    if second and best["matched_step_count"] <= second["matched_step_count"] and coverage < 1.0:
        return None
    return best


def format_walkthrough_step_label(step: dict[str, Any]) -> str:
    label = step.get("raw") or ""
    repeat = int(step.get("repeat") or 1)
    if repeat > 1:
        label += f" x{repeat}"
    return label


def command_variants_for_node(node: dict[str, Any]) -> list[dict[str, Any]]:
    variants: list[dict[str, Any]] = []
    seen: set[str] = set()
    for command in [*node.get("commands", []), node.get("block_command")]:
        if not command:
            continue
        action, target = parse_walkthrough_command(command)
        token = json.dumps({"command": command, "action": action, "target": target}, sort_keys=True)
        if token in seen:
            continue
        seen.add(token)
        variants.append(
            {
                "command": command,
                "action": action,
                "target": target,
            }
        )
    return variants


def node_matches_walkthrough_step(node: dict[str, Any], step: dict[str, Any]) -> bool:
    return any(step_matches_command(step, variant) for variant in command_variants_for_node(node))


def extract_command_variant_number(command: str) -> int | None:
    match = re.search(r"\((\d+)\)\s*$", command)
    if match:
        return int(match.group(1))
    match = re.search(r"\b(\d+)\s*$", command)
    if match:
        return int(match.group(1))
    return None


def score_walkthrough_variant(step: dict[str, Any], variant: dict[str, Any]) -> tuple[int, int]:
    command = (variant.get("command") or "").strip()
    lowered = command.lower()
    repeat = int(step.get("repeat") or 1)
    number = extract_command_variant_number(command)

    score = 20
    if any(token in lowered for token in ("after", "while", "later", "unused")):
        score -= 8
    else:
        score += 8

    if repeat > 1:
        if number is not None and 1 <= number <= repeat:
            score += 12
        elif number is None:
            score += 2
        else:
            score -= 3
    else:
        if number == 1:
            score += 10
        elif number is None:
            score += 6
        else:
            score -= 2

    return score, number if number is not None else 999


def resolve_walkthrough_step_nodes(nodes: list[dict[str, Any]], step: dict[str, Any]) -> list[dict[str, Any]]:
    ranked: list[tuple[int, int, int, dict[str, Any]]] = []
    for node in nodes:
        best_score: tuple[int, int] | None = None
        for variant in command_variants_for_node(node):
            if not step_matches_command(step, variant):
                continue
            variant_score = score_walkthrough_variant(step, variant)
            if best_score is None or variant_score > best_score:
                best_score = variant_score
        if best_score is None:
            continue
        ranked.append((best_score[0], -best_score[1], -normalize_flag_value(node["start_offset"]), node))

    if not ranked:
        return []

    ranked.sort(reverse=True)
    repeat = int(step.get("repeat") or 1)
    if repeat == 1:
        if len(ranked) > 1 and ranked[0][0] < ranked[1][0] + 4:
            return []
        return [ranked[0][3]]

    if len(ranked) < repeat:
        return []

    selected = [entry[3] for entry in ranked[:repeat]]
    selected.sort(key=lambda node: normalize_flag_value(node["start_offset"]))
    return selected


def sort_walkthrough_labels(values: list[str]) -> list[str]:
    return sorted(set(values), key=lambda item: (item.split(" x", 1)[0], item))


def annotate_node_walkthrough_step(
    node: dict[str, Any],
    *,
    section: dict[str, Any],
    candidate: dict[str, Any],
    step_index: int,
    step_label: str,
    repeat: int,
    sequence_index: int,
    sequence_total: int,
    prior_labels: list[str],
) -> None:
    node["walkthrough_steps"].append(
        {
            "section_index": section["index"],
            "heading_jp": section["heading_jp"],
            "heading_en": section["heading_en"],
            "step_index": step_index,
            "step_label": step_label,
            "repeat": repeat,
            "coverage": candidate["coverage"],
            "hint_strength": "walkthrough",
            "sequence_index": sequence_index,
            "sequence_total": sequence_total,
        }
    )
    if prior_labels:
        node["walkthrough_prior_steps"] = sort_walkthrough_labels(
            [*node.get("walkthrough_prior_steps", []), *prior_labels]
        )


def append_walkthrough_hint_edge(
    payload: dict[str, Any],
    edge_seen: set[tuple[str, str, int]],
    *,
    section: dict[str, Any],
    source_node: dict[str, Any],
    target_node: dict[str, Any],
    from_step: str,
    to_step: str,
) -> None:
    edge = {
        "type": "walkthrough_hint",
        "from_node": source_node["id"],
        "to_node": target_node["id"],
        "section_index": section["index"],
        "heading_jp": section["heading_jp"],
        "heading_en": section["heading_en"],
        "from_step": from_step,
        "to_step": to_step,
        "strength": "hint",
    }
    edge_key = (edge["from_node"], edge["to_node"], edge["section_index"])
    if edge_key in edge_seen:
        return
    edge_seen.add(edge_key)
    payload["walkthrough_hint_edges"].append(edge)


def annotate_graph_with_walkthrough_hints(state_graph: dict[str, Any], walkthrough_report: dict[str, Any]) -> None:
    files = state_graph.get("files", {})

    for payload in files.values():
        payload["walkthrough_sections"] = []
        payload["walkthrough_hint_edges"] = []
        for node in payload.get("nodes", []):
            node["walkthrough_steps"] = []
            node["walkthrough_prior_steps"] = []

    for section in walkthrough_report.get("sections", []):
        candidate = choose_walkthrough_candidate(section)
        if candidate is None:
            continue

        filename = candidate["sheet"]
        payload = files.get(filename)
        if payload is None:
            continue

        section_summary = {
            "section_index": section["index"],
            "heading_jp": section["heading_jp"],
            "heading_en": section["heading_en"],
            "matched_step_count": candidate["matched_step_count"],
            "step_count": candidate["step_count"],
            "coverage": candidate["coverage"],
        }
        payload["walkthrough_sections"].append(section_summary)

        nodes = payload.get("nodes", [])
        previous_group: list[dict[str, Any]] = []
        previous_label = ""
        prior_labels: list[str] = []
        edge_seen = {
            (
                edge.get("from_node"),
                edge.get("to_node"),
                edge.get("section_index"),
            )
            for edge in payload["walkthrough_hint_edges"]
        }

        for step_index, step in enumerate(section.get("steps", [])):
            step_label = format_walkthrough_step_label(step)
            resolved_group = resolve_walkthrough_step_nodes(nodes, step)
            if not resolved_group:
                prior_labels.append(step_label)
                continue

            repeat = int(step.get("repeat") or 1)
            for group_index, node in enumerate(resolved_group):
                annotate_node_walkthrough_step(
                    node,
                    section=section,
                    candidate=candidate,
                    step_index=step_index,
                    step_label=step_label,
                    repeat=repeat,
                    sequence_index=group_index + 1,
                    sequence_total=len(resolved_group),
                    prior_labels=prior_labels,
                )

            if previous_group:
                append_walkthrough_hint_edge(
                    payload,
                    edge_seen,
                    section=section,
                    source_node=previous_group[-1],
                    target_node=resolved_group[0],
                    from_step=previous_label,
                    to_step=step_label,
                )

            if len(resolved_group) > 1:
                for source_node, target_node in zip(resolved_group, resolved_group[1:]):
                    append_walkthrough_hint_edge(
                        payload,
                        edge_seen,
                        section=section,
                        source_node=source_node,
                        target_node=target_node,
                        from_step=step_label,
                        to_step=step_label,
                    )

            previous_group = resolved_group
            previous_label = step_label
            prior_labels.append(step_label)

        for node in nodes:
            node["walkthrough_prior_steps"] = sort_walkthrough_labels(node.get("walkthrough_prior_steps", []))


def main() -> None:
    root = Path(__file__).resolve().parent
    output_dir = root / "script_viewer"
    output_dir.mkdir(exist_ok=True)
    payload = build_viewer_payload(root)

    js = "window.PSSR_VIEWER_DATA = " + json.dumps(payload, ensure_ascii=True) + ";\n"
    output_path = output_dir / "viewer-data.js"
    output_path.write_text(js, encoding="utf-8")
    print(f"Wrote {payload['meta']['recordCount']} records to {output_path}")


if __name__ == "__main__":
    main()
