from __future__ import annotations

import json
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

    return {
        "stateGraph": state_graph,
        "walkthroughAcceptance": acceptance,
        "commandMatrix": command_matrix,
    }


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
