"""
    Possessioner reinserter.
    Based on the CRW reinserter base via Pssr98-II.
"""

import os

from rominfo import FILE_BLOCKS, ORIGINAL_ROM_PATH, TARGET_ROM_PATH, DUMP_XLS_PATH, POINTER_DUMP_XLS_PATH
from romtools.disk import Disk, Gamefile, Block
from romtools.dump import DumpExcel, PointerExcel

Dump = DumpExcel(DUMP_XLS_PATH)
PtrDump = PointerExcel(POINTER_DUMP_XLS_PATH)
OriginalPssr = Disk(ORIGINAL_ROM_PATH, dump_excel=Dump, pointer_excel = PtrDump)
TargetPssr = Disk(TARGET_ROM_PATH)

FILES_TO_REINSERT = ['POS.EXE', 'POSM.EXE', 'POS1.MSD']

for filename in FILES_TO_REINSERT:
    path_in_disk = "PSSR\\"
    gamefile_path = os.path.join('original', filename)

    gamefile = Gamefile(gamefile_path, disk=OriginalPssr, dest_disk=TargetPssr)

    if filename == 'POS.EXE':
        # Ascii text hack for nametags, see notes.txt
        gamefile.edit(0xa0ba, b'\x74\x15\x30\xe4\x90\x90\x90\x90\x90\x90\x90\x90')
        gamefile.edit(0xa0cd, b'\x90\x90')


    for block in FILE_BLOCKS[filename]:
        block = Block(gamefile, block)
        print(block)
        previous_text_offset = block.start
        diff = 0
        for t in Dump.get_translations(block, include_blank=True):
            #print(t.english)
            loc_in_block = t.location - block.start + diff

            this_diff = len(t.en_bytestring) - len(t.jp_bytestring)

            # Taking off training wheels
            #if this_diff > 0:
            #    print(t.en_bytestring, t.jp_bytestring)
            #    raise Exception
            #while this_diff < 0 and t.en_bytestring != b'':
            #    t.en_bytestring += b' '
            #    this_diff = len(t.en_bytestring) - len(t.jp_bytestring)

            if t.en_bytestring != b'':
                print(t.en_bytestring)


            """
            if filename.endswith('.DAT'):
                print(t.en_bytestring)
                print(t.jp_bytestring)
                print("Diff is ", this_diff)
                # Need to pad with 00's
                while this_diff < 0:
                    t.en_bytestring += b'\x00'
                    this_diff += 1
                while this_diff > 0:
                    t.jp_bytestring += b'\x00'
                    this_diff -= 1

                assert len(t.en_bytestring) - len(t.jp_bytestring) == 0
            """

            if t.english == b'' or t.english == t.japanese:
                #print(hex(t.location), t.english, "Blank string")
                this_diff = 0
                #print("Diff is", diff)

                gamefile.edit_pointers_in_range((previous_text_offset, t.location), diff)
                previous_text_offset = t.location
                continue

            try:
                i = block.blockstring.index(t.jp_bytestring)
            except ValueError:
                print(t, "wasn't found in the string. Skipping for now")
                continue
            j = block.blockstring.count(t.jp_bytestring)

            index = 0
            while index < len(block.blockstring):
                index = block.blockstring.find(t.jp_bytestring, index)
                if index == -1:
                    break
                index += len(t.jp_bytestring) # +2 because len('ll') == 2

            assert loc_in_block == i, (t, hex(loc_in_block), hex(i))

            block.blockstring = block.blockstring.replace(t.jp_bytestring, t.en_bytestring, 1)

            gamefile.edit_pointers_in_range((previous_text_offset, t.location), diff)
            previous_text_offset = t.location

            diff += this_diff
            print("Diff is", diff)

        block_diff = len(block.blockstring) - len(block.original_blockstring)
        if block_diff < 0:
            block.blockstring += (-1)*block_diff*b'\x00'
        block_diff = len(block.blockstring) - len(block.original_blockstring)
        assert block_diff == 0, block_diff

        block.incorporate()

    gamefile.write(path_in_disk=path_in_disk)
