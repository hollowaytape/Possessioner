"""
    Possessioner reinserter.
    Based on the CRW reinserter base via Pssr98-II.
"""

import os

from rominfo import FILE_BLOCKS, FILES, FILES_TO_REINSERT, ORIGINAL_ROM_PATH, TARGET_ROM_PATH, DUMP_XLS_PATH, POINTER_DUMP_XLS_PATH, inverse_CONCISE_CTRL, inverse_CTRL
from rominfo import ENEMY_NAME_LOCATIONS
from romtools.disk import Disk, Gamefile, Block
from romtools.dump import DumpExcel, PointerExcel

Dump = DumpExcel(DUMP_XLS_PATH)
PtrDump = PointerExcel(POINTER_DUMP_XLS_PATH)
OriginalPssr = Disk(ORIGINAL_ROM_PATH, dump_excel=Dump, pointer_excel = PtrDump)
TargetPssr = Disk(TARGET_ROM_PATH)

MAPPING_MODE = True
CHEATS_ON = True

def run_reinsert():
    # Calculate total number of strings in the dump
    total_strings = 0
    total_translations = 0
    for filename in FILES:
        path_in_disk = "PSSR\\"
        gamefile_path = os.path.join('original', filename)
        #print(filename)
        gamefile = Gamefile(gamefile_path, disk=OriginalPssr, dest_disk=TargetPssr)
        if not filename.endswith(".SEL"):
            string_count = len(Dump.get_translations(gamefile, include_blank=True))
            total_strings += string_count

    # Start reinserting things
    for filename in FILES:
        path_in_disk = "PSSR\\"

        if filename.endswith(".SEL") or filename.endswith(".CGX"):
            #print("Static image file - reinsert the one from /patched")
            gamefile_path = os.path.join('patched', filename)
            gamefile = Gamefile(gamefile_path, dest_disk=TargetPssr)
            gamefile.write(path_in_disk=path_in_disk)
            continue

        else:
            gamefile_path = os.path.join('original', filename)
            gamefile = Gamefile(gamefile_path, disk=OriginalPssr, dest_disk=TargetPssr)

            string_count = len(Dump.get_translations(gamefile, include_blank=True))
            #print(string_count)
            translation_count = 0

        # .MSD files have their pointers in 
        if filename.endswith('.MSD'):
            pointer_gamefile = Gamefile('patched\\POS.EXE', disk=OriginalPssr, 
                                        dest_disk=TargetPssr, pointer_sheet_name=filename)
        else:
            pointer_gamefile = gamefile

        if filename == 'POS.EXE':
            # Ascii text hack for nametags, see notes.txt
            gamefile.edit(0xa0ba, b'\x74\x15\x30\xe4\x90\x90\x90\x90\x90\x90\x90\x90')
            gamefile.edit(0xa0cd, b'\x90\x90')

            # Reassign tile indices for in-battle nametag images
            # a = space
            # Alisa
            gamefile.edit(0xd81a, b'aabcde')

            # Honghua
            gamefile.edit(0xd821, b'anopqrst')

            # Meryl
            gamefile.edit(0xd82a, b'aafghi')

            # Nedra
            gamefile.edit(0xd831, b'ajgklm')

            # Increase text speed
            gamefile.edit(0xa3bf, b'\xa8\x04')

            if CHEATS_ON:
                # Set all enemy HP to 0, so they die in one hit
                for loc in ENEMY_NAME_LOCATIONS:
                    gamefile.edit(loc - 9, b'\x00')   # HP = 0
                    gamefile.edit(loc - 10, b'\x80')  # State = dead?

                # Instant text display
                gamefile.edit(0xa3bf, b'\xa8\x03')

        elif filename == 'POSM.EXE':
            # Redirect font table reference
            gamefile.edit(0x28d1, b'\xc0\x25')

            # Make ascii text go to fullwidth routine
            gamefile.edit(0x174f, b'\x02')

            # Nop out an "inc si"
            gamefile.edit(0x17aa, b'\x90') 

            # Top byte is always 82
            gamefile.edit(0x17ab, b'\xb4\x82')

            # Nop out mov al, [si]
            gamefile.edit(0x17ad, b'\x90\x90')

            # Mysterious double-inc [si]
            gamefile.edit(0x8b19, b'\x90')

            # Extremely inelegant punctuation fix
            gamefile.edit(0x28d7, b'\xb6\x29')

            # Fix "@  QUEEN  SOFT"
            gamefile.edit(0xb450, b' ')
            gamefile.edit(0xb45f, b' ')

        for block in FILE_BLOCKS[filename]:
            block = Block(gamefile, block)
            #print(block)
            previous_text_offset = block.start
            diff = 0
            for i, t in enumerate(Dump.get_translations(block, include_blank=True)):
                print(t.english)
                loc_in_block = t.location - block.start + diff

                for ccc in inverse_CONCISE_CTRL:
                    t.jp_bytestring = t.jp_bytestring.replace(ccc, inverse_CONCISE_CTRL[ccc])
                    t.en_bytestring = t.en_bytestring.replace(ccc, inverse_CONCISE_CTRL[ccc])
                    if t.prefix is not None:
                        t.prefix = t.prefix.replace(ccc, inverse_CONCISE_CTRL[ccc])

                for cc in inverse_CTRL:
                    t.jp_bytestring = t.jp_bytestring.replace(cc, inverse_CTRL[cc])
                    t.en_bytestring = t.en_bytestring.replace(cc, inverse_CTRL[cc])
                    if t.prefix is not None:
                        t.prefix = t.prefix.replace(cc, inverse_CTRL[cc])

                this_diff = len(t.en_bytestring) - len(t.jp_bytestring)

                if t.english == b'' or t.en_bytestring == t.prefix or t.english == t.japanese:
                    if filename.endswith('MSD') and MAPPING_MODE:
                        #print(this_diff)
                        if this_diff >= -8:
                            id_string = b'%i' % (i+2)
                        else:
                            id_string = b'%b-%i' % (filename[:4].encode('ascii'), (i+2))
                        t.en_bytestring += id_string
                        #print(t.en_bytestring)
                        while len(t.en_bytestring) < len(t.jp_bytestring):
                            t.en_bytestring += b' '
                        #if len(id_string) < len(t.jp_bytestring):
                        #    print(id_string)
                        #    t.en_bytestring = id_string + t.jp_bytestring[len(id_string):]
                        this_diff = len(t.en_bytestring) - len(t.jp_bytestring)
                        #print(t.en_bytestring)
                        assert this_diff == 0

                    else:
                        # Still count things if they're just internal system things we don't want to change
                        if t.english == t.japanese:
                            translation_count += 1
                            total_translations += 1
                        #print(hex(t.location), t.english, "Blank string")
                        this_diff = 0
                        #print("Diff is", diff)

                        pointer_gamefile.edit_pointers_in_range((previous_text_offset, t.location), diff)
                        previous_text_offset = t.location
                        continue
                else:
                    #if t.english:
                    #    print(t.english)
                    translation_count += 1
                    total_translations += 1

                try:
                    i = block.blockstring.index(t.jp_bytestring)
                except ValueError:
                    print(t, "wasn't found in the string. Skipping for now")
                    continue
                j = block.blockstring.count(t.jp_bytestring)

                # Does this do anything????
                index = 0
                while index < len(block.blockstring):
                    index = block.blockstring.find(t.jp_bytestring, index)
                    #print("Found it at", hex(index))
                    if index == -1:
                        break
                    index += len(t.jp_bytestring) # +2 because len('ll') == 2

                assert loc_in_block == i, (t, hex(loc_in_block), hex(i))
                #while loc_in_block != i:

                #print(t.jp_bytestring, t.en_bytestring)
                block.blockstring = block.blockstring.replace(t.jp_bytestring, t.en_bytestring, 1)
                #print(block.blockstring)


                pointer_gamefile.edit_pointers_in_range((previous_text_offset, t.location), diff)

                # Adjust line-counter bytes
                if b'\r\xf3' in t.en_bytestring and filename.endswith(".MSD"):
                    #print(t.en_bytestring)
                    inc = t.en_bytestring.count(b'\r\xf3')
                    this_window_pointers = []

                    # Look back through the pointers until we find the most recent one
                    window_cursor = 0
                    while this_window_pointers == [] and t.location - window_cursor > 0:
                        window_cursor += 1
                        this_window_pointers = [p for p in pointer_gamefile.pointers if t.location - window_cursor <= p <= t.location]
                    for p in this_window_pointers:
                        for ptr in pointer_gamefile.pointers[p]:
                            line_count_location = ptr.location + 2

                            # Don't try to increment the thing that loads a new image (?)
                            if pointer_gamefile.filestring[line_count_location] == 0xb9:
                                #print("Bad idea to increment this... let's try the next byte instead")
                                line_count_location += 1

                            #print(hex(line_count_location), "being incremented by", inc)
                            pointer_gamefile.edit(line_count_location, inc, diff=True, window_increment=True)

                previous_text_offset = t.location


                diff += this_diff
                #print("Diff is", diff)

            if not filename.endswith('.MSD'):
                block_diff = len(block.blockstring) - len(block.original_blockstring)
                if block_diff < 0:
                    block.blockstring += (-1)*block_diff*b'\x00'
                block_diff = len(block.blockstring) - len(block.original_blockstring)
                #print(block)
                assert block_diff == 0, block_diff

            block.incorporate()

        percentage = round((translation_count / string_count) * 100, 1)
        print(gamefile, ": %s%% (%s / %s)" % (percentage, translation_count, string_count))
        print()

        gamefile.write(path_in_disk=path_in_disk)
        pointer_gamefile.write(path_in_disk=path_in_disk)

    percentage = round((total_translations / total_strings) * 100, 1)
    print("Possessioner: %s%% (%s / %s)" % (percentage, total_translations, total_strings))

if __name__ == '__main__':
    run_reinsert()