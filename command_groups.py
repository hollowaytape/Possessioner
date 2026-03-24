from __future__ import annotations

from collections import defaultdict
from pathlib import Path

from rominfo import ARRIVAL_POINTERS, MSD_POINTER_RANGES, ORIGINAL_ROM_DIR

ALLOWED_PRECEDING_BYTES = {
    0x00, 0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07, 0x08,
    0x09, 0x0A, 0x0B, 0x0C, 0x0D, 0x0E, 0x0F, 0x10, 0x11, 0x12, 0x13, 0x14, 0x15, 0x16, 0x17,
    0x18, 0x19, 0x1A, 0x1B, 0x1C, 0x1D, 0x1E, 0x1F, 0x20, 0x21, 0x22, 0x23, 0x24, 0x2B, 0x39, 0xFF,
}


def parse_offset(value: object) -> int | None:
    if value is None:
        return None
    if isinstance(value, int):
        return value
    text = str(value).strip()
    if not text:
        return None
    return int(text, 16)


def format_offset(offset: int) -> str:
    return f"0x{offset:05x}"


def load_pos_exe_bytes(pos_exe_path: Path | None = None) -> bytes:
    if pos_exe_path is None:
        pos_exe_path = Path(ORIGINAL_ROM_DIR) / "POS.EXE"
    return pos_exe_path.read_bytes()


def find_command_groups(
    filename: str,
    row_offsets: list[int],
    pos_exe_bytes: bytes,
) -> tuple[dict[int, int], dict[int, list[tuple[int, int]]]]:
    groups_by_start: dict[int, int] = {}
    grouped_rows: dict[int, dict[int, int]] = defaultdict(dict)

    if filename not in MSD_POINTER_RANGES:
        return groups_by_start, {}

    offset_to_index = {offset: index for index, offset in enumerate(row_offsets)}

    for range_start, range_stop in MSD_POINTER_RANGES[filename]:
        scan_start = max(1, range_start)
        scan_stop = min(range_stop, len(pos_exe_bytes) - 3)

        for pointer_location in range(scan_start, scan_stop + 1):
            if pointer_location < 2:
                continue
            if pos_exe_bytes[pointer_location - 1] != 0x02:
                continue
            if pos_exe_bytes[pointer_location] == 0xFF:
                continue
            if pos_exe_bytes[pointer_location - 2] not in ALLOWED_PRECEDING_BYTES:
                continue

            text_offset = pos_exe_bytes[pointer_location] | (pos_exe_bytes[pointer_location + 1] << 8)
            group_size = pos_exe_bytes[pointer_location + 2]

            start_index = offset_to_index.get(text_offset)
            if text_offset <= 0 or start_index is None or group_size <= 0:
                continue

            group_rows = row_offsets[start_index : start_index + group_size]
            if len(group_rows) != group_size:
                continue

            existing_size = groups_by_start.get(text_offset)
            if existing_size is None or group_size > existing_size:
                groups_by_start[text_offset] = group_size

            for row_offset in group_rows:
                grouped_rows[row_offset][text_offset] = group_size

    normalized_groups = {
        row_offset: sorted(group_map.items(), key=lambda item: item[0])
        for row_offset, group_map in grouped_rows.items()
    }
    return groups_by_start, normalized_groups


def find_arrival_groups(
    filename: str,
    row_offsets: list[int],
    pos_exe_bytes: bytes,
) -> dict[int, list[tuple[int, int, int]]]:
    grouped_rows: dict[int, dict[tuple[int, int, int], None]] = defaultdict(dict)
    offset_to_index = {offset: index for index, offset in enumerate(row_offsets)}

    for text_offset, pointer_location in ARRIVAL_POINTERS.get(filename, []):
        start_index = offset_to_index.get(text_offset)
        if start_index is None:
            continue
        if pointer_location + 2 >= len(pos_exe_bytes):
            continue
        group_size = pos_exe_bytes[pointer_location + 2]
        if group_size <= 0:
            group_size = 1
        group_rows = row_offsets[start_index : start_index + group_size]
        if not group_rows:
            continue
        for row_offset in group_rows:
            grouped_rows[row_offset][(text_offset, group_size, pointer_location)] = None

    return {
        row_offset: sorted(group_map.keys(), key=lambda item: (item[0], item[2]))
        for row_offset, group_map in grouped_rows.items()
    }


def find_direct_range_groups(
    filename: str,
    row_offsets: list[int],
    pos_exe_bytes: bytes,
) -> dict[int, list[tuple[int, int, int]]]:
    grouped_rows: dict[int, dict[tuple[int, int, int], None]] = defaultdict(dict)

    if filename not in MSD_POINTER_RANGES:
        return {}

    offset_to_index = {offset: index for index, offset in enumerate(row_offsets)}

    for range_start, range_stop in MSD_POINTER_RANGES[filename]:
        scan_start = max(0, range_start)
        scan_stop = min(range_stop, len(pos_exe_bytes) - 11)

        for cursor in range(scan_start, scan_stop + 1):
            if pos_exe_bytes[cursor] != 0xBE:
                continue
            if pos_exe_bytes[cursor + 3] != 0xB9:
                continue
            if pos_exe_bytes[cursor + 6] != 0x9A:
                continue
            if pos_exe_bytes[cursor + 7 : cursor + 11] != b"\x46\x22\xf0\x05":
                continue

            text_offset = pos_exe_bytes[cursor + 1] | (pos_exe_bytes[cursor + 2] << 8)
            group_size = pos_exe_bytes[cursor + 4] | (pos_exe_bytes[cursor + 5] << 8)

            start_index = offset_to_index.get(text_offset)
            if start_index is None or group_size <= 0:
                continue

            group_rows = row_offsets[start_index : start_index + group_size]
            if len(group_rows) != group_size:
                continue

            for row_offset in group_rows:
                grouped_rows[row_offset][(text_offset, group_size, cursor)] = None

    return {
        row_offset: sorted(group_map.keys(), key=lambda item: (item[0], item[2]))
        for row_offset, group_map in grouped_rows.items()
    }

