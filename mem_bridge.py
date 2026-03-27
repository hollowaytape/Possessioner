"""mem_bridge.py — Read PC-98 game RAM from the np2debug emulator process.

Uses Win32 ReadProcessMemory to locate and read the emulated PC-98's main
RAM buffer inside the np2debug process.  The base address is found via a
one-time pattern scan that matches known save-state bytes.

Typical usage:

    from mem_bridge import MemBridge
    bridge = MemBridge.attach(hwnd)
    map_byte = bridge.read_map_byte()
    flag_set = bridge.read_flag(0x7b, 0)
    bridge.close()
"""

from __future__ import annotations

import ctypes
import ctypes.wintypes as wt
import struct
import time
from dataclasses import dataclass

# ── Win32 constants ──────────────────────────────────────────────────

PROCESS_VM_READ = 0x0010
PROCESS_QUERY_INFORMATION = 0x0400
MEM_COMMIT = 0x1000
PAGE_NOACCESS = 0x01
PAGE_GUARD = 0x100

kernel32 = ctypes.windll.kernel32
user32 = ctypes.windll.user32


class MEMORY_BASIC_INFORMATION(ctypes.Structure):
    _fields_ = [
        ("BaseAddress", ctypes.c_void_p),
        ("AllocationBase", ctypes.c_void_p),
        ("AllocationProtect", wt.DWORD),
        ("RegionSize", ctypes.c_size_t),
        ("State", wt.DWORD),
        ("Protect", wt.DWORD),
        ("Type", wt.DWORD),
    ]


# ── Save-format offsets (from docs/save_format.txt) ─────────────────

OFF_MAP = 0x00        # Current map/scene index byte
OFF_FLAGS = 0x02      # Event flags start (256 bytes = 2048 flag bits)
OFF_FLAGS_END = 0x102
OFF_ROOM = 0x5E       # Current room (within map)
OFF_STATS = 0x100     # Character stats block start

# Size of the game state region we care about (first ~512 bytes is safe)
_SCAN_SIZE = 0x200

# ── Segment-relative layout ─────────────────────────────────────────
# The game saves/loads via DOS INT 21h with DX=0x6B8A and CX=0x013D,
# meaning the 317-byte save block starts at segment offset 0x6B8A.
# Our `base` address points at save byte 0 (the map byte), so:
#   segment_addr = base + (seg_offset - SEG_SAVE_START)

SEG_SAVE_START = 0x6B8A   # Segment offset where save data lives

# Menu-state variables (segment-relative offsets), validated by live
# memory diffing across verb menu → target menu → dialogue transitions.
SEG_MENU_DEPTH = 0x2D2A   # 0 = verb/top level, 1 = target/sub level
SEG_MENU_TEXT  = 0x2D2C   # complement of MENU_DEPTH (1=verb, 0=target)
SEG_MENU_COUNT = 0x2D40   # Number of items in the current visible menu
SEG_CURSOR_POS = 0x2D42   # 0-based cursor position in current menu


def _get_process_id(hwnd: int) -> int:
    """Return the PID owning *hwnd*."""
    pid = ctypes.c_ulong()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    if pid.value == 0:
        raise OSError(f"GetWindowThreadProcessId failed for hwnd {hwnd}")
    return int(pid.value)


def _open_process(pid: int) -> int:
    """Open the process for memory reading.  Returns a process handle."""
    access = PROCESS_VM_READ | PROCESS_QUERY_INFORMATION
    handle = kernel32.OpenProcess(access, False, pid)
    if not handle:
        raise OSError(f"OpenProcess failed for PID {pid} "
                      f"(error {ctypes.GetLastError()})")
    return handle


def _read_bytes(handle: int, address: int, size: int) -> bytes:
    """Read *size* bytes from *address* in the target process."""
    buf = ctypes.create_string_buffer(size)
    bytes_read = ctypes.c_size_t(0)
    ok = kernel32.ReadProcessMemory(
        handle, ctypes.c_void_p(address), buf, size,
        ctypes.byref(bytes_read),
    )
    if not ok:
        raise OSError(f"ReadProcessMemory failed at 0x{address:X} "
                      f"(error {ctypes.GetLastError()})")
    return buf.raw[:bytes_read.value]


