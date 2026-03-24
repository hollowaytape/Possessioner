"""
    Generic dumper of Shift-JIS text into an excel spreadsheet.
    Meant for quick estimations of how much text is in a game.
"""

import sys
import os
import xlsxwriter
from analyze_dispatch_contexts import scan_dispatch_context_lookup
from analyze_handoff_contexts import scan_handoff_context_lookup, summarize_handoff_details
from rominfo import FILE_BLOCKS, FILES, ORIGINAL_ROM_DIR, DUMP_XLS_PATH, CONTROL_CODES, CONCISE_CONTROL_CODES, POINTER_CONSTANT
from command_groups import (
    find_arrival_groups,
    find_command_groups,
    find_direct_range_groups,
    format_offset,
    load_pos_exe_bytes,
)

COMPILER_MESSAGES = [b'Turbo', b'Borland', b'C++', b'Library', b'Copyright']

ASCII_MODE = 2
# 0 = none
# 1: punctuation and c format strings only (not implemented)
# 2: All ascii

THRESHOLD = 2


def summarize_dispatch_details(dispatch_contexts):
    grouped = {}

    for context in dispatch_contexts:
        action = str(context.get("action") or "").strip()
        target = str(context.get("target") or "").strip()
        command_label = str(context.get("command") or "").strip()
        header_location = context.get("header_location")
        key = (header_location, action, target, command_label)
        entry = grouped.setdefault(key, {"inline": False, "via_locations": []})
        via_target_location = context.get("via_target_location")
        if isinstance(via_target_location, int):
            if via_target_location not in entry["via_locations"]:
                entry["via_locations"].append(via_target_location)
        else:
            entry["inline"] = True

    details = []
    for (header_location, action, target, command_label), entry in grouped.items():
        route_bits = []
        if action:
            route_bits.append(action)
        if target:
            route_bits.append(target)
        route_text = " / ".join(route_bits) if route_bits else "dispatch context"
        if command_label:
            route_text += f" -> {command_label}"

        qualifier_bits = []
        if isinstance(header_location, int):
            qualifier_bits.append(f"header {format_offset(header_location)}")
        if entry["inline"]:
            qualifier_bits.append("inline")
        if entry["via_locations"]:
            qualifier_bits.append("via " + ", ".join(format_offset(location) for location in entry["via_locations"]))

        if qualifier_bits:
            route_text += " [" + "; ".join(qualifier_bits) + "]"
        details.append(route_text)

    return details

