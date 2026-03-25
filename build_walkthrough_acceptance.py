from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def rate_file(payload: dict[str, Any]) -> str:
    node_count = payload["node_count"] or 1
    unknown_nodes = sum(1 for node in payload["nodes"] if node["route_status"] == "unknown")
    unknown_ratio = unknown_nodes / node_count

    if unknown_ratio <= 0.10:
        return "strong"
    if unknown_ratio <= 0.35:
        return "partial"
    return "weak"


def summarize_file(file_name: str, payload: dict[str, Any]) -> dict[str, Any]:
    nodes = payload["nodes"]
    route_known_nodes = [node for node in nodes if node["route_status"] in {"known", "conditional"}]
    conditional_nodes = [node for node in nodes if node["route_status"] == "conditional"]
    trigger_unknown_nodes = [node for node in nodes if node["route_status"] == "unknown"]
    critical_nodes = [node for node in nodes if node["route_role"] == "critical"]
    optional_nodes = [node for node in nodes if node["route_role"] == "optional"]

    unknown_hotspots = sorted(
        trigger_unknown_nodes,
        key=lambda node: (node["row_count"], len(node["flag_gates"])),
        reverse=True,
    )[:10]
    conditional_hotspots = sorted(
        conditional_nodes,
        key=lambda node: (len(node["flag_gates"]), node["row_count"]),
        reverse=True,
    )[:10]

    return {
        "file": file_name,
        "readiness": rate_file(payload),
        "node_count": payload["node_count"],
        "edge_count": payload["edge_count"],
        "dispatch_edge_count": payload["dispatch_edge_count"],
        "event_transition_edge_count": payload["event_transition_edge_count"],
        "room_transition_edge_count": payload["room_transition_edge_count"],
        "action_target_pairs": payload["action_target_pairs"],
        "destinations": payload["destinations"],
        "route_known_count": len(route_known_nodes),
        "conditional_count": len(conditional_nodes),
        "trigger_unknown_count": len(trigger_unknown_nodes),
        "critical_count": len(critical_nodes),
        "optional_count": len(optional_nodes),
        "unknown_hotspots": [
            {
                "id": node["id"],
                "block_command": node["block_command"],
                "start_offset": node["start_offset"],
                "row_count": node["row_count"],
                "display_types": node["display_types"],
                "route_status": node["route_status"],
                "route_role": node["route_role"],
                "flag_gates": node["flag_gates"],
                "english_preview": node["english_preview"],
            }
            for node in unknown_hotspots
        ],
        "conditional_hotspots": [
            {
                "id": node["id"],
                "block_command": node["block_command"],
                "start_offset": node["start_offset"],
                "row_count": node["row_count"],
                "display_types": node["display_types"],
                "route_status": node["route_status"],
                "route_role": node["route_role"],
                "flag_gates": node["flag_gates"],
                "english_preview": node["english_preview"],
            }
            for node in conditional_hotspots
        ],
    }


def build_acceptance_outline(graph: dict[str, Any]) -> dict[str, Any]:
    files = [summarize_file(file_name, payload) for file_name, payload in graph["files"].items()]
    files.sort(
        key=lambda item: (
            {"weak": 0, "partial": 1, "strong": 2}[item["readiness"]],
            -item["trigger_unknown_count"],
            -item["conditional_count"],
        )
    )

    return {
        "global_summary": graph["global_summary"],
        "ready_files": [item["file"] for item in files if item["readiness"] == "strong"],
        "partial_files": [item["file"] for item in files if item["readiness"] == "partial"],
        "weak_files": [item["file"] for item in files if item["readiness"] == "weak"],
        "files": files,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Summarize state-graph coverage into a walkthrough-readiness outline.")
    parser.add_argument("--state-graph", type=Path, required=True, help="Path to state_graph.json")
    parser.add_argument("--output", type=Path, help="Write JSON to this path instead of stdout")
    args = parser.parse_args()

    outline = build_acceptance_outline(load_json(args.state_graph))
    rendered = json.dumps(outline, indent=2, ensure_ascii=False)
    if args.output:
        args.output.write_text(rendered, encoding="utf-8")
    else:
        print(rendered)


if __name__ == "__main__":
    main()
