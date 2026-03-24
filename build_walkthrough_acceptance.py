from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def rate_file(payload: dict[str, Any]) -> str:
    node_count = payload["node_count"] or 1
    dispatch_edges = payload["dispatch_edge_count"]
    special_edges = payload["handoff_edge_count"] + payload["transition_edge_count"]
    unattached_nodes = sum(
        1
        for node in payload["nodes"]
        if not node["dispatch_triggers"] and not node["handoffs"] and not node["transitions"]
    )
    unattached_ratio = unattached_nodes / node_count

    if dispatch_edges >= 10 and unattached_ratio < 0.5:
        return "strong"
    if dispatch_edges > 0 or special_edges > 0:
        return "partial"
    return "weak"


def summarize_file(file_name: str, payload: dict[str, Any]) -> dict[str, Any]:
    nodes = payload["nodes"]
    unattached_nodes = [
        node
        for node in nodes
        if not node["dispatch_triggers"] and not node["handoffs"] and not node["transitions"]
    ]
    flagged_unattached = [node for node in unattached_nodes if node["flag_gates"]]

    hotspots = sorted(
        flagged_unattached,
        key=lambda node: (len(node["flag_gates"]), node["row_count"]),
        reverse=True,
    )[:10]

    return {
        "file": file_name,
        "readiness": rate_file(payload),
        "node_count": payload["node_count"],
        "edge_count": payload["edge_count"],
        "dispatch_edge_count": payload["dispatch_edge_count"],
        "handoff_edge_count": payload["handoff_edge_count"],
        "transition_edge_count": payload["transition_edge_count"],
        "action_target_pairs": payload["action_target_pairs"],
        "destinations": payload["destinations"],
        "unattached_node_count": len(unattached_nodes),
        "flagged_unattached_count": len(flagged_unattached),
        "hotspots": [
            {
                "id": node["id"],
                "block_command": node["block_command"],
                "start_offset": node["start_offset"],
                "row_count": node["row_count"],
                "display_types": node["display_types"],
                "flag_gates": node["flag_gates"],
                "english_preview": node["english_preview"],
            }
            for node in hotspots
        ],
    }


def build_acceptance_outline(graph: dict[str, Any]) -> dict[str, Any]:
    files = [summarize_file(file_name, payload) for file_name, payload in graph["files"].items()]
    files.sort(
        key=lambda item: (
            {"weak": 0, "partial": 1, "strong": 2}[item["readiness"]],
            -item["flagged_unattached_count"],
            -item["unattached_node_count"],
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
