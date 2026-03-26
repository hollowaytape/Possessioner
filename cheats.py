from __future__ import annotations

# Battle-launch calls we can safely skip with current RE.
# For literal `mov ss:[6b8a], scene_id` aftermath routes, NOPing the shared 0x348e
# launch call lets the existing reward/aftermath code run.
# The two RASU1 sites are same-file aftermaths that preserve their verified flag paths
# when the launch call is skipped.
SKIP_BATTLE_LAUNCH_CALLS = {
    0x2705D: "RASU1 first sewer battle",
    0x271EB: "RASU1 elevator battle",
    0x109E6: "YUMI -> scene 0x56",
    0x1A3DE: "TINA -> scene 0x12",
    0x1A702: "END/fairy -> scene 0x19",
    0x24941: "AYAKA -> scene 0x0a",
    0x24D16: "MINS -> scene 0x0d",
    0x2507C: "RASU2 / PLYM -> scene 0x09",
    0x2745C: "MAI -> scene 0x0c",
    0x28640: "MISHA -> scene 0x0b",
}


def apply_pos_cheats(gamefile, enemy_name_locations) -> None:
    # Instant text display
    gamefile.edit(0xA3BF, b"\xA8\x03")

    # One-hit kill: set HP=0 and state=dead for every enemy entry
    for loc in enemy_name_locations:
        gamefile.edit(loc - 9, b"\x00")
        gamefile.edit(loc - 10, b"\x80")

    for launch_call_offset in SKIP_BATTLE_LAUNCH_CALLS:
        gamefile.edit(launch_call_offset, b"\x90\x90\x90\x90\x90")
