import json
with open("D:\\Code\\roms\\Possessioner\\pos1_analysis.json", "r") as f:
    data = json.load(f)
    records = data.get("records", [])
    
    print("=== POS1.MSD FLAG OPERATIONS ===\n")
    
    has_flags = False
    for r in records:
        labels = r.get("labels", [])
        if any("flag" in label for label in labels):
            has_flags = True
            print(json.dumps(r, indent=2))
    
    if not has_flags:
        print("No flag operations found in POS1.MSD")
        print("\nLet me check branchy-context records:")
        count = 0
        for r in records:
            labels = r.get("labels", [])
            if "branchy-context" in labels and count < 5:
                print(f"\nOffset: {r.get('offset')}, Command: {r.get('command')}")
                print(f"Labels: {labels}")
                count += 1
