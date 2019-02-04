import os
from collections import OrderedDict
# Need the third-party regex library, which supports overlapping matches
import regex as re
from romtools.dump import BorlandPointer, DumpExcel, PointerExcel
from romtools.disk import Gamefile

from rominfo import POINTER_CONSTANT, POINTER_TABLES, POINTER_TABLE_SEPARATOR, CONTROL_CODES, POINTER_DISAMBIGUATION,  FILE_BLOCKS, DUMP_XLS_PATH, MSD_POINTER_RANGES

FILES_WITH_POINTERS = POINTER_CONSTANT
#FILES_WITH_POINTERS = ['POS1.MSD']

# POINTER_CONSTANT is the line where "Borland Compiler" appears, rounded down to the nearest 0x10.

# 8b03 = 03 10
# 8b0c = 0c 10
# 8b15
# 8b1c

# constant = 0x7b00

# battle things:
# cfb8 = b8 54 
    # found at c227, be b8 54 e8 fe
# cfcf = cf 54
    # found at c4a6, be cf 54 e8 7f

Dump = DumpExcel(DUMP_XLS_PATH)

# Removing the 9a at the end of this one. Didn't show up in some pointers.
pointer_regex = r'\\xbe\\x([0-f][0-f])\\x([0-f][0-f])\\xe8'
pointer_regex_2 = r'\\xbe\\x([0-f][0-f])\\x([0-f][0-f])\\xbf'  # that one combat pointer
# msd_pointer_regex = r'\\xff\\x02\\x([0-f][0-f])\\x([0-f][0-f])'
msd_pointer_regex = r'\\x02\\x([0-f][0-f])\\x([0-f][0-f])'
msd_pointer_regex_2 = r'\\xbe\\x([0-f][0-f])\\x([0-f][0-f])\\xb9'
table_pointer_regex = r'\\x([0-f][0-f])\\x([0-f][0-f])sep'


def capture_pointers_from_function(hx, regex): 
    return re.compile(regex).finditer(hx, overlapped=True)


def location_from_pointer(pointer, constant):
    return '0x' + str(format((unpack(pointer[0], pointer[1]) + constant), '05x'))


def unpack(s, t=None):
    if t is None:
        t = str(s)[2:]
        s = str(s)[0:2]
    #print(s, t)
    s = int(s, 16)
    t = int(t, 16)
    value = (t * 0x100) + s
    return value


pointer_count = 0

try:
    os.remove('PSSR_pointer_dump.xlsx')
except FileNotFoundError:
    pass

PtrXl = PointerExcel('PSSR_pointer_dump.xlsx')

