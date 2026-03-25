"""
Screen state classifier for Possessioner emulator automation.

Uses the Claude vision API (haiku model) to classify a captured screenshot
into one of five game states, so the automation can decide whether to press
SPACE, navigate a menu, or wait.

Usage as a module:
    from screen_state import classify_screen_state
    state = classify_screen_state(pil_image)   # returns e.g. 'action_menu'

Usage as a CLI smoke-test:
    python screen_state.py screens/hq-move-patch-action2/00-after-load-state.png
    # should print: action_menu
"""
from __future__ import annotations

import base64
import io
import sys
from pathlib import Path

import anthropic
from PIL import Image

MODEL = "claude-haiku-4-5-20251001"

# States and their distinctive visual signatures (used in the classification prompt)
_STATE_DESCRIPTIONS = {
    "action_menu": (
        "The game is displaying a scene (background visible, possibly a character portrait "
        "in the upper right) with a vertical column of 5–7 action-verb buttons on the RIGHT "
        "side of the game area. These buttons contain short Japanese text (e.g. 見る, 話す, "
        "調べる, 移動, 考える). This is the state where the player selects an action."
    ),
    "dialogue": (
        "The game is displaying a scene with a TEXT BOX at the bottom of the screen containing "
        "Japanese dialogue or narration. A character portrait may be visible on the right. "
        "The action-verb column on the right is NOT visible or is replaced by a portrait. "
        "Text is being shown but the player has not yet chosen an action from a menu."
    ),
    "cutscene": (
        "A FULL-SCREEN or near-full-screen scene is showing, typically with Japanese text "
        "overlaid on a dark/coloured background. No action menu is present. This includes "
        "story sequences, animated transitions, and inter-scene narration panels."
    ),
    "loading": (
        "The screen is MOSTLY BLACK, or shows a company logo (e.g. 'Queen Soft' in red/blue "
        "letters), or shows the POSSESSIONER title card. The game is loading or transitioning "
        "between states and is not yet interactive."
    ),
    "battle": (
        "The screen shows a BATTLE SCENE with a completely different layout from normal "
        "gameplay: character and enemy portraits arranged for combat, HP or status indicators, "
        "and a combat-specific menu (e.g. attack/item options). The standard background scene "
        "and action-verb column are not present."
    ),
}

_VALID_STATES = set(_STATE_DESCRIPTIONS)

_PROMPT = (
    "This screenshot is from the PC-98 visual novel Possessioner running in "
    "Neko Project 21 emulator. Identify which of the following game states the "
    "screenshot shows, then reply with ONLY the state name — no explanation.\n\n"
    + "\n\n".join(
        f"- {name}: {desc}" for name, desc in _STATE_DESCRIPTIONS.items()
    )
    + "\n\nReply with exactly one of: "
    + ", ".join(_STATE_DESCRIPTIONS)
    + "."
)


def classify_screen_state(image: Image.Image) -> str:
    """Classify a PIL screenshot into one of the five game states.

    Returns one of: 'action_menu', 'dialogue', 'cutscene', 'loading', 'battle',
    or 'unknown' if the API response cannot be mapped to a known state.

    Requires the ANTHROPIC_API_KEY environment variable to be set.
    """
    buf = io.BytesIO()
    image.save(buf, format="PNG")
    b64 = base64.standard_b64encode(buf.getvalue()).decode()

    client = anthropic.Anthropic()
    response = client.messages.create(
        model=MODEL,
        max_tokens=20,
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": "image/png",
                            "data": b64,
                        },
                    },
                    {"type": "text", "text": _PROMPT},
                ],
            }
        ],
    )
    raw = response.content[0].text.strip().lower()
    # Accept the response if it contains any valid state name
    for state in _VALID_STATES:
        if state in raw:
            return state
    return "unknown"


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python screen_state.py <image_path> [<image_path> ...]")
        sys.exit(1)
    for arg in sys.argv[1:]:
        path = Path(arg)
        img = Image.open(path)
        state = classify_screen_state(img)
        print(f"{path.name}: {state}")