def _scan_for_pattern(handle: int, pattern: bytes,
                      *, max_address: int = 0x7FFFFFFF,
                      alignment: int = 0x1000) -> list[int]:
    """Scan readable committed regions for *pattern*.  Returns all matches."""
    matches: list[int] = []
    addr = 0
    mbi = MEMORY_BASIC_INFORMATION()
    mbi_size = ctypes.sizeof(mbi)

    while addr < max_address:
        ret = kernel32.VirtualQueryEx(
            handle, ctypes.c_void_p(addr), ctypes.byref(mbi), mbi_size,
        )
        if ret == 0:
            break

        region_base = mbi.BaseAddress if mbi.BaseAddress else addr
        region_size = mbi.RegionSize

        # Only scan committed, readable regions
        if (mbi.State == MEM_COMMIT
                and mbi.Protect not in (PAGE_NOACCESS, PAGE_GUARD, 0)
                and not (mbi.Protect & PAGE_GUARD)):
            try:
                data = _read_bytes(handle, region_base, region_size)
            except OSError:
                pass
            else:
                offset = 0
                while True:
                    idx = data.find(pattern, offset)
                    if idx < 0:
                        break
                    matches.append(region_base + idx)
                    offset = idx + 1

        # Advance to next region
        next_addr = region_base + region_size
        if next_addr <= addr:
            addr += 0x1000
        else:
            addr = next_addr

    return matches


# ── Public API ───────────────────────────────────────────────────────

