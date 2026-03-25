from __future__ import annotations

from collections.abc import Container


def normalize_msd_row_offset(offset: int, known_offsets: Container[int], text_bytes: bytes) -> int:
    if offset in known_offsets:
        return offset
    if offset < 0 or offset + 1 >= len(text_bytes):
        return offset
    if text_bytes[offset] == 0xF3 and (offset + 1) in known_offsets:
        return offset + 1
    return offset
