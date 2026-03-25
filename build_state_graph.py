from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def hex5(value: int | None) -> str | None:
    if value is None:
        return None
    return f"0x{value:05x}"


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def append_unique(items: list[dict[str, Any]], item: dict[str, Any], seen: set[str]) -> None:
    token = json.dumps(item, sort_keys=True, ensure_ascii=False)
    if token in seen:
        return
    seen.add(token)
    items.append(item)


def summarize_text(rows: list[dict[str, Any]], limit: int = 3) -> list[str]:
    snippets: list[str] = []
    for row in rows:
        english = row.get("english")
        if not english:
            continue
        text = str(english).strip().replace("\r", " ").replace("\n", " ")
        if not text:
            continue
        snippets.append(text[:160])
        if len(snippets) >= limit:
            break
    return snippets


OPTIONAL_ACTIONS = {"Look", "Talk", "Examine", "Think", "Move"}


def classify_node(
    commands: list[str],
    block_command: str | None,
    display_types: list[str],
    dispatch_triggers: list[dict[str, Any]],
    event_transitions: list[dict[str, Any]],
    room_transitions: list[dict[str, Any]],
    flag_gates: list[dict[str, Any]],
) -> tuple[str, str]:
    command_texts = [cmd for cmd in commands if cmd] + ([block_command] if block_command else [])
    lowered_display = " | ".join(display_types).lower()
    actions = {(trigger.get("action") or "").strip() for trigger in dispatch_triggers if trigger.get("action")}
    optional_command = any(
        any(text.startswith(prefix) for prefix in OPTIONAL_ACTIONS)
        for text in command_texts
    )
    optional_dispatch = bool(actions & OPTIONAL_ACTIONS)
    has_display_path = bool(display_types) and not all(text == "manual block only" for text in display_types)
    route_known = bool(command_texts or dispatch_triggers or event_transitions or room_transitions or has_display_path)

    if route_known:
        route_status = "conditional" if flag_gates else "known"
    else:
        route_status = "unknown"

    if optional_command or optional_dispatch:
        route_role = "optional"
    elif (
        block_command in {"(Arrive)", "(End of scene)"}
        or "arrival text" in lowered_display
        or "direct range" in lowered_display
        or event_transitions
        or room_transitions
    ):
        route_role = "critical"
    elif route_known:
        route_role = "critical"
    else:
        route_role = "unknown"

    return route_status, route_role


def should_start_new_node(previous: dict[str, Any] | None, current: dict[str, Any]) -> bool:
    if previous is None:
        return True
    if current.get("command"):
        return True
    if current.get("block_command") != previous.get("block_command"):
        return True
    return False


def build_node(file_name: str, rows: list[dict[str, Any]]) -> dict[str, Any]:
    start_offset = rows[0]["offset"]
    end_offset = rows[-1]["offset"]
    node_id = f"{file_name}:{hex5(start_offset)}"

    commands: list[str] = []
    display_types: list[str] = []
    display_details: list[str] = []
    dispatch_triggers: list[dict[str, Any]] = []
    event_transitions: list[dict[str, Any]] = []
    room_transitions: list[dict[str, Any]] = []
    flag_gates: list[dict[str, Any]] = []

    command_seen: set[str] = set()
    display_type_seen: set[str] = set()
    display_detail_seen: set[str] = set()
    dispatch_seen: set[str] = set()
    event_transition_seen: set[str] = set()
    room_transition_seen: set[str] = set()
    flag_seen: set[str] = set()

    for row in rows:
        command = row.get("command")
        if command and command not in command_seen:
            command_seen.add(command)
            commands.append(command)

        display_type = row.get("display_type")
        if display_type and display_type not in display_type_seen:
            display_type_seen.add(display_type)
            display_types.append(display_type)

        display_detail = row.get("display_detail")
        if display_detail and display_detail not in display_detail_seen:
            display_detail_seen.add(display_detail)
            display_details.append(display_detail)

        for context in row.get("dispatch_contexts", []):
            append_unique(
                dispatch_triggers,
                {
                    "action": context.get("action"),
                    "target": context.get("target"),
                    "header_location": context.get("header_location"),
                    "source": context.get("source"),
                    "opcode_location": context.get("opcode_location"),
                    "table_location": context.get("table_location"),
                    "target_location": context.get("target_location"),
                },
                dispatch_seen,
            )

        for context in row.get("handoff_contexts", []):
            append_unique(
                event_transitions,
                {
                    "location": context.get("location"),
                    "arg1": context.get("arg1"),
                    "destination_label": context.get("destination_label"),
                    "preceding_text": context.get("preceding_text"),
                },
                event_transition_seen,
            )

        for context in row.get("transition_contexts", []):
            append_unique(
                room_transitions,
                {
                    "location": context.get("location"),
                    "arg1": context.get("arg1"),
                    "destination_label": context.get("destination_label"),
                    "preceding_text": context.get("preceding_text"),
                },
                room_transition_seen,
            )

        for context in row.get("flag_contexts", []):
            append_unique(
                flag_gates,
                {
                    "kind": context.get("kind"),
                    "arg1": context.get("arg1"),
                    "arg2": context.get("arg2"),
                    "count": context.get("count"),
                    "locations": context.get("locations", []),
                },
                flag_seen,
            )

    route_status, route_role = classify_node(
        commands,
        rows[0].get("block_command"),
        display_types,
        dispatch_triggers,
        event_transitions,
        room_transitions,
        flag_gates,
    )

    return {
        "id": node_id,
        "file": file_name,
        "block_command": rows[0].get("block_command"),
        "commands": commands,
        "start_offset": hex5(start_offset),
        "end_offset": hex5(end_offset),
        "row_count": len(rows),
        "display_types": display_types,
        "display_details": display_details,
        "english_preview": summarize_text(rows),
        "route_status": route_status,
        "route_role": route_role,
        "dispatch_triggers": dispatch_triggers,
        "event_transitions": event_transitions,
        "room_transitions": room_transitions,
        "flag_gates": flag_gates,
    }


