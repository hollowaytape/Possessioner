"""
    Generic dumper of Shift-JIS text into an excel spreadsheet.
    Meant for quick estimations of how much text is in a game.
"""

import sys
import os
import xlsxwriter
from rominfo import FILE_BLOCKS, FILES, ORIGINAL_ROM_DIR, DUMP_XLS_PATH, CONTROL_CODES, CONCISE_CONTROL_CODES, POINTER_CONSTANT

COMPILER_MESSAGES = [b'Turbo', b'Borland', b'C++', b'Library', b'Copyright']

ASCII_MODE = 2
# 0 = none
# 1: punctuation and c format strings only (not implemented)
# 2: All ascii

THRESHOLD = 2

def dump(files):
    for filename in FILES:
        print(filename)
        worksheet = workbook.add_worksheet(filename)

        OFFSET_COLUMN = 0
        if filename.endswith('.MSD'):
            COMMAND_COLUMN = 1
            CODES_COLUMN = 2
            JP_COLUMN = 3
            JP_LEN_COLUMN = 4
            EN_COLUMN = 5
            EN_LEN_COLUMN = 6
            COMMENT_COLUMN = 7
        else:
            JP_COLUMN = 1
            JP_LEN_COLUMN = 2
            EN_COLUMN = 3
            EN_LEN_COLUMN = 4
            COMMENT_COLUMN = 5

        worksheet.write(0, OFFSET_COLUMN, 'Offset', header)
        worksheet.write(0, JP_COLUMN, 'Japanese', header)
        worksheet.write(0, JP_LEN_COLUMN, 'JP_len', header)
        worksheet.write(0, EN_COLUMN, 'English', header)
        worksheet.write(0, EN_LEN_COLUMN, 'EN_len', header)
        worksheet.write(0, COMMENT_COLUMN, 'Comments', header)

        worksheet.set_column('A:A', 8)
        if filename.endswith('.MSD'):
            worksheet.write(0, COMMAND_COLUMN, 'Command', header)
            worksheet.write(0, CODES_COLUMN, 'Ctrl Codes', header)

            worksheet.set_column('B:B', 20)
            worksheet.set_column('D:D', 50)
            worksheet.set_column('E:E', 5)
            worksheet.set_column('F:F', 50)
            worksheet.set_column('G:G', 5)
            worksheet.set_column('H:H', 50)
            JP_COLUMN_LETTER = 'D'
            EN_COLUMN_LETTER = 'F'
        else:
            worksheet.set_column('B:B', 50)
            worksheet.set_column('C:C', 5)
            worksheet.set_column('D:D', 50)
            worksheet.set_column('E:E', 5)
            worksheet.set_column('F:F', 50)
            JP_COLUMN_LETTER = 'B'
            EN_COLUMN_LETTER = 'D'


        row = 1
        blocks = FILE_BLOCKS[filename]

        src_filepath = os.path.join(ORIGINAL_ROM_DIR, filename)

        #if filename not in UNCOMPRESSED_FILES:
        #    src_filepath = 'original/decompressed/%s.decompressed' % filename
        #else:
        #    src_filepath = 'original/%s' % filename

        with open(os.path.join(src_filepath), 'rb') as f:
            contents = f.read()

            cursor = 0
            sjis_buffer = b""
            sjis_buffer_start = 0
            sjis_strings = []

            for c in COMPILER_MESSAGES:
                #print(c)
                if c in contents:
                    #print(contents)
                    cursor = contents.index(c)
                    sjis_buffer_start = contents.index(c)
                    break

            for (start, stop) in blocks:
                #print((hex(start), hex(stop)))
                cursor = start
                sjis_buffer_start = cursor

                while cursor <= stop:
                    # First byte of SJIS text. Read the next one, too
                    try:
                        if 0x80 <= contents[cursor] <= 0x9f or 0xe0 <= contents[cursor] <= 0xef:
                            #print(bytes(contents[cursor]))
                            sjis_buffer += contents[cursor].to_bytes(1, byteorder='little')
                            cursor += 1
                            sjis_buffer += contents[cursor].to_bytes(1, byteorder='little')

                        ## Halfwidth katakana
                        elif 0xa1 <= contents[cursor] <= 0xdf:
                            sjis_buffer += contents[cursor].to_bytes(1, byteorder='little')

                        # ASCII text
                        elif 0x20 <=contents[cursor] <= 0x7e and ASCII_MODE in (1, 2):
                            sjis_buffer += contents[cursor].to_bytes(1, byteorder='little')

                        elif contents[cursor] in (0xf0, 0xf2, 0xf4, 0xf5):
                            code = contents[cursor:cursor+2]
                            #print(filename, hex(start + cursor))
                            #print(code)
                            sjis_buffer += CONTROL_CODES[code]
                            cursor += 1

                        elif contents[cursor] == 0xf3:
                            code = b'\xf3'
                            sjis_buffer += CONTROL_CODES[code]

                        # End of continuous SJIS string, so add the buffer to the strings and reset buffer
                        else:
                            sjis_strings.append((sjis_buffer_start, sjis_buffer))
                            sjis_buffer = b""
                            sjis_buffer_start = cursor+1
                        cursor += 1
                        #print(sjis_buffer)
                    except IndexError:
                        break

                # Catch anything left after exiting the loop
                if sjis_buffer:
                    sjis_strings.append((sjis_buffer_start, sjis_buffer))
                    sjis_buffer = b''


            if len(sjis_strings) == 0:
                continue

            for s in sjis_strings:
                # Remove leading U's
                #while s[1].startswith(b'U'):
                #    s = (s[0] + 1, s[1][1:])
                #    #s[1] = s[1][1:]
                #    #s[0] += 1

                #s = (s[0], s[1].rstrip(b'U'))

                if s[1].startswith(b'='):
                    s = (s[0], s[1].replace(b'=', b'[=]'))

                if len(s[1]) < THRESHOLD:
                    continue

                codes = b""
                while s[1].startswith(b'['):
                    codes += s[1].split(b']')[0] + b']'
                    s = (s[0], b']'.join(s[1].split(b']')[1:]))
                if codes:
                    #print(codes)
                    for ccc in CONCISE_CONTROL_CODES:
                        codes = codes.replace(ccc, CONCISE_CONTROL_CODES[ccc])
                    #print(codes)

                if codes == b'[Clear]':
                    codes = b''
                    s = (s[0] + 1, s[1])

                command = b''
                # Ignoring this, find_pointers.py has a better way of doing it
                #if b'[Start]' in codes:
                #    command = b'?'

                loc = '0x' + hex(s[0]).lstrip('0x').zfill(5)
                try:
                    jp = s[1].decode('shift-jis')
                except UnicodeDecodeError:
                    print(loc)
                    print(s[1])
                    print("Couldn't decode that")
                    continue

                if len(jp.strip()) == 0:
                    continue
                #print(loc, jp)

                worksheet.write(row, 0, loc)
                worksheet.write(row, JP_COLUMN, jp)

                if filename.endswith('.MSD'):
                    worksheet.write(row, CODES_COLUMN, codes.decode('shift-jis'))
                    worksheet.write(row, COMMAND_COLUMN, command.decode('shift-jis'))

                worksheet.write(row, JP_LEN_COLUMN, "=LEN(%s%s)*2" % (JP_COLUMN_LETTER, row+1))
                worksheet.write(row, EN_LEN_COLUMN, "=LEN(%s%s)" % (EN_COLUMN_LETTER, row+1))
                row += 1

    workbook.close()

if __name__ == '__main__':
    workbook = xlsxwriter.Workbook(DUMP_XLS_PATH)
    header = workbook.add_format({'bold': True, 'align': 'center', 'bottom': True, 'bg_color': 'gray'})

    print(FILES)
    dump(FILES)
