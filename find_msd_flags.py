def search_flags_in_ranges():
    from rominfo import MSD_POINTER_RANGES
    
    with open("D:\\Code\\roms\\Possessioner\\original\\POS.EXE", "rb") as f:
        exe_data = f.read()
    
    file_flags = {}
    
    for msd_file, ranges in MSD_POINTER_RANGES.items():
        file_flags[msd_file] = {
            "set": [],
            "check": [],
            "clear": []
        }
        
        for start, end in ranges:
            # Search for flag operations in this range
            for i in range(start, min(end + 1, len(exe_data) - 4)):
                # SET_FLAG: 0x02 ff 01
                if exe_data[i] == 0x02 and exe_data[i+1] == 0xff and exe_data[i+2] == 0x01:
                    flag_id = exe_data[i+3]
                    flag_bit = exe_data[i+4]
                    file_flags[msd_file]["set"].append((i, flag_id, flag_bit))
                
                # CHECK_FLAG: 0x02 ff 02
                if exe_data[i] == 0x02 and exe_data[i+1] == 0xff and exe_data[i+2] == 0x02:
                    flag_id = exe_data[i+3]
                    flag_bit = exe_data[i+4]
                    file_flags[msd_file]["check"].append((i, flag_id, flag_bit))
            
            # CLEAR_FLAG: 0x03 ff 01
            for i in range(start, min(end + 1, len(exe_data) - 5)):
                if exe_data[i] == 0x03 and exe_data[i+1] == 0xff and exe_data[i+2] == 0x01:
                    file_flags[msd_file]["clear"].append((i, exe_data[i+3], exe_data[i+4]))
    
    return file_flags

flags = search_flags_in_ranges()

print("=== FLAG OPERATIONS IN MSD POINTER RANGES ===\n")

for msd_file in ["POS1.MSD", "YUMI.MSD"]:
    print(f"\n{msd_file}:")
    print(f"  SET_FLAG operations: {len(flags[msd_file]['set'])}")
    for offset, flag_id, flag_bit in flags[msd_file]["set"]:
        print(f"    0x{offset:05x}: flag 0x{flag_id:02x}, bit {flag_bit}")
    
    print(f"  CHECK_FLAG operations: {len(flags[msd_file]['check'])}")
    for offset, flag_id, flag_bit in flags[msd_file]["check"]:
        print(f"    0x{offset:05x}: flag 0x{flag_id:02x}, bit {flag_bit}")
    
    print(f"  CLEAR_FLAG operations: {len(flags[msd_file]['clear'])}")
    for offset, flag_id, flag_bit in flags[msd_file]["clear"]:
        print(f"    0x{offset:05x}: flag 0x{flag_id:02x}, bit {flag_bit}")

