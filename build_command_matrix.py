from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def build_command_matrix(graph: dict[str, Any]) -> dict[str, Any]:
    matrix: dict[str, Any] = {}

    for file_name, payload in graph["files"].items():
        actions: dict[str, dict[str, Any]] = {}

        for node in payload["nodes"]:
            for trigger in node.get("dispatch_triggers", []):
                action = (trigger.get("action") or "").strip() or "(unknown action)"
                target = (trigger.get("target") or "").strip() or "(unknown target)"
                action_bucket = actions.setdefault(action, {})
                target_bucket = action_bucket.setdefault(
                    target,
                    {
                        "nodes": [],
                        "destinations": [],
                        "handoffs": [],
                        "flags": [],
                    },
                )

                node_entry = {
                    "id": node["id"],
                    "block_command": node["block_command"],
                    "commands": node["commands"],
                    "start_offset": node["start_offset"],
                    "row_count": node["row_count"],
                    "display_types": node["display_types"],
                    "english_preview": node["english_preview"],
                }
                if node_entry not in target_bucket["nodes"]:
                    target_bucket["nodes"].append(node_entry)

                for transition in node.get("transitions", []):
                    destination = transition.get("destination_label")
                    if destination and destination not in target_bucket["destinations"]:
                        target_bucket["destinations"].append(destination)

                for handoff in node.get("handoffs", []):
                    label = handoff.get("destination_label")
                    if label and label not in target_bucket["handoffs"]:
                        target_bucket["handoffs"].append(label)

                for flag in node.get("flag_gates", []):
                    flag_entry = {
                        "kind": flag.get("kind"),
                        "arg1": flag.get("arg1"),
                        "arg2": flag.get("arg2"),
                    }
                    if flag_entry not in target_bucket["flags"]:
                        target_bucket["flags"].append(flag_entry)

        matrix[file_name] = {
            "action_count": len(actions),
            "actions": actions,
        }

    return matrix


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a walkthrough-friendly action/target command matrix from state_graph.json.")
    parser.add_argument("--state-graph", type=Path, required=True, help="Path to state_graph.json")
    parser.add_argument("--output", type=Path, help="Write JSON to this path instead of stdout")
    args = parser.parse_args()

    matrix = build_command_matrix(load_json(args.state_graph))
    rendered = json.dumps(matrix, indent=2, ensure_ascii=False)
    if args.output:
        args.output.write_text(rendered, encoding="utf-8")
    else:
        print(rendered)


if __name__ == "__main__":
    main()