for gamefile in FILES_WITH_POINTERS:
    print(gamefile)
    pointer_locations = OrderedDict()
    gamefile_path = os.path.join('original', gamefile)

    # MSD files have their pointers in POS.EXE.
    if gamefile.endswith('.MSD'):
        GF = Gamefile('original\\POS.EXE', pointer_constant=POINTER_CONSTANT[gamefile])
        GF2 = Gamefile(gamefile_path, pointer_constant=POINTER_CONSTANT[gamefile])

        gamefile_path = 'original\\POS.EXE'
    else:
        GF = Gamefile(gamefile_path, pointer_constant=POINTER_CONSTANT[gamefile])
        GF2 = Gamefile(gamefile_path, pointer_constant=POINTER_CONSTANT[gamefile])

    with open(gamefile_path, 'rb') as f:
        print(gamefile_path)
        bs = f.read()
        target_areas = FILE_BLOCKS[gamefile]

        if gamefile.endswith('.MSD'):
            target_areas = []
            for t in Dump.get_translations(gamefile, include_blank=True):
                if t.command is not None:
                    #target_areas.append((t.location - 8, t.location - 7))
                    if t.location > 0x00:
                        print("Target: " + hex(t.location))
                        target_areas.append((t.location, t.location))


        # target_area = (GF.pointer_constant, len(bs))
        #print(hex(target_area[0]), hex(target_area[1]))

        only_hex = u""
        for c in bs:
            only_hex += u'\\x%02x' % c

        #print(only_hex)

        # Plain tables (no separators)
        try:
            tables = POINTER_TABLES[gamefile]
            for t in tables:
                start, stop = t
                cursor = start
                while cursor <= stop:
                    pointer_location = cursor
                    pointer_location = '0x%05x' % pointer_location
                    text_location = (GF.filestring[cursor+1] * 0x100) + GF.filestring[cursor] + GF.pointer_constant
                    #print(text_location)
                    cursor += 2

                    if all([not t[0] <= text_location<= t[1] for t in target_areas]):
                        #print("Skipping")
                        continue

                    all_locations = [int(pointer_location, 16),]

                    #print(pointer_locations)

                    if (GF, text_location) in pointer_locations.keys():
                        all_locations = pointer_locations[(GF, text_location)]
                        all_locations.append(int(pointer_location, 16))

                    pointer_locations[(GF, text_location)] = all_locations
                    #print(pointer_locations[(GF, text_location)])

        except KeyError:
            # When POINTER_TABLE_SEPARATOR[gamefile] is None, no pointer
            # tables. skip that regex
            pass

        # Separated tables
        try:
            separator = POINTER_TABLE_SEPARATOR[gamefile]
            table_regex = table_pointer_regex.replace('sep', separator)
            #print(table_regex)
        except KeyError:
            table_regex = None

        if gamefile.endswith('MSD'):
            msd_regex = msd_pointer_regex
            msd_regex_2 = msd_pointer_regex_2
        else:
            msd_regex = None
            msd_regex_2 = None


        #print(pointer_regex)
        for regex in (pointer_regex, pointer_regex_2, msd_regex, msd_regex_2, table_regex):
            if regex is None:
                continue
            #print(regex)
            pointers = capture_pointers_from_function(only_hex, regex)

            for p in pointers:
                #print(p)
                # Different offsets for each regex?
                if regex == pointer_regex:
                    pointer_location = p.start()//4 + 1
                elif regex == pointer_regex_2:
                    pointer_location = p.start()//4 + 1
                elif regex == msd_pointer_regex:
                    pointer_location = p.start()//4 + 1
                elif regex == msd_pointer_regex_2:
                    pointer_location = p.start()//4 + 1
                elif regex == table_regex:
                    pointer_location = p.start()//4
                else:
                    raise Exception

                pointer_location = '0x%05x' % pointer_location

                text_location = int(location_from_pointer((p.group(1), p.group(2)), GF.pointer_constant), 16)

                if all([not t[0] <= text_location<= t[1] for t in target_areas]):
                    #print("Skipping")
                    continue

                all_locations = [int(pointer_location, 16),]

                #print(pointer_locations)

                if (GF2, text_location) in pointer_locations.keys():
                    all_locations = pointer_locations[(GF2, text_location)]
                    all_locations.append(int(pointer_location, 16))

                pointer_locations[(GF2, text_location)] = all_locations


    # Setup the worksheet for this file
    worksheet = PtrXl.add_worksheet(GF2.filename)

    row = 1

    try:
        itemlist = sorted((pointer_locations.items()))
    except:
        itemlist = pointer_locations.items()

    for (gamefile, text_location), pointer_locations in itemlist:
        if gamefile.filename == 'POSM.EXE':
            separator = b'\x00'
        else:
            separator = b'\x0d'
        obj = BorlandPointer(gamefile, pointer_locations, text_location, separator=separator)
        #print(hex(text_location))
        #print(pointer_locations)

        # Restrict pointer locations to a particular area when there are dupes
        if len(pointer_locations) > 1:
            if gamefile.filename in MSD_POINTER_RANGES:
                better_pointer_locations = []
                #print("Text is at", hex(text_location))
                for pointer_loc in pointer_locations:
                    if any([s[0] <= pointer_loc <= s[1] for s in MSD_POINTER_RANGES[gamefile.filename]]):
                        print(hex(text_location), hex(pointer_loc), "is good")
                        better_pointer_locations.append(pointer_loc)
                    else:
                        print(hex(text_location), hex(pointer_loc), "is bad")
                        pass
                if better_pointer_locations != []:
                    pointer_locations = better_pointer_locations

        # Use pointer disambiguation to remove pointers with hundreds of locs
        for (dis_file, dis_text_loc, dis_pointer_loc) in POINTER_DISAMBIGUATION:
            if dis_file == gamefile.filename and dis_text_loc == text_location:
                print("Using pointer disambiguation for %s, %s" % (dis_file, dis_text_loc))
                pointer_locations = [dis_pointer_loc,]


        for pointer_loc in pointer_locations:
            worksheet.write(row, 0, '0x' + hex(text_location).lstrip('0x').zfill(5))
            worksheet.write(row, 1, '0x' + hex(pointer_loc).lstrip('0x').zfill(5))
            try:
                worksheet.write(row, 2, obj.text(CONTROL_CODES))
            except:
                worksheet.write(row, 2, u'')
            row += 1

PtrXl.close()