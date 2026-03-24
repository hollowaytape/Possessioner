import struct

def search_exe_for_flags(filepath):
    with open(filepath, "rb") as f:
        data = f.read()
    
    print(f"=== {filepath.split(chr(92))[-1]} (Size: {len(data)} bytes) ===\n")
    
    set_flags = []
    check_flags = []
    clear_flags = []
    
    for i in range(len(data) - 4):
        if data[i] == 0x02 and data[i+1] == 0xff and data[i+2] == 0x01:
            flag_id = data[i+3]
            flag_bit = data[i+4]
            set_flags.append((i, flag_id, flag_bit))
        
        if data[i] == 0x02 and data[i+1] == 0xff and data[i+2] == 0x02:
            flag_id = data[i+3]
            flag_bit = data[i+4]
            check_flags.append((i, flag_id, flag_bit))
    
    for i in range(len(data) - 5):
        if data[i] == 0x03 and data[i+1] == 0xff and data[i+2] == 0x01:
            payload = data[i+3:i+6]
            clear_flags.append((i, payload))
    
    if set_flags:
        print("SET_FLAG operations:")
        for offset, fid, bit in set_flags[:20]:
            print(f"  0x{offset:05x}: flag_id=0x{fid:02x}, bit={bit}")
        if len(set_flags) > 20:
            print(f"  ... and {len(set_flags) - 20} more")
    
    if check_flags:
        print("\nCHECK_FLAG operations:")
        for offset, fid, bit in check_flags[:20]:
            print(f"  0x{offset:05x}: flag_id=0x{fid:02x}, bit={bit}")
        if len(check_flags) > 20:
            print(f"  ... and {len(check_flags) - 20} more")
    
    if clear_flags:
        print("\nCLEAR_FLAG operations:")
        for offset, payload in clear_flags[:20]:
            print(f"  0x{offset:05x}: payload={' '.join(f'{b:02x}' for b in payload)}")
        if len(clear_flags) > 20:
            print(f"  ... and {len(clear_flags) - 20} more")
    
    print(f"\nSummary: SET={len(set_flags)}, CHECK={len(check_flags)}, CLEAR={len(clear_flags)}\n")
    return set_flags, check_flags, clear_flags

set_f, check_f, clear_f = search_exe_for_flags("D:\\Code\\roms\\Possessioner\\original\\POS.EXE")
