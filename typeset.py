"""
    Text typesetter for Possessioner.
"""
from rominfo import DUMP_XLS_PATH, FILES_TO_REINSERT

from romtools.dump import DumpExcel
#from openpyxl.styles import PatternFill

def run_typesetting():
    Dump = DumpExcel(DUMP_XLS_PATH)

    filenames = FILES_TO_REINSERT
    filenames.remove('POS.EXE')
    filenames.remove('POSM.EXE')
    filenames.remove('POSE.EXE')

    filenames = [f for f in filenames if f.endswith(".MSD")]
    print(filenames)

    def typeset(text, length):
        text = text.replace("\x0a", "[LN]")
        if len(text) <= length:
            return [text,]
        lines = []
        words = text.split(' ')
        this_line = ''
        while words:
            # Handle manual line breaks
            if '[LN]' in words[0]:
                ln_words = words.pop(0).split('[LN]')
                this_line += ln_words[0]
                lines.append(this_line)
                this_line = ''
                words.insert(0, ln_words[1])
                continue

            # Handle the normal case
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
        worksheet = Dump.workbook[m]
        first_row = list(worksheet.rows)[0]
        header_values = [t.value for t in first_row]
        command_col = header_values.index('Command')
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

            lookahead_index = -1
            free_row_count = 1

            for j, l in enumerate(lines):
                #print(j, l)
                try:
                    if list(worksheet.rows)[row_count+j][en_col].value is None and list(worksheet.rows)[row_count+j][command_col].value is None:
                        #print("Blank")
                        #print ("blank ->" + l)
                        free_row_count += 1
                    else:
                        #print("Running into " + str(list(worksheet.rows)[row_count+j][en_col].value))
                        #print(list(worksheet.rows)[row_count+j][en_col].value + " -> " + l)
                        break
                except IndexError:
                    print("At the end of the sheet now")
                    break


            print("Lines: %s, free_lines: %s" % (len(lines), free_row_count))

            # If there's only one, just dump them all separated with [LN]s in that line
            if free_row_count <= 1:
                print('[LN]'.join(lines))
                list(worksheet.rows)[row_count+lookahead_index][en_typeset_col].value = '[LN]'.join(lines)
                #free_row_count = 0
                #lines = []
                row_count += 1
                continue

            # If there is space to spare, just put them all one after another
            if free_row_count >= len(lines):
                # Put each line
                while lines:
                    print(lines[0])
                    assert list(worksheet.rows)[row_count+lookahead_index][en_typeset_col].value == '', list(worksheet.rows)[row_count+lookahead_index][en_typeset_col].value
                    list(worksheet.rows)[row_count+lookahead_index][en_typeset_col].value = lines.pop(0)
                    lookahead_index += 1
                    free_row_count -= 1
                # Put blanks in the rest of the space
                if free_row_count > 1:
                    print("Spare lines: %s" % free_row_count)
                    while free_row_count > 1:
                        assert list(worksheet.rows)[row_count+lookahead_index][en_typeset_col].value == '', list(worksheet.rows)[row_count+lookahead_index][en_typeset_col].value
                        list(worksheet.rows)[row_count+lookahead_index][en_typeset_col].value = '[BLANK]'
                        lookahead_index += 1
                        free_row_count -= 1
                assert lines == []

            # Otherwise, dump them individually and then squish the rest in the last line
            while free_row_count > 1 and lines:
                # Make sure the row is empty
                dest_row = list(worksheet.rows)[row_count+lookahead_index][en_typeset_col].value
                assert dest_row == "", dest_row

                # Write a line
                print(lines[0])
                list(worksheet.rows)[row_count+lookahead_index][en_typeset_col].value = lines.pop(0)
                lookahead_index += 1
                free_row_count -= 1
            if lines:
                try:
                    dest_row = list(worksheet.rows)[row_count+lookahead_index][en_typeset_col].value
                    assert dest_row == "", dest_row

                    # Write all the rest of the lines
                    print('[LN]'.join(lines))
                    list(worksheet.rows)[row_count+lookahead_index][en_typeset_col].value = '[LN]'.join(lines)
                except IndexError:
                    # TODO: Better handling
                    print("Well, that's the last string")
                lines = []

            row_count += 1


            #row[en_typeset_col].value = english

    Dump.workbook.save(DUMP_XLS_PATH)

    print("%s windows overflow" % overflows)

if __name__ == "__main__":
    run_typesetting()