import os
from collections import OrderedDict
# Need the third-party regex library, which supports overlapping matches
import regex as re
from romtools.dump import BorlandPointer, DumpExcel, PointerExcel
from romtools.disk import Gamefile

from rominfo import POINTER_CONSTANT, POINTER_TABLES, POINTER_TABLE_SEPARATOR
from rominfo import EXTRA_POINTERS,  CONTROL_CODES, POINTER_DISAMBIGUATION, SKIP_TARGET_AREAS, ARRIVAL_POINTERS
from rominfo import FILE_BLOCKS, DUMP_XLS_PATH, MSD_POINTER_RANGES, FILES_TO_REINSERT, FILES

Dump = DumpExcel(DUMP_XLS_PATH)

# Removing the 9a at the end of this one. Didn't show up in some pointers.
pointer_regex = r'\\xbe\\x([0-f][0-f])\\x([0-f][0-f])\\xe8'
pointer_regex_2 = r'\\xbe\\x([0-f][0-f])\\x([0-f][0-f])\\xbf'  # that one combat pointer
# msd_pointer_regex = r'\\xff\\x02\\x([0-f][0-f])\\x([0-f][0-f])'
# Prefixes are ff 02 and 00 02 always?

msd_pointer_regex = r'\\x02\\x([0-f][0-f])\\x([0-f][0-f])\\x([0-f][0-f])'
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

final_target_areas = {}

