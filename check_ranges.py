# Check the raw ranges from rominfo
from rominfo import MSD_POINTER_RANGES

print("=== MSD_POINTER_RANGES from rominfo ===\n")
for file, ranges in MSD_POINTER_RANGES.items():
    print(f"{file}:")
    for start, end in ranges:
        print(f"  0x{start:05x} - 0x{end:05x}")
    print()