@dataclass
class MemBridge:
    """Live connection to the emulated PC-98 game state in np2debug."""

    handle: int     # Win32 process handle
    pid: int
    base: int       # Address of the game-state block (save-format byte 0x00)

    # ── Construction ─────────────────────────────────────────────────

    @classmethod
    def attach(cls, hwnd: int, *,
               reference_save: bytes | None = None,
               known_base: int | None = None,
               timeout: float = 10.0) -> MemBridge:
        """Attach to the emulator process owning *hwnd*.

        *known_base* — if a previous session already found the base address,
        pass it here to skip the scan.  The address is validated before use.

        *reference_save* — the full content of the save file currently loaded
        in the emulator.  The stats block (bytes 0x100+) is used as the
        primary scan pattern because character stats are constant and
        distinctive.  Falls back to scanning the flag region.
        """
        pid = _get_process_id(hwnd)
        handle = _open_process(pid)

        try:
            if known_base is not None:
                # Validate the cached base is still good
                try:
                    _read_bytes(handle, known_base, 1)
                    base = known_base
                except OSError:
                    base = cls._find_game_state(handle, reference_save, timeout)
            else:
                base = cls._find_game_state(handle, reference_save, timeout)
        except Exception:
            kernel32.CloseHandle(handle)
            raise

        return cls(handle=handle, pid=pid, base=base)

    @classmethod
    def _find_game_state(cls, handle: int,
                         reference_save: bytes | None,
                         timeout: float) -> int:
        """Locate the game-state base address via pattern scanning.

        Strategy:
        1. Primary: scan for the stats block (offsets 0x100–0x120 of the save
           file).  Character stats contain distinctive non-zero byte sequences
           that are stable across scenes.
        2. Fallback: scan for the flags region (offsets 0x02–0x20) which
           contains the initial flag pattern.
        3. Final fallback: scan for the first 32 bytes of the save verbatim.

        For each candidate address, we read 0x200 bytes and verify the map
        byte is in range and the stats pattern matches at the expected offset.
        """
        if reference_save is None or len(reference_save) < 0x120:
            raise ValueError(
                "reference_save (full save file content, ≥288 bytes) is "
                "required for base-address discovery"
            )

        # Build candidate patterns ordered by distinctiveness
        patterns: list[tuple[str, int, bytes]] = []

        # Stats block: offsets 0x102–0x11C (26 bytes, mostly non-zero)
        stats = reference_save[0x102:0x11C]
        if any(b != 0 for b in stats):
            patterns.append(("stats", 0x102, stats))

        # Flags region: offsets 0x02–0x22 (32 bytes including flag start)
        flags = reference_save[0x02:0x22]
        if any(b != 0 for b in flags):
            patterns.append(("flags", 0x02, flags))

        # Head: first 32 bytes verbatim
        head = reference_save[:32]
        patterns.append(("head", 0, head))

        deadline = time.time() + timeout

        for label, offset_in_save, pattern in patterns:
            while True:
                matches = _scan_for_pattern(handle, pattern)
                if matches:
                    # Each match is where *pattern* was found.  Subtract the
                    # save-file offset to get the candidate base address.
                    candidates = [addr - offset_in_save for addr in matches]
                    valid = cls._validate_candidates(
                        handle, candidates, reference_save
                    )
                    if valid:
                        return valid[0]
                if time.time() >= deadline:
                    break
                time.sleep(0.3)

        raise RuntimeError(
            f"Could not find game-state pattern in emulator memory. "
            f"Tried {len(patterns)} pattern(s) over {timeout}s."
        )

    @staticmethod
    def _validate_candidates(handle: int, candidates: list[int],
                             reference_save: bytes) -> list[int]:
        """Filter candidate base addresses by cross-checking multiple offsets."""
        valid = []
        save_len = len(reference_save)
        for base in candidates:
            if base < 0:
                continue
            try:
                block = _read_bytes(handle, base, min(save_len, _SCAN_SIZE))
            except OSError:
                continue
            # Map byte must be in plausible range (0x00–0x60)
            if block[OFF_MAP] > 0x60:
                continue
            # Stats signature: check that the stats area matches the reference
            # (these bytes don't change during gameplay for initial stats)
            if save_len > 0x110:
                ref_stats = reference_save[0x103:0x106]  # D2 00 D2 pattern
                mem_stats = block[0x103:0x106]
                if ref_stats == mem_stats:
                    valid.append(base)
                    continue
            # If we can't check stats, accept based on map byte alone
            valid.append(base)
        return valid

    # ── Lifecycle ────────────────────────────────────────────────────

    def close(self) -> None:
        """Release the process handle."""
        if self.handle:
            kernel32.CloseHandle(self.handle)
            self.handle = 0

    def __enter__(self) -> MemBridge:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def is_valid(self) -> bool:
        """Check that the process handle is still usable."""
        try:
            _read_bytes(self.handle, self.base, 1)
            return True
        except OSError:
            return False

    # ── Reads ────────────────────────────────────────────────────────

    def read_byte(self, offset: int) -> int:
        """Read a single byte at *offset* from the game state base."""
        data = _read_bytes(self.handle, self.base + offset, 1)
        return data[0]

    def read_bytes(self, offset: int, size: int) -> bytes:
        """Read *size* bytes at *offset* from the game state base."""
        return _read_bytes(self.handle, self.base + offset, size)

    def read_word(self, offset: int) -> int:
        """Read a 16-bit little-endian word at *offset*."""
        data = _read_bytes(self.handle, self.base + offset, 2)
        return struct.unpack("<H", data)[0]

    def read_map_byte(self) -> int:
        """Current map/scene index (0x00–0x57+)."""
        return self.read_byte(OFF_MAP)

    def read_room_byte(self) -> int:
        """Current room byte (offset 0x5E)."""
        return self.read_byte(OFF_ROOM)

    def read_flags(self) -> bytes:
        """All 256 event flag bytes (offsets 0x02–0x102)."""
        return self.read_bytes(OFF_FLAGS, OFF_FLAGS_END - OFF_FLAGS)

    def read_flag(self, flag_id: int, flag_bit: int) -> bool:
        """Check whether a specific event flag is set.

        *flag_id* is the byte index (0x00–0xFF) within the flag area.
        *flag_bit* is the bit index (0–7) within that byte.
        """
        byte_val = self.read_byte(OFF_FLAGS + flag_id)
        return bool(byte_val & (1 << flag_bit))

    def read_stats(self) -> bytes:
        """Raw character stats block (offsets 0x100–0x126)."""
        return self.read_bytes(OFF_STATS, 0x26)

    def read_alisa_hp(self) -> tuple[int, int]:
        """Return (current_hp, max_hp) for Alisa."""
        cur = self.read_byte(0x10A)
        mx = self.read_byte(0x10B)
        return cur, mx

    # ── Segment-relative reads ──────────────────────────────────────

    def read_seg_byte(self, seg_addr: int) -> int:
        """Read one byte at a segment-relative address."""
        offset = seg_addr - SEG_SAVE_START
        return self.read_byte(offset)

    def read_seg_word(self, seg_addr: int) -> int:
        """Read a 16-bit LE word at a segment-relative address."""
        offset = seg_addr - SEG_SAVE_START
        return self.read_word(offset)

    def read_seg_bytes(self, seg_addr: int, size: int) -> bytes:
        """Read *size* bytes starting at a segment-relative address."""
        offset = seg_addr - SEG_SAVE_START
        return self.read_bytes(offset, size)

    # ── Menu state ──────────────────────────────────────────────────

    def menu_depth(self) -> int:
        """0 = verb/top-level menu, 1 = target/sub-level menu."""
        return self.read_seg_byte(SEG_MENU_DEPTH)

    def menu_count(self) -> int:
        """Number of items in the currently visible menu."""
        return self.read_seg_byte(SEG_MENU_COUNT)

    def cursor_pos(self) -> int:
        """0-based cursor position in the current menu."""
        return self.read_seg_byte(SEG_CURSOR_POS)

    def is_menu_ready(self) -> bool:
        """True when a menu is displayed and accepting input.

        When text/dialogue is showing, menu_depth and menu_text are briefly
        swapped.  A menu is ready when menu_depth and menu_text are
        complementary (they always sum to 1) AND menu_count > 0.
        """
        depth = self.read_seg_byte(SEG_MENU_DEPTH)
        text = self.read_seg_byte(SEG_MENU_TEXT)
        count = self.read_seg_byte(SEG_MENU_COUNT)
        return (depth + text == 1) and count > 0

    def menu_state(self) -> dict:
        """Full snapshot of menu state for debugging."""
        return {
            "depth": self.menu_depth(),
            "text": self.read_seg_byte(SEG_MENU_TEXT),
            "count": self.menu_count(),
            "cursor": self.cursor_pos(),
            "map": f"0x{self.read_map_byte():02X}",
        }

    # ── Snapshot / diff helpers ──────────────────────────────────────

    def snapshot(self, size: int = _SCAN_SIZE) -> bytes:
        """Capture a snapshot of the game state block."""
        return self.read_bytes(0, size)

    def diff(self, old: bytes, new: bytes) -> list[tuple[int, int, int]]:
        """Return list of (offset, old_byte, new_byte) for changed bytes."""
        changes = []
        for i in range(min(len(old), len(new))):
            if old[i] != new[i]:
                changes.append((i, old[i], new[i]))
        return changes

    def dump_state(self) -> dict:
        """Human-readable dump of key game state for debugging."""
        return {
            "map": f"0x{self.read_map_byte():02X}",
            "room": f"0x{self.read_room_byte():02X}",
            "alisa_hp": self.read_alisa_hp(),
            "flag_0x7b": self.read_flag(0x7B, 0),
        }

    # ── MSD text buffer ──────────────────────────────────────────────

    # The game loads MSD (dialogue) files into a buffer at physical
    # address 0x1E500 in the emulated PC-98 RAM.  DS=0x1E50 in the text
    # rendering routine at 2440:23EF.
    _MSD_PHYS = 0x1E500

    @property
    def ram_base(self) -> int:
        """Physical address 0 of the emulated PC-98's 1MB RAM."""
        return self.base - SEG_SAVE_START - 0x24400

    def read_msd_buffer(self, size: int = 0x8000) -> bytes:
        """Read the currently-loaded MSD file from the text buffer.

        The game loads one MSD file at a time into the buffer at physical
        address 0x1E500.  Returns up to *size* bytes (default 32KB,
        enough for the largest MSD files).
        """
        addr = self.ram_base + self._MSD_PHYS
        return _read_bytes(self.handle, addr, size)

    def read_game_segment(self, size: int = 0x10000) -> bytes:
        """Read the game code/data segment (POS.EXE in memory).

        The code segment starts at physical 0x24400 (segment 0x2440).
        Contains text pointer dispatch tables, flag checks, and handlers.
        """
        addr = self.ram_base + 0x24400
        return _read_bytes(self.handle, addr, size)

    def flags_snapshot(self) -> bytes:
        """Capture the 256-byte flag area for before/after comparison."""
        return self.read_flags()

    def flags_diff(self, before: bytes, after: bytes) -> list[tuple[int, int, int, int]]:
        """Compare two flag snapshots, return changed (byte, bit, old_val, new_val).

        Returns list of (flag_byte_index, bit_index, old_bit, new_bit)
        for each individual flag bit that changed.
        """
        changes = []
        for i in range(min(len(before), len(after))):
            if before[i] != after[i]:
                diff = before[i] ^ after[i]
                for bit in range(8):
                    if diff & (1 << bit):
                        old_bit = (before[i] >> bit) & 1
                        new_bit = (after[i] >> bit) & 1
                        changes.append((i, bit, old_bit, new_bit))
        return changes

    # ── Re-scan (if base address shifts) ────────────────────────────

    def rescan(self, reference_save: bytes) -> None:
        """Re-locate the game state base address after an emulator reset."""
        self.base = self._find_game_state(self.handle, reference_save, 10.0)