for gamefile in FILES_TO_REINSERT:
    print("Getting pointers for", gamefile)
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

        # Missing ptr const here

    with open(gamefile_path, 'rb') as f:
        bs = f.read()
        target_areas = FILE_BLOCKS[gamefile]

        if gamefile.endswith('.MSD'):
            target_areas = []
            for t in Dump.get_translations(gamefile, include_blank=True):
                # IMPORTANT!Disabling this for now

                #if t.command is not None:

                # Disabling this too. It can tell you which of the next few strings to skip
                #if t.location > 0x00:
                #print("Target: " + hex(t.location))
                target_areas.append((t.location, t.location))
            if gamefile in SKIP_TARGET_AREAS:
                for sta in SKIP_TARGET_AREAS[gamefile]:
                    target_areas.remove((sta, sta))
                    assert sta not in target_areas


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
                    assert (GF, text_location) in pointer_locations
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

                text_location = int(location_from_pointer((p.group(1), p.group(2)), GF.pointer_constant), 16)

                if all([not t[0] <= text_location<= t[1] for t in target_areas]):
                    #for t in target_areas:
                    #    print(hex(t[0]), hex(t[1]))
                    #print("Skipping")
                    continue

                if (gamefile, text_location, None) in POINTER_DISAMBIGUATION:
                    #print("Really bad pointer, skipping that one")
                    continue

                throwaway = False
                if regex == msd_pointer_regex and gamefile in MSD_POINTER_RANGES:
                    byte_before = bs[p.start()//4 - 1]
                    # This started out as a reasonable list. Oops
                    if byte_before in (0x00, 0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07, 0x08, 
                                       0x09, 0x0a, 0x0b, 0x0c, 0x0d, 0x0e, 0x0f, 0x10, 0x11, 0x12, 0x13, 0x14, 0x15, 0x16, 0x17, 
                                       0x18, 0x19, 0x1a, 0x1b, 0x1c, 0x1d, 0x1e, 0x1f, 0x20, 0x21, 0x22, 0x23, 0x24, 0x2b, 0x39, 0xff):
                        #print(pointer_location)
                        #print("length: " + int(p.group(3), 16))

                        ranges = MSD_POINTER_RANGES[gamefile]

                        # Don't do this removal if there are multiple pointers to one text location.
                        # That would skip areas unnecessarily
                        if (GF2, text_location) not in pointer_locations.keys():
                            if any([r[0] <= pointer_location <= r[1] for r in ranges]):
                                pointer_lines = int(p.group(3), 16)
                                #print(hex(pointer_location), hex(text_location), pointer_lines)
                                i = target_areas.index((text_location, text_location))
                                pointer_lines -= 1
                                #print(gamefile, hex(byte_before))
                                # Remove the next N target areas
                                # TODO: Disabling this
                                #while pointer_lines:
                                #    print("No longer looking for " + hex(target_areas.pop(i+1)[0]))
                                #    pointer_lines -= 1
                            else:
                                throwaway = True
                        else:
                            # That's fine, just don't do pointer_line removals
                            pass
                    else:
                        throwaway = True

                if throwaway:
                    continue

                pointer_location = '0x%05x' % pointer_location

                all_locations = [int(pointer_location, 16),]

                #print(pointer_locations)

                if (GF2, text_location) in pointer_locations.keys():
                    all_locations = pointer_locations[(GF2, text_location)]
                    all_locations.append(int(pointer_location, 16))

                pointer_locations[(GF2, text_location)] = all_locations

        final_target_areas[gamefile] = target_areas

    # Add those pesky manual ones that don't get found
    #print(final_target_areas.keys())
    print(gamefile)
    #if gamefile in ARRIVAL_POINTERS:
    #    for (text_loc, pointer_loc) in ARRIVAL_POINTERS[gamefile]:
    #        print("It's an arrival pointer", text_loc, pointer_loc)
    #        pointer_locations[(GF2, text_loc)] = [pointer_loc,]
    #        final_target_areas[gamefile].append((text_loc, text_loc))
    #        print(pointer_locations[(GF2, text_loc)])

    if gamefile in EXTRA_POINTERS:
        print("It's an extra pointer")
        # TODO: What is final_target_areas for??
        #gamefile_path = os.path.join('original', gf)
        #GF = Gamefile(gamefile_path, pointer_constant=POINTER_CONSTANT[gf])
        for (text_loc, pointer_loc) in EXTRA_POINTERS[gamefile]:
            pointer_locations[(GF2, text_loc)] = [pointer_loc,]
            final_target_areas[gamefile].append((text_loc, text_loc))
            print(text_loc, pointer_loc)
            print(pointer_locations[(GF2, text_loc)])

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
        if text_location == 0x0:
            continue

        #    # Definitely don't use these. They were useful for pointer_lines calculation,
        #    # but they have served their purpose
        #    continue
        #print(gamefile)
        if gamefile.filename.endswith('.MSD'):
            if not any([text_location == ta[0] for ta in final_target_areas[gamefile.filename]]):
                print(hex(text_location), "wasn't on the targets list")
                continue

        """
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
        """
        if gamefile.filename in MSD_POINTER_RANGES:
            better_pointer_locations = []
            for pointer_loc in pointer_locations:
                if any([s[0] <= pointer_loc <= s[1] for s in MSD_POINTER_RANGES[gamefile.filename]]):
                    #print(hex(text_location), hex(pointer_loc), "is good")
                    better_pointer_locations.append(pointer_loc)
                else:
                    # One more chance...?
                    if Gamefile('original/POS.EXE').filestring[pointer_loc-1] == 0xbe:
                        better_pointer_locations.append(pointer_loc)
                    else:
                        print(hex(text_location), hex(pointer_loc), "is bad")
            pointer_locations = better_pointer_locations
            if pointer_locations == []:
                #print("Oops, no good pointers for", hex(text_location))
                continue


        # TODO: Could I do something like throw out all MSD pointers below 0x10000?
        # Might work...

        # Use pointer disambiguation to remove pointers with hundreds of locs
        throwaway = False
        for (dis_file, dis_text_loc, dis_pointer_loc) in POINTER_DISAMBIGUATION:
            if dis_file == gamefile.filename and dis_text_loc == text_location:
                #print("Using pointer disambiguation for %s, %s" % (dis_file, dis_text_loc))
                if dis_pointer_loc is None:
                    throwaway = True
                pointer_locations = [dis_pointer_loc,]

        if throwaway:
            continue

        for pointer_loc in pointer_locations:
            worksheet.write(row, 0, '0x' + hex(text_location).lstrip('0x').zfill(5))
            worksheet.write(row, 1, '0x' + hex(pointer_loc).lstrip('0x').zfill(5))
            try:
                worksheet.write(row, 2, obj.text(CONTROL_CODES))
            except:
                worksheet.write(row, 2, u'')
            row += 1
    try:
        if gamefile.filename in ARRIVAL_POINTERS:
            print(gamefile.filename, "has an arrival pointer")
            for pt in ARRIVAL_POINTERS[gamefile.filename]:
                print(pt)
                text_location, pointer_loc = pt
                worksheet.write(row, 0, '0x' + hex(text_location).lstrip('0x').zfill(5))
                worksheet.write(row, 1, '0x' + hex(pointer_loc).lstrip('0x').zfill(5))
                worksheet.write(row, 2, u'Arrival text')
                row += 1
    except AttributeError:
        pass

PtrXl.close()