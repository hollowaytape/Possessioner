from __future__ import annotations

import json
from pathlib import Path

from PIL import Image

REPO_ROOT = Path(__file__).resolve().parent
MANIFEST_PATH = REPO_ROOT / "script_viewer" / "assets" / "locations" / "phon1-manifest.json"
VIEWER_DIR = REPO_ROOT / "script_viewer" / "assets" / "locations" / "viewer"
VIEWER_SCENE_DIR = VIEWER_DIR / "scene"
VIEWER_FULL_DIR = VIEWER_DIR / "full"

# Captured emulator screenshots are 648x451 with a fixed 640x400 game frame inset.
GAME_FRAME_BOX = (4, 42, 644, 442)

# Match the script viewer mock scene-panel proportions for room/location backdrops.
SCENE_PANEL_BOX = (31, 19, 476, 254)

BATTLE_MARKERS = ("battle", "attack")
FULL_FRAME_SCENE_MARKER = "scene"


def relative_repo_path(path: Path) -> str:
    return str(path.relative_to(REPO_ROOT)).replace("\\", "/")


def is_battle_label(label: str) -> bool:
    lowered = label.lower()
    return any(marker in lowered for marker in BATTLE_MARKERS)


def is_full_frame_scene_label(label: str) -> bool:
    lowered = label.lower()
    return FULL_FRAME_SCENE_MARKER in lowered and not is_battle_label(lowered)


def build_viewer_variants(image_path: Path) -> tuple[Image.Image, Image.Image]:
    with Image.open(image_path) as image:
        frame = image.crop(GAME_FRAME_BOX)
        scene = frame.crop(SCENE_PANEL_BOX)
        return frame.copy(), scene.copy()


def main() -> None:
    payload = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    VIEWER_SCENE_DIR.mkdir(parents=True, exist_ok=True)
    VIEWER_FULL_DIR.mkdir(parents=True, exist_ok=True)

    processed = 0
    skipped = 0

    for item in payload.get("locations", []):
        label = str(item.get("label") or "")
        image_rel = str(item.get("image") or "")
        image_path = REPO_ROOT / Path(image_rel.replace("/", "\\"))

        full_image, scene_image = build_viewer_variants(image_path)
        full_output_path = VIEWER_FULL_DIR / image_path.name
        scene_output_path = VIEWER_SCENE_DIR / image_path.name
        full_image.save(full_output_path)
        scene_image.save(scene_output_path)

        default_full = is_full_frame_scene_label(label) or is_battle_label(label)
        default_image = full_image if default_full else scene_image
        default_output_path = full_output_path if default_full else scene_output_path

        item["viewer_usable"] = not is_battle_label(label)
        item["viewer_crop"] = "full-frame" if default_full else "scene-panel"
        item["viewer_image"] = relative_repo_path(default_output_path)
        item["viewer_size"] = {"width": default_image.width, "height": default_image.height}
        item["viewer_full_image"] = relative_repo_path(full_output_path)
        item["viewer_full_size"] = {"width": full_image.width, "height": full_image.height}
        item["viewer_scene_image"] = relative_repo_path(scene_output_path)
        item["viewer_scene_size"] = {"width": scene_image.width, "height": scene_image.height}
        if item["viewer_usable"]:
            processed += 1
        else:
            skipped += 1

    MANIFEST_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"Processed {processed} viewer-ready captures")
    print(f"Skipped {skipped} battle captures")
    print(f"Updated manifest: {MANIFEST_PATH}")


if __name__ == "__main__":
    main()
