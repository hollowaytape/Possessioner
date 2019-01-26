"""
    Possessioner reinserter.
    Based on the CRW reinserter base via Pssr98-II.
"""

import os

from rominfo import FILE_BLOCKS, ORIGINAL_ROM_PATH, TARGET_ROM_PATH, DUMP_XLS_PATH, POINTER_DUMP_XLS_PATH, inverse_CTRL
from romtools.disk import Disk, Gamefile, Block
from romtools.dump import DumpExcel, PointerExcel

Dump = DumpExcel(DUMP_XLS_PATH)
PtrDump = PointerExcel(POINTER_DUMP_XLS_PATH)
OriginalPssr = Disk(ORIGINAL_ROM_PATH, dump_excel=Dump, pointer_excel = PtrDump)
TargetPssr = Disk(TARGET_ROM_PATH)

FILES_TO_REINSERT = ['POS.EXE', 'POSM.EXE',]

for filename in FILES_TO_REINSERT:
    path_in_disk = "PSSR\\"
    gamefile_path = os.path.join('original', filename)

    gamefile = Gamefile(gamefile_path, disk=OriginalPssr, dest_disk=TargetPssr)

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

        # Reassign tile numbers for in-battle nametag images
        # a = space
        # Alisa
        gamefile.edit(0xd81a, b'aabcde')

        # Honghua
        gamefile.edit(0xd821, b'anopqrst')

        # Meryl
        gamefile.edit(0xd82a, b'aafghi')

        # Nedra?
        gamefile.edit(0xd831, b'ajgklm')


    for block in FILE_BLOCKS[filename]:
        block = Block(gamefile, block)
        print(block)
        previous_text_offset = block.start
        diff = 0
        for t in Dump.get_translations(block, include_blank=True):
            #print(t.english)
            loc_in_block = t.location - block.start + diff

            for cc in inverse_CTRL:
                t.jp_bytestring = t.jp_bytestring.replace(cc, inverse_CTRL[cc])
                t.en_bytestring = t.en_bytestring.replace(cc, inverse_CTRL[cc])
                if t.prefix is not None:
                    t.prefix = t.prefix.replace(cc, inverse_CTRL[cc])

            this_diff = len(t.en_bytestring) - len(t.jp_bytestring)

            # Taking off training wheels
            #if this_diff > 0:
            #    print(t.en_bytestring, t.jp_bytestring)
            #    raise Exception
            #while this_diff < 0 and t.en_bytestring != b'':
            #    t.en_bytestring += b' '
            #    this_diff = len(t.en_bytestring) - len(t.jp_bytestring)


            if t.english == b'' or t.en_bytestring == t.prefix or t.english == t.japanese:
                #print(hex(t.location), t.english, "Blank string")
                this_diff = 0
                #print("Diff is", diff)

                pointer_gamefile.edit_pointers_in_range((previous_text_offset, t.location), diff)
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
            #while loc_in_block != i:


            block.blockstring = block.blockstring.replace(t.jp_bytestring, t.en_bytestring, 1)

            pointer_gamefile.edit_pointers_in_range((previous_text_offset, t.location), diff)
            previous_text_offset = t.location

            diff += this_diff
            print("Diff is", diff)

        if not filename.endswith('.MSD'):
            block_diff = len(block.blockstring) - len(block.original_blockstring)
            if block_diff < 0:
                block.blockstring += (-1)*block_diff*b'\x00'
            block_diff = len(block.blockstring) - len(block.original_blockstring)
            assert block_diff == 0, block_diff

        block.incorporate()

    gamefile.write(path_in_disk=path_in_disk)
    pointer_gamefile.write(path_in_disk=path_in_disk)
