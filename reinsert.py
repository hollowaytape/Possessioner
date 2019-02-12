"""
    Possessioner reinserter.
    Based on the CRW reinserter base via Pssr98-II.
"""

import os

from rominfo import FILE_BLOCKS, FILES_TO_REINSERT, ORIGINAL_ROM_PATH, TARGET_ROM_PATH, DUMP_XLS_PATH, POINTER_DUMP_XLS_PATH, inverse_CONCISE_CTRL, inverse_CTRL
from romtools.disk import Disk, Gamefile, Block
from romtools.dump import DumpExcel, PointerExcel

Dump = DumpExcel(DUMP_XLS_PATH)
PtrDump = PointerExcel(POINTER_DUMP_XLS_PATH)
OriginalPssr = Disk(ORIGINAL_ROM_PATH, dump_excel=Dump, pointer_excel = PtrDump)
TargetPssr = Disk(TARGET_ROM_PATH)

MAPPING_MODE = True

for filename in FILES_TO_REINSERT:
    path_in_disk = "PSSR\\"
    gamefile_path = os.path.join('original', filename)
    print(filename)
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
        print(block)
        previous_text_offset = block.start
        diff = 0
        for i, t in enumerate(Dump.get_translations(block, include_blank=True)):
            #print(t.english)
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

            block.blockstring = block.blockstring.replace(t.jp_bytestring, t.en_bytestring, 1)
            #print(block.blockstring)

            pointer_gamefile.edit_pointers_in_range((previous_text_offset, t.location), diff)
            previous_text_offset = t.location

            diff += this_diff
            #print("Diff is", diff)

        if not filename.endswith('.MSD'):
            block_diff = len(block.blockstring) - len(block.original_blockstring)
            if block_diff < 0:
                block.blockstring += (-1)*block_diff*b'\x00'
            block_diff = len(block.blockstring) - len(block.original_blockstring)
            assert block_diff == 0, block_diff

        block.incorporate()

    gamefile.write(path_in_disk=path_in_disk)
    pointer_gamefile.write(path_in_disk=path_in_disk)
