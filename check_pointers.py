"""
    This script checks for text locations that appear to have multiple pointers pointing to them.
    Sometimes this is ok, like when arriving at a location at different points in the game has the same text.
    Other times it means there's a bug.
"""

import os

from rominfo import FILES, FILE_BLOCKS, ORIGINAL_ROM_PATH, TARGET_ROM_PATH, DUMP_XLS_PATH, POINTER_DUMP_XLS_PATH, inverse_CONCISE_CTRL, inverse_CTRL
from romtools.disk import Disk, Gamefile, Block
from romtools.dump import DumpExcel, PointerExcel

Dump = DumpExcel(DUMP_XLS_PATH)
PtrDump = PointerExcel(POINTER_DUMP_XLS_PATH)
OriginalPssr = Disk(ORIGINAL_ROM_PATH, dump_excel=Dump, pointer_excel = PtrDump)
TargetPssr = Disk(TARGET_ROM_PATH)

#FILES = ['HONHOA.MSD', 'DOCTOR.MSD', 'MINS.MSD', 'P_GE.MSD', 'MAI.MSD',]

text_offsets = {}
pointer_offsets = {}
problem_count = 0

print("Text locations with an assigned command but no pointers:")
for filename in [f for f in FILES if f.endswith('.MSD')]:
    GF = Gamefile('original/%s' % filename, disk=OriginalPssr, dest_disk=TargetPssr)
    # important_locations: text locations that have a command defined for them
    important_locations = []
    for t in Dump.get_translations(filename, include_blank=True):
        if t.command is not None and t.command != '?' and 'unused' not in t.command:
            if t.location > 0x0:
                important_locations.append(t.location)
            try:
                #print(hex(t.location), t.command)
                pass
            except UnicodeEncodeError:
                # print("something else")
                pass

    pointers = PtrDump.get_pointers(GF, pointer_sheet_name=filename)
    for p in pointers:
        if p in important_locations:
            important_locations.remove(p)

        for loc in pointers[p]:
            if (filename, loc.text_location) in text_offsets:
                text_offsets[(filename, loc.text_location)].append(loc.location)
            else:
                text_offsets[(filename, loc.text_location)] = [loc.location,]

            if loc.location in pointer_offsets:
                pointer_offsets[loc.location].append((filename, loc.text_location))
            else:
                pointer_offsets[loc.location] = [(filename, loc.text_location),]

            #if (filename, loc.location) in pointer_offsets:
            #    pointer_offsets[loc.text_location].append((filename, loc.text_location))
            #else:
            #    pointer_offsets[loc.text_location] = [(filename, loc.text_location),]

    # These are the identified important_locations that do not have any pointer for them yet
    if len(important_locations) > 0:
        print(filename, ":")
        for t in important_locations:
            print(hex(t))
            problem_count += 1

print("")
print("Text locations with multiple pointer locations:")
for p in text_offsets:
    #print(p, text_offsets[p])
    if len(text_offsets[p]) > 1:
        print(p[0], hex(p[1]), [hex(x) for x in text_offsets[p]])
        problem_count += 1

print("")
print("Pointer locations referenced in multiple files:")
for p in pointer_offsets:
    if len(pointer_offsets[p]) > 1:
        print(hex(p), [x[0] + " " + hex(x[1]) for x in pointer_offsets[p]])
        problem_count += 1
        # TODO: can we predict which one is correct based on that file's pointer locations?

print("")
print(problem_count, "potential problems detected")
