from __future__ import annotations

from typing import Any


KNOWN_BATTLE_NODES: list[dict[str, Any]] = [
    {
        "file": "RASU1.MSD",
        "start_offset": "0x00585",
        "label": "Encounter -> same-file aftermath",
        "kind": "same_file_aftermath",
        "destination_label": '0x27 "Sewer, gondola top (2 lines)"',
        "launch_location": "0x2705d",
        "flags": ["0x98 = 0x01"],
        "status": "verified",
        "notes": "Skipping the shared 0x348e launch reproduces the real post-battle save diff.",
    },
    {
        "file": "RASU1.MSD",
        "start_offset": "0x010f9",
        "label": "Encounter -> same-file aftermath",
        "kind": "same_file_aftermath",
        "destination_label": '0x29 "Sewer, still on gondola (5 lines)"',
        "launch_location": "0x271eb",
        "flags": ["0x9a = 0x01"],
        "status": "verified",
        "notes": "Skipping the shared 0x348e launch reproduces the real elevator aftermath flag change.",
    },
    {
        "file": "YUMI.MSD",
        "start_offset": "0x0297c",
        "label": "Battle aftermath -> Yumi scene",
        "kind": "scene_return",
        "destination_label": '0x56 "Yumi scene"',
        "launch_location": "0x109e6",
        "flags": [],
        "status": "verified",
        "notes": "The reward/aftermath path ends by writing 0x56 to 6b8a and dispatching to the Yumi scene.",
    },
    {
        "file": "YUMI.MSD",
        "start_offset": "0x029db",
        "label": "Battle aftermath -> Yumi scene",
        "kind": "scene_return",
        "destination_label": '0x56 "Yumi scene"',
        "launch_location": "0x109e6",
        "flags": [],
        "status": "verified",
        "notes": "The reward/aftermath path ends by writing 0x56 to 6b8a and dispatching to the Yumi scene.",
    },
]


def annotate_graph_with_battle_knowledge(state_graph: dict[str, Any]) -> None:
    by_file_offset = {
        (entry["file"], entry["start_offset"].lower()): entry for entry in KNOWN_BATTLE_NODES
    }

    total_encounters = 0
    total_nodes = 0
    for file_name, payload in (state_graph.get("files") or {}).items():
        file_encounters = 0
        file_nodes = 0
        for node in payload.get("nodes", []):
            match = by_file_offset.get((file_name, str(node.get("start_offset") or "").lower()))
            if not match:
                continue
            node["battle_encounters"] = [match]
            file_encounters += 1
            file_nodes += 1
        payload["battle_encounter_count"] = file_encounters
        payload["battle_encounter_node_count"] = file_nodes
        total_encounters += file_encounters
        total_nodes += file_nodes

    summary = state_graph.setdefault("global_summary", {})
    summary["battle_encounter_count"] = total_encounters
    summary["battle_encounter_node_count"] = total_nodes
