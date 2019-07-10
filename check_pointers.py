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

for filename in [f for f in FILES if f.endswith('.MSD')]:
    GF = Gamefile('original/%s' % filename, disk=OriginalPssr, dest_disk=TargetPssr)
    important_locations = []
    for t in Dump.get_translations(filename, include_blank=True):
        if t.command is not None and t.command != '?':
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

        #if p in pointer_offsets:
        #    pointer_offsets[p].append(pointers[p])
        #else:
        #    pointer_offsets[p] = [pointers[p],]
        for loc in pointers[p]:
            if (filename, loc.text_location) in text_offsets:
                text_offsets[(filename, loc.text_location)].append(loc.location)
            else:
                text_offsets[(filename, loc.text_location)] = [loc.location,]

            if (filename, loc.location) in pointer_offsets:
                pointer_offsets[loc.text_location].append((filename, loc.text_location))
            else:
                pointer_offsets[loc.text_location] = [(filename, loc.text_location),]


    if len(important_locations) > 0:
        print(filename, ":")
        for t in important_locations:
            print(hex(t))

for p in text_offsets:
    #print(p, text_offsets[p])
    if len(text_offsets[p]) > 1:
            print(p[0], hex(p[1]), text_offsets[p])