"""
    Text typesetter for Possessioner.
"""
from rominfo import DUMP_XLS_PATH

from romtools.dump import DumpExcel
#from openpyxl.styles import PatternFill

Dump = DumpExcel(DUMP_XLS_PATH)

filenames = ['POS1.MSD', 'YUMI.MSD']


def typeset(text, length):
    if len(text) <= length:
        return [text,]
    lines = []
    words = text.split(' ')
    this_line = ''
    while words:
        if len(this_line + words[0]) + 1 > length:
            this_line = this_line.rstrip(' ')
            lines.append(this_line)
            this_line = ''
        this_line += words.pop(0)
        this_line += ' '

    lines.append(this_line)

    return lines

overflows = 0

for m in filenames:
    print(m)
    worksheet = Dump.workbook.get_sheet_by_name(m)
    first_row = list(worksheet.rows)[0]
    header_values = [t.value for t in first_row]
    en_col = header_values.index('English')
    jp_col = header_values.index('Japanese')
    en_typeset_col = header_values.index('English (Typeset)')
    row_count = 2

    # Clear the typeset column first
    for row in list(worksheet.rows)[1:]:
        row[en_typeset_col].value = ''

    for row in list(worksheet.rows)[1:]:
        nametag = False
        terminal_newline = False
        japanese = row[jp_col].value
        english = row[en_col].value

        if english is None:
            row_count += 1
            continue

        lines = typeset(english, 39)

        lookahead_index = 0
        free_row_count = 0
        for j, l in enumerate(lines):
            if len(list(worksheet.rows)) > row_count+j:
                if list(worksheet.rows)[row_count+j][en_col].value is None:
                    print ("blank ->" + l)
                    free_row_count += 1
                else:
                    print(list(worksheet.rows)[row_count+j][en_col].value + " -> " + l)

        if len(lines) == 1:
            row[en_typeset_col].value = lines[0]
            lines = []

        for f in range(free_row_count):
            #print("Looking at row", row_count+f-1, list(worksheet.rows)[row_count+f-1][en_col].value)
            print(lines)
            print(f, free_row_count)
            if lines:
                if f == free_row_count:
                    print("Putting the rest of the lines here")
                    print('[LN]'.join(lines))
                    list(worksheet.rows)[row_count+f-1][en_typeset_col].value = '[LN]'.join(lines)
                    lines = []
                else:
                    list(worksheet.rows)[row_count+f-1][en_typeset_col].value = lines.pop(0)

        # Catch remaining lines (especially if it's a one-line string)
        if lines:
            print("Remaining lines:", lines)
            list(worksheet.rows)[row_count+free_row_count-1][en_typeset_col].value = '[LN]'.join(lines)

        row_count += 1


        #row[en_typeset_col].value = english

Dump.workbook.save(DUMP_XLS_PATH)

print("%s windows overflow" % overflows)