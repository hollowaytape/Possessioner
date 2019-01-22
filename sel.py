"""
    .SEL encoder for Possessioner.
"""

from shutil import copyfile
from PIL import Image
from bitstring import BitArray
from romtools.disk import Disk
from rominfo import TARGET_ROM_PATH

def encode(filename):
    sel_filename = filename.replace('png', 'sel')

    img = Image.open(filename)
    width, height = img.size
    blocks = width//8
    pix = img.load()

    pattern_sequence = []
    for b in range(blocks):
        for row in range(height):
            rowdata =[pix[col, row][0:3] for col in range(b*8, (b*8)+8)]
            pattern = []
            for p in rowdata:
                if p != (0, 0, 0):
                    pattern.append(True)
                else:
                    pattern.append(False)
            pattern = BitArray(pattern).bytes
            pattern_sequence.append(pattern)

    with open(sel_filename, 'wb') as f:
        f.write(blocks.to_bytes(1, 'little'))
        f.write(height.to_bytes(2, 'little'))

        pattern_cursor = 0
        while pattern_cursor < len(pattern_sequence):
            pattern = pattern_sequence[pattern_cursor]

            # Full lines
            if pattern == b'\xff':
                consecutive_full_lines = 1
                pattern_cursor += 1

                if pattern_cursor < len(pattern_sequence):

                    while pattern_sequence[pattern_cursor] == b'\xff':
                        consecutive_full_lines += 1
                        pattern_cursor += 1

                        if pattern_cursor == len(pattern_sequence):
                            break

                print(consecutive_full_lines, "consecutive full lines there")
                full_line_byte = 0x28 + consecutive_full_lines
                f.write(full_line_byte.to_bytes(1, 'little'))

            # Binary writes
            else:
                consecutive_binary_writes = 1
                binaries = [pattern_sequence[pattern_cursor]]
                pattern_cursor += 1
                while pattern_sequence[pattern_cursor] != b'\xff':
                    binaries.append(pattern_sequence[pattern_cursor])
                    consecutive_binary_writes += 1
                    pattern_cursor += 1

                    if pattern_cursor == len(pattern_sequence):
                        break

                print(consecutive_binary_writes, "consecutive binary writes there")
                print("the binary is:", binaries)
                binary_write_byte = 0xc8 + consecutive_binary_writes
                f.write(binary_write_byte.to_bytes(1, 'little'))
                for b in binaries:
                    f.write(b)

        # Divider
        f.write(b'\x00')

        # Thing with the 28's. Dunno what it is
        height_to_cover = height * blocks
        while height_to_cover > 0x28:
            f.write(b'\x28')
            height_to_cover -= 0x28
        f.write(height_to_cover.to_bytes(1, 'little'))
        f.write(b'\x00')

        # 2nd plane thing? with the f1
        height_to_cover = height * blocks
        while height_to_cover > 0xff:
            f.write(b'\xf1')
            f.write(b'\xff')
            height_to_cover -= 0xff
        f.write(b'\xf1')
        f.write(height_to_cover.to_bytes(1, 'little'))
        f.write(b'\x00')

        # 3rd plane thing? with the f2
        height_to_cover = height * blocks
        while height_to_cover > 0xff:
            f.write(b'\xf2')
            f.write(b'\xff')
            height_to_cover -= 0xff
        f.write(b'\xf2')
        f.write(height_to_cover.to_bytes(1, 'little'))
        f.write(b'\x00')

if __name__ == "__main__":
    filenames = ["font.png", "font2.png"]

    for filename in filenames:
        sel_filename = filename.replace('.png', '.sel')

        encode('img/edited/%s' % filename)
        copyfile('img/edited/%s' % sel_filename, 'patched/%s' % sel_filename)

        disk = Disk(TARGET_ROM_PATH)
        disk.insert('patched/%s' % sel_filename, path_in_disk='PSSR')

