"""
    Rom description of Possessioner.
"""

import os

ORIGINAL_ROM_DIR = 'original'
TARGET_ROM_DIR = 'patched'

ORIGINAL_ROM_PATH = os.path.join(ORIGINAL_ROM_DIR, 'Possessioner.hdi')
TARGET_ROM_PATH = os.path.join(TARGET_ROM_DIR, 'Possessioner.hdi')
DUMP_XLS_PATH = 'PSSR_dump.xlsx'
POINTER_DUMP_XLS_PATH = 'PSSR_pointer_dump.xlsx'

FILES = ['POSM.EXE', 'POS.EXE', 'POS1.MSD', 'P_7.MSD', 'P_71.MSD', 
         'P_BILL.MLL', 'P_BILL.MSD', 'P_BOX.MSD', 'P_BYO.MSD',
         'P_CITY.MSD', 'P_ENT.MSD', 'P_ENT2.MSD', 'P_GE.MSD', 
         'P_GYOTEI.MSD', 'P_GYOTEI.MSG', 'P_HI.MSD', 'P_HON1.MSD',
         'P_HOU.MSD', 'P_JUNK.MSD', 'P_KYU.MSD', 'P_ROU1.MSD',
         'P_SE.MSD', 'P_SIRYO.MSD', 'P_SUTE.MSD', 'P_SW1.MSD',
         'P_SYO.MSD', 'RASU1.MSD', 'RASU2.MSD', 'STAFF.TXT',
         'TINA.MSD', 'YUMI.MSD', 'ARISA.MSD', 'AYAKA.MSD',
         'ERIS.MSD', 'HONHOA.MSD', 'MAI.MSD', 'MERYL.MSD', 
         'MINS.MSD', 'MISHA.MSD', 'NEDRA1.MSD', 'NEDRA2.MSD',
         'DOCTOR.MSD', 'PLYM.MSD', 
         'POSE.EXE', 'END.MSD', ]

# .M files have song titles/descriptions in them, probably just internal
# "Arisa, songs of being fucked by the machine"


FILE_BLOCKS = {
    "POS.EXE": [
        (0x7fcf, 0x800b),
        (0x8b03, 0x9329),
        (0xa122, 0xa397),  # table thing
        (0xab98, 0xac3e),
        (0xcf61, 0xd12a),
        (0xdb2d, 0xdb3f), # Arisa
        (0xdb63, 0xdb74), # Hong Ho
        (0xdb99, 0xdbaa), # Melissa
        (0xdbcf, 0xdbe0), # Sedora
        # Some more annoying ones to map between 0xdc13 and 0sdd93
        (0xe00b, 0xe1fb),
        # and a ton more between ~0x17000 and 0x28000
    ],

    "POSE.EXE": [
        (0x9628, 0x9648), # errors
        (0x98fe, 0x9cfc), # ending text?
    ],

    'POSM.EXE': [
        (0xb238, 0xb450),  # sound test songs
        (0xb88c, 0xbf18),  # intro text
    ]
}

POINTER_CONSTANT = {
    'POS.EXE': 0x7b00,
    'POSM.EXE': 0xafe0,
    'POS1.MSD': 0,
}

# b238  = 58 02
# b244 = 64 02
# b251 = 71 02

# Plain, continuous pointer tables with no distinguishing prefix/suffix/separator.
POINTER_TABLES = {
    'POS.EXE': [
        (0x88bf, 0x8b03),
    ]
}

POINTER_TABLE_SEPARATOR = {
    'POSM.EXE': '\\\\x1e\\\\x0a'
}

# default to dumping the whole file
for f in FILES:
    if f not in FILE_BLOCKS:
        FILE_BLOCKS[f] = [(0, 0xfffff)]

assert len(FILE_BLOCKS) == len(FILES), "%s %s" % (len(FILE_BLOCKS), len(FILES))