def build_file_graph(file_name: str, rows: list[dict[str, Any]]) -> dict[str, Any]:
    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []
    edge_seen: set[str] = set()
    pair_seen: set[str] = set()
    action_target_pairs: list[dict[str, str | None]] = []
    destination_seen: set[str] = set()
    destinations: list[str] = []

    current_rows: list[dict[str, Any]] = []
    previous_row: dict[str, Any] | None = None

    def flush_current() -> None:
        if not current_rows:
            return
        node = build_node(file_name, current_rows)
        nodes.append(node)

        for trigger in node["dispatch_triggers"]:
            pair = {"action": trigger.get("action"), "target": trigger.get("target")}
            pair_key = json.dumps(pair, sort_keys=True, ensure_ascii=False)
            if pair_key not in pair_seen:
                pair_seen.add(pair_key)
                action_target_pairs.append(pair)

            append_unique(
                edges,
                {
                    "type": "dispatch",
                    "file": file_name,
                    "from_action": trigger.get("action"),
                    "from_target": trigger.get("target"),
                    "header_location": trigger.get("header_location"),
                    "to_node": node["id"],
                },
                edge_seen,
            )

        for event_transition in node["event_transitions"]:
            destination = event_transition.get("destination_label")
            if destination and destination not in destination_seen:
                destination_seen.add(destination)
                destinations.append(destination)
            append_unique(
                edges,
                {
                    "type": "event_transition",
                    "file": file_name,
                    "from_node": node["id"],
                    "location": event_transition.get("location"),
                    "arg1": event_transition.get("arg1"),
                    "destination_label": destination,
                },
                edge_seen,
            )

        for room_transition in node["room_transitions"]:
            destination = room_transition.get("destination_label")
            if destination and destination not in destination_seen:
                destination_seen.add(destination)
                destinations.append(destination)
            append_unique(
                edges,
                {
                    "type": "room_transition",
                    "file": file_name,
                    "from_node": node["id"],
                    "location": room_transition.get("location"),
                    "arg1": room_transition.get("arg1"),
                    "destination_label": destination,
                },
                edge_seen,
            )

        current_rows.clear()

    for row in rows:
        if should_start_new_node(previous_row, row):
            flush_current()
        current_rows.append(row)
        previous_row = row
    flush_current()

    return {
        "node_count": len(nodes),
        "edge_count": len(edges),
        "dispatch_edge_count": sum(1 for edge in edges if edge["type"] == "dispatch"),
        "event_transition_edge_count": sum(1 for edge in edges if edge["type"] == "event_transition"),
        "room_transition_edge_count": sum(1 for edge in edges if edge["type"] == "room_transition"),
        "action_target_pairs": action_target_pairs,
        "destinations": destinations,
        "nodes": nodes,
        "edges": edges,
    }


def build_graph(trigger_model: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    files: dict[str, Any] = {}
    total_nodes = 0
    total_edges = 0
    total_dispatch_edges = 0
    total_event_transition_edges = 0
    total_room_transition_edges = 0

    for file_name, rows in trigger_model.items():
        if not rows:
            continue
        file_graph = build_file_graph(file_name, rows)
        files[file_name] = file_graph
        total_nodes += file_graph["node_count"]
        total_edges += file_graph["edge_count"]
        total_dispatch_edges += file_graph["dispatch_edge_count"]
        total_event_transition_edges += file_graph["event_transition_edge_count"]
        total_room_transition_edges += file_graph["room_transition_edge_count"]

    return {
        "global_summary": {
            "file_count": len(files),
            "node_count": total_nodes,
            "edge_count": total_edges,
            "dispatch_edge_count": total_dispatch_edges,
            "event_transition_edge_count": total_event_transition_edges,
            "room_transition_edge_count": total_room_transition_edges,
        },
        "files": files,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a higher-level state/trigger graph from trigger_model.json.")
    parser.add_argument("--trigger-model", type=Path, required=True, help="Path to trigger_model.json")
    parser.add_argument("--output", type=Path, help="Write JSON to this path instead of stdout")
    args = parser.parse_args()

    graph = build_graph(load_json(args.trigger_model))
    rendered = json.dumps(graph, indent=2, ensure_ascii=False)
    if args.output:
        args.output.write_text(rendered, encoding="utf-8")
    else:
        print(rendered)


if __name__ == "__main__":
    main()