# ── CLI entry point for testing ──────────────────────────────────────

def main() -> None:
    import argparse
    import sys

    sys.path.insert(0, ".")
    from experiment_emulator_route import find_main_window

    parser = argparse.ArgumentParser(
        description="Test memory bridge against a running np2debug instance"
    )
    parser.add_argument(
        "--save", type=str, default=None,
        help="Path to the save file currently loaded in the emulator "
             "(default: auto-detect from patched/DATA*.SLD)"
    )
    parser.add_argument(
        "--pattern-hex", type=str, default=None,
        help="Hex string to use as scan pattern (advanced)"
    )
    parser.add_argument(
        "--dump", action="store_true",
        help="Dump the first 512 bytes of game state"
    )
    parser.add_argument(
        "--watch", type=float, default=0,
        help="Continuously read and display map byte every N seconds"
    )
    parser.add_argument(
        "--diff", action="store_true",
        help="Take two snapshots 3s apart and show changes"
    )
    args = parser.parse_args()

    # Find emulator window
    print("Looking for np2debug window...")
    hwnd = find_main_window(timeout=5.0)
    print(f"Found window: hwnd=0x{hwnd:X}")

    # Build reference from save file
    if args.pattern_hex:
        # Raw pattern mode — needs at least 288 bytes for the validator
        print("WARNING: --pattern-hex bypasses the standard save-file scan")
        reference = bytes.fromhex(args.pattern_hex)
    else:
        save_path = args.save
        if save_path is None:
            # Auto-detect: try patched saves in order
            from pathlib import Path
            for name in ["DATA1.SLD", "DATA2.SLD", "DATA3.SLD"]:
                candidate = Path("patched") / name
                if candidate.exists():
                    save_path = str(candidate)
                    break
            if save_path is None:
                parser.error("No save file found; use --save")

        with open(save_path, "rb") as f:
            reference = f.read()
        print(f"Using save file: {save_path} ({len(reference)} bytes)")
        print(f"  Map byte in save: 0x{reference[0]:02X}")
        print(f"  Stats signature: {reference[0x102:0x10C].hex()}")

    # Attach
    print("\nScanning emulator memory for game state...")
    t0 = time.time()
    bridge = MemBridge.attach(hwnd, reference_save=reference)
    elapsed = time.time() - t0
    print(f"✓ Found game state at base address: 0x{bridge.base:X} ({elapsed:.1f}s)")
    print(f"  PID: {bridge.pid}")

    # Read state
    state = bridge.dump_state()
    print(f"\nGame state:")
    for k, v in state.items():
        print(f"  {k}: {v}")

    if args.dump:
        data = bridge.snapshot(512)
        print(f"\nGame state dump ({len(data)} bytes):")
        for row in range(0, len(data), 16):
            chunk = data[row:row + 16]
            hex_part = " ".join(f"{b:02X}" for b in chunk)
            ascii_part = "".join(
                chr(b) if 0x20 <= b < 0x7F else "." for b in chunk
            )
            print(f"  {row:04X}: {hex_part:<48s}  {ascii_part}")

    if args.diff:
        print("\nTaking snapshot... (interact with the game, then wait 3s)")
        snap1 = bridge.snapshot(512)
        time.sleep(3.0)
        snap2 = bridge.snapshot(512)
        changes = bridge.diff(snap1, snap2)
        if changes:
            print(f"  {len(changes)} byte(s) changed:")
            for off, old, new in changes:
                print(f"    0x{off:04X}: 0x{old:02X} → 0x{new:02X}")
        else:
            print("  No changes detected.")

    if args.watch > 0:
        print(f"\nWatching map byte every {args.watch}s (Ctrl+C to stop):")
        try:
            prev_map = None
            prev_flags = None
            while True:
                mb = bridge.read_map_byte()
                flags = bridge.read_flags()
                if mb != prev_map:
                    print(f"  map: 0x{mb:02X}", flush=True)
                    prev_map = mb
                if flags != prev_flags and prev_flags is not None:
                    changes = bridge.diff(
                        b"\x00\x00" + prev_flags,
                        b"\x00\x00" + flags,
                    )
                    for off, old, new in changes:
                        print(f"  flag 0x{off:02X}: 0x{old:02X} → 0x{new:02X}",
                              flush=True)
                prev_flags = flags
                time.sleep(args.watch)
        except KeyboardInterrupt:
            print("\nStopped.")

    bridge.close()
    print("\nDone.")


if __name__ == "__main__":
    main()