def dump(files):
    pos_exe_bytes = load_pos_exe_bytes()

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
            GROUP_LABEL_COLUMN = 8
            GROUP_START_COLUMN = 9
            GROUP_SIZE_COLUMN = 10
            DISPLAY_TYPE_COLUMN = 11
            DISPLAY_DETAIL_COLUMN = 12
            DISPATCH_ACTION_COLUMN = 13
            DISPATCH_TARGET_COLUMN = 14
            DISPATCH_HEADER_COLUMN = 15
            DISPATCH_DETAIL_COLUMN = 16
            HANDOFF_TYPE_COLUMN = 17
            HANDOFF_DESTINATION_COLUMN = 18
            HANDOFF_DETAIL_COLUMN = 19
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
            worksheet.write(0, GROUP_LABEL_COLUMN, 'Command Group Label', header)
            worksheet.write(0, GROUP_START_COLUMN, 'Command Group Start', header)
            worksheet.write(0, GROUP_SIZE_COLUMN, 'Command Group Size', header)
            worksheet.write(0, DISPLAY_TYPE_COLUMN, 'Command Display Type', header)
            worksheet.write(0, DISPLAY_DETAIL_COLUMN, 'Command Display Detail', header)
            worksheet.write(0, DISPATCH_ACTION_COLUMN, 'Command Dispatch Action', header)
            worksheet.write(0, DISPATCH_TARGET_COLUMN, 'Command Dispatch Target', header)
            worksheet.write(0, DISPATCH_HEADER_COLUMN, 'Command Dispatch Header', header)
            worksheet.write(0, DISPATCH_DETAIL_COLUMN, 'Command Dispatch Detail', header)
            worksheet.write(0, HANDOFF_TYPE_COLUMN, 'Command Handoff Type', header)
            worksheet.write(0, HANDOFF_DESTINATION_COLUMN, 'Command Handoff Destination', header)
            worksheet.write(0, HANDOFF_DETAIL_COLUMN, 'Command Handoff Detail', header)

            worksheet.set_column('B:B', 20)
            worksheet.set_column('D:D', 50)
            worksheet.set_column('E:E', 5)
            worksheet.set_column('F:F', 50)
            worksheet.set_column('G:G', 5)
            worksheet.set_column('H:H', 50)
            worksheet.set_column('I:I', 30)
            worksheet.set_column('J:J', 12)
            worksheet.set_column('K:K', 8)
            worksheet.set_column('L:L', 22)
            worksheet.set_column('M:M', 50)
            worksheet.set_column('N:N', 18)
            worksheet.set_column('O:O', 18)
            worksheet.set_column('P:P', 16)
            worksheet.set_column('Q:Q', 60)
            worksheet.set_column('R:R', 22)
            worksheet.set_column('S:S', 32)
            worksheet.set_column('T:T', 60)
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

            sheet_rows = []

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

                loc = format_offset(s[0])
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

                row_data = {
                    "offset": s[0],
                    "loc": loc,
                    "jp": jp,
                    "codes": codes.decode('shift-jis') if filename.endswith('.MSD') else '',
                    "command": command.decode('shift-jis') if filename.endswith('.MSD') else '',
                    "group_label": '',
                    "group_start": '',
                    "group_size": '',
                    "display_type": '',
                    "display_detail": '',
                    "dispatch_action": '',
                    "dispatch_target": '',
                    "dispatch_header": '',
                    "dispatch_detail": '',
                    "handoff_type": '',
                    "handoff_destination": '',
                    "handoff_detail": '',
                }
                sheet_rows.append(row_data)

            if filename.endswith('.MSD'):
                current_block_command = ''
                for row_data in sheet_rows:
                    if row_data["command"]:
                        current_block_command = row_data["command"]
                    row_data["block_command"] = current_block_command

                row_offsets = [row_data["offset"] for row_data in sheet_rows]
                _, grouped_rows = find_command_groups(filename, row_offsets, pos_exe_bytes)
                arrival_rows = find_arrival_groups(filename, row_offsets, pos_exe_bytes)
                direct_range_rows = find_direct_range_groups(filename, row_offsets, pos_exe_bytes)
                dispatch_context_lookup = scan_dispatch_context_lookup(
                    filename,
                    pos_exe_bytes,
                    [
                        {
                            "file": filename,
                            "offset": row_data["offset"],
                            "command": row_data["command"],
                            "block_command": row_data["block_command"],
                            "english": row_data["jp"],
                        }
                        for row_data in sheet_rows
                    ],
                )
                handoff_context_lookup = scan_handoff_context_lookup(
                    filename,
                    pos_exe_bytes,
                    [
                        {
                            "file": filename,
                            "offset": row_data["offset"],
                            "command": row_data["command"],
                            "block_command": row_data["block_command"],
                            "english": row_data["jp"],
                        }
                        for row_data in sheet_rows
                    ],
                )
                for row_data in sheet_rows:
                    groups = grouped_rows.get(row_data["offset"], [])
                    if groups:
                        row_data["group_label"] = "; ".join(format_offset(start) for start, _size in groups)
                        row_data["group_start"] = "; ".join(format_offset(start) for start, _size in groups)
                        row_data["group_size"] = "; ".join(str(size) for _start, size in groups)

                    display_types = []
                    display_details = []
                    for start, size in groups:
                        display_types.append('0x02 text command')
                        display_details.append(f'0x02 group {format_offset(start)} size {size}')
                    for start, size, pointer_loc in arrival_rows.get(row_data["offset"], []):
                        display_types.append('arrival text')
                        display_details.append(f'arrival {format_offset(start)} size {size} via {format_offset(pointer_loc)}')
                    for start, size, call_loc in direct_range_rows.get(row_data["offset"], []):
                        display_types.append('direct range call')
                        display_details.append(f'direct range {format_offset(start)} size {size} via {format_offset(call_loc)}')
                    if not display_types and row_data["offset"] == 0 and row_data["command"] == '(Arrive)':
                        display_types.append('arrival text')
                        display_details.append('arrival offset 0 (no pointer override known)')

                    row_data["display_type"] = "; ".join(display_types)
                    row_data["display_detail"] = "; ".join(display_details)

                    dispatch_contexts: list[dict[str, object]] = []
                    seen_dispatch_keys: set[tuple[object, ...]] = set()
                    dispatch_start_offsets = {row_data["offset"]}
                    dispatch_start_offsets.update(start_offset for start_offset, _size in groups)
                    dispatch_start_offsets.update(
                        start_offset for start_offset, _size, _pointer_location in arrival_rows.get(row_data["offset"], [])
                    )
                    dispatch_start_offsets.update(
                        start_offset for start_offset, _size, _call_location in direct_range_rows.get(row_data["offset"], [])
                    )

                    for start_offset in sorted(dispatch_start_offsets):
                        for context in dispatch_context_lookup.get(start_offset, []):
                            key = (
                                context["header_location"],
                                context["via_target_location"],
                                context["action"],
                                context["target"],
                                context["command"],
                            )
                            if key in seen_dispatch_keys:
                                continue
                            seen_dispatch_keys.add(key)
                            dispatch_contexts.append(context)

                    dispatch_actions = []
                    dispatch_targets = []
                    dispatch_headers = []
                    dispatch_details = []
                    for context in dispatch_contexts:
                        action = str(context.get("action") or "").strip()
                        target = str(context.get("target") or "").strip()
                        header_location = context.get("header_location")

                        if action and action not in dispatch_actions:
                            dispatch_actions.append(action)
                        if target and target not in dispatch_targets:
                            dispatch_targets.append(target)

                        if isinstance(header_location, int):
                            header_text = format_offset(header_location)
                            if header_text not in dispatch_headers:
                                dispatch_headers.append(header_text)

                    dispatch_details = summarize_dispatch_details(dispatch_contexts)

                    row_data["dispatch_action"] = "; ".join(dispatch_actions)
                    row_data["dispatch_target"] = "; ".join(dispatch_targets)
                    row_data["dispatch_header"] = "; ".join(dispatch_headers)
                    row_data["dispatch_detail"] = "; ".join(dispatch_details)

                    handoff_contexts = []
                    seen_handoff_keys = set()
                    handoff_start_offsets = {row_data["offset"]}
                    handoff_start_offsets.update(start_offset for start_offset, _size in groups)
                    handoff_start_offsets.update(
                        start_offset for start_offset, _size, _pointer_location in arrival_rows.get(row_data["offset"], [])
                    )
                    handoff_start_offsets.update(
                        start_offset for start_offset, _size, _call_location in direct_range_rows.get(row_data["offset"], [])
                    )

                    for start_offset in sorted(handoff_start_offsets):
                        for context in handoff_context_lookup.get(start_offset, []):
                            key = (context["location"], context["arg1"], context["destination_name"], context["handoff_type"])
                            if key in seen_handoff_keys:
                                continue
                            seen_handoff_keys.add(key)
                            handoff_contexts.append(context)

                    handoff_types = []
                    handoff_destinations = []
                    for context in handoff_contexts:
                        handoff_type = str(context.get("handoff_type") or "").strip()
                        destination_name = str(context.get("destination_label") or "").strip()
                        if handoff_type and handoff_type not in handoff_types:
                            handoff_types.append(handoff_type)
                        if destination_name and destination_name not in handoff_destinations:
                            handoff_destinations.append(destination_name)

                    row_data["handoff_type"] = "; ".join(handoff_types)
                    row_data["handoff_destination"] = "; ".join(handoff_destinations)
                    row_data["handoff_detail"] = "; ".join(summarize_handoff_details(handoff_contexts))

            for row_data in sheet_rows:
                worksheet.write(row, 0, row_data["loc"])
                worksheet.write(row, JP_COLUMN, row_data["jp"])

                if filename.endswith('.MSD'):
                    worksheet.write(row, CODES_COLUMN, row_data["codes"])
                    worksheet.write(row, COMMAND_COLUMN, row_data["command"])
                    worksheet.write(row, GROUP_LABEL_COLUMN, row_data["group_label"])
                    worksheet.write(row, GROUP_START_COLUMN, row_data["group_start"])
                    worksheet.write(row, GROUP_SIZE_COLUMN, row_data["group_size"])
                    worksheet.write(row, DISPLAY_TYPE_COLUMN, row_data["display_type"])
                    worksheet.write(row, DISPLAY_DETAIL_COLUMN, row_data["display_detail"])
                    worksheet.write(row, DISPATCH_ACTION_COLUMN, row_data["dispatch_action"])
                    worksheet.write(row, DISPATCH_TARGET_COLUMN, row_data["dispatch_target"])
                    worksheet.write(row, DISPATCH_HEADER_COLUMN, row_data["dispatch_header"])
                    worksheet.write(row, DISPATCH_DETAIL_COLUMN, row_data["dispatch_detail"])
                    worksheet.write(row, HANDOFF_TYPE_COLUMN, row_data["handoff_type"])
                    worksheet.write(row, HANDOFF_DESTINATION_COLUMN, row_data["handoff_destination"])
                    worksheet.write(row, HANDOFF_DETAIL_COLUMN, row_data["handoff_detail"])

                worksheet.write(row, JP_LEN_COLUMN, "=LEN(%s%s)*2" % (JP_COLUMN_LETTER, row+1))
                worksheet.write(row, EN_LEN_COLUMN, "=LEN(%s%s)" % (EN_COLUMN_LETTER, row+1))
                row += 1

    workbook.close()

if __name__ == '__main__':
    workbook = xlsxwriter.Workbook(DUMP_XLS_PATH)
    header = workbook.add_format({'bold': True, 'align': 'center', 'bottom': True, 'bg_color': 'gray'})

    print(FILES)
    dump(FILES)
