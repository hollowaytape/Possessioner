import struct

# From the analysis we found:
# SET_FLAG at YUMI context: pointer 0x27aa3
# Preceding operation at 0x27a94: 02 ff 01 18 05
# This sets flag_id=0x18, bit=5

# Let's find context around the pointer in POS.EXE

with open("D:\\Code\\roms\\Possessioner\\original\\POS.EXE", "rb") as f:
    data = f.read()
    
# Check context around 0x27aa3
ptr_loc = 0x27aa3
window_start = ptr_loc - 30
window_end = ptr_loc + 30

print("Context around pointer location 0x27aa3:")
for offset in range(window_start, window_end, 16):
    hex_str = " ".join(f"{data[offset + i]:02x}" if offset + i < len(data) else "  " for i in range(16))
    marker = ""
    if offset <= ptr_loc < offset + 16:
        idx = ptr_loc - offset
        marker = f" <-- pointer at +{idx}"
    print(f"0x{offset:05x}: {hex_str}{marker}")

print("\n\nByte-by-byte around the set_flag operation at 0x27a94:")
for i in range(0x27a94 - 10, 0x27a94 + 20):
    if i >= 0 and i < len(data):
        print(f"0x{i:05x}: 0x{data[i]:02x}")
