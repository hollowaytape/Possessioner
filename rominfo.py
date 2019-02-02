"""
    Rom description of Possessioner.
"""

import os
from collections import OrderedDict

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

CONTROL_CODES = {
    b'\x0d\xf3': b'[LN]',

    b'\x0d': b'[0d]',

    # Text colors
    b'\xf0\x00': b'[Black]',
    b'\xf0\x01': b'[Blue]',
    b'\xf0\x02': b'[Red]',
    b'\xf0\x03': b'[Purple]',
    b'\xf0\x04': b'[Green]',
    b'\xf0\x05': b'[Cyan]',
    b'\xf0\x06': b'[Yellow]',
    b'\xf0\x07': b'[White]',

    # Fucked up Nedra codes
    b'\xf0\x4a': b'[Red, but 4a]',
    b'\xf0\x54': b'[Green, but 54]',

    # Nmaetags
    b'\xf2\x01': b'[Alisa]',
    b'\xf2\x02': b'[Meryl]',
    b'\xf2\x03': b'[Honghua]',
    b'\xf2\x04': b'[Operator]',
    b'\xf2\x05': b'[Possessioner]',
    b'\xf2\x06': b'[Nedra]',
    b'\xf2\x07': b'[Yumi]',
    b'\xf2\x08': b'[Ayaka]',
    b'\xf2\x09': b'[Purim]',
    b'\xf2\x0a': b'[Eris]',
    b'\xf2\x0b': b'[Deal]',
    b'\xf2\x0c': b'[Kumiko]',
    b'\xf2\x0d': b'[Message]',
    b'\xf2\x0e': b'[Voice]',
    b'\xf2\x0f': b'[Janitor 1]',
    b'\xf2\x10': b'[Janitor 2]',
    b'\xf2\x11': b'[Janitor 3]',
    b'\xf2\x12': b'[Clerk]',
    b'\xf2\x13': b'[Owner]',
    b'\xf2\x14': b'[Receptionist]',
    b'\xf2\x15': b'[Passerby 1]',
    b'\xf2\x16': b'[Passerby 2]',
    b'\xf2\x17': b'[Doctor]',
    b'\xf2\x18': b'[Assistant]',
    b'\xf2\x19': b'[Master]',
    b'\xf2\x1a': b'[Passerby]',
    b'\xf2\x1b': b'[Carmine]',
    b'\xf2\x1c': b'[Iris]',
    b'\xf2\x1d': b'[Michaas]',
    b'\xf2\x1e': b'[May]',
    b'\xf2\x1f': b'[Person]',
    b'\xf2\x20': b'[Man]',
    b'\xf2\x21': b'[Rashmar]',
    b'\xf2\x22': b'[Empress]',
    b'\xf2\x23': b'[Girl]',
    b'\xf2\x24': b'[Fairy]',
    b'\xf2\x25': b'[Tina]',

    b'\xf2\x2c': b'[I really dunno]',
    b'\xf2\x44': b'[I still dunno]',

    b'\xf3': b'[Clear?]',

    # Portraits
    b'\xf4\x00': b'[P-Same]',
    b'\xf4\x01': b'[P-Al-Neutral]',
    b'\xf4\x02': b'[P-Al-Energetic]',
    b'\xf4\x03': b'[P-Al-Upset]',
    b'\xf4\x04': b'[P-Al-Surprised]',
    b'\xf4\x05': b'[P-Ho-Neutral]',
    b'\xf4\x06': b'[P-Ho-Happy]',
    b'\xf4\x07': b'[P-Ho-Upset]',
    b'\xf4\x08': b'[P-Ho-Sad]',
    b'\xf4\x09': b'[P-Me-Neutral]',
    b'\xf4\x0a': b'[P-Me-Excited]',
    b'\xf4\x0b': b'[P-Me-Upset]',
    b'\xf4\x0c': b'[P-Me-Sad]',
    b'\xf4\x0d': b'[P-Ne-Neutral]',
    b'\xf4\x0e': b'[P-Ne-Happy]',
    b'\xf4\x0f': b'[P-Ne-Upset]',
    b'\xf4\x10': b'[P-Ne-Sad]',
    # Operators? Dunno their names yet
    b'\xf4\x11': b'[P-Blonde]',
    b'\xf4\x12': b'[P-Brun',
    b'\xf4\x13': b'[P-Blue]',

    # Text things
    b'\xf5\x00': b'[Start]',
    b'\xf5\x01': b'[Continue]',
    b'\xf5\x02': b'[f502?]',
    b'\xf5\x03': b'[f503?]',
}

inverse_CTRL = {v: k for k, v in CONTROL_CODES.items()}


FILE_BLOCKS = {
    "POS.EXE": [
        (0x7fcf, 0x800b),
        (0x8b03, 0x9329),
        (0xa122, 0xa397),  # table thing
        (0xab98, 0xac3e),
        (0xcf61, 0xd12a),
        (0xdb2d, 0xdb3f), # Alisa
        (0xdb63, 0xdb74), # Honghua
        (0xdb99, 0xdbaa), # Meryl
        (0xdbcf, 0xdbe0), # Nedra
        (0xdc13, 0xdc23), # BC 1
        (0xdc60, 0xdc70), # 
        (0xdcad, 0xdcbd), #
        (0xdcfa, 0xdd0a), # Yumi
        (0xdd47, 0xdd57), # Yumi
        (0xdd93, 0xdda3), # Yumi
        (0xe00b, 0xe1fb),

        (0xf0ac, 0xf0bc), # BC 1
        (0xf0f9, 0xf109), # BC 2
        (0xf146, 0xf156), # BC 3
        (0xf193, 0xf1a3), # Yumi

        # The rest are all Bio Clusters
        (0x162a4, 0x162b4),
        (0x162f1, 0x16301),
        (0x1633e, 0x1634e),
        (0x1638b, 0x1639b),

        (0x166b3, 0x166c3),
        (0x16700, 0x16710),
        (0x1674d, 0x1675d),
        (0x1679a, 0x167aa),
        (0x16c22, 0x16c32),

        (0x17338, 0x17348),
        (0x17385, 0x17395),
        (0x173d2, 0x173e2),
        (0x1741f, 0x1742f),

        (0x17596, 0x175a6),
        (0x175e3, 0x175f3),
        (0x17630, 0x17640),
        (0x17900, 0x17910),
        (0x1794d, 0x1795d),
        (0x1799a, 0x179aa),

        (0x17ce1, 0x17cf1),
        (0x17d2e, 0x17d3e),

        (0x1814a, 0x1815a),
        (0x18380, 0x18390),
        (0x183cd, 0x183dd),

        (0x186f8, 0x18708),
        (0x18745, 0x18755),
        (0x18792, 0x187a2),

        (0x18a5b, 0x18a6b),
        (0x18aa8, 0x18ab8),
        (0x18af5, 0x18b05),

        (0x18f7c, 0x18f8c),
        (0x18fc9, 0x18fd9),

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

POINTER_CONSTANT = OrderedDict({
    'POS.EXE': 0x7b00,
    'POSM.EXE': 0xafe0,
    'POS1.MSD': 0,    # HQ (intro)
    'YUMI.MSD': 0,
    'P_HON1.MSD': 0,  # HQ
    'P_ROU1.MSD': 0,   # Corridor
    'P_SE.MSD': 0,    # Maintenance Room
    'P_ENT.MSD': 0,   # Entrance
    'P_BYO.MSD': 0,   # Medical Ward
    'P_HI.MSD': 0,    # Lounge
    'P_SW1.MSD': 0,   # Shower
    'MERYL.MSD': 0,
})

MSD_POINTER_RANGES = {
    'POS1.MSD': [
        (0xeaf6, 0xee2f)
    ],
    'YUMI.MSD': [
        (0xefcc, 0xf06a),     # Adv scene
        (0x2776e, 0x28aac)    # Yumi scene
    ],
    'MERYL.MSD': [
        (0x1c252, 0x1e10e),
    ],
    'P_BYO.MSD': [
        (0x1a81a, 0x1c000),
    ],
    'P_SE.MSD': [
        (0x28700, 0x291e1)
    ],
    'P_ENT.MSD': [
        (0x1b115, 0x1ff00),
    ],
    'P_HI.MSD': [
        (0x128a2, 0x13d19),
    ],
    'P_HON1.MSD': [
        (0xf2fe, 0x10c8e),
    ],
    'P_ROU1.MSD': [
        (0x21061, 0x24000),
    ]
}

# Plain, continuous pointer tables with no distinguishing prefix/suffix/separator.
POINTER_TABLES = {
    'POS.EXE': [
        (0x88bf, 0x8b03),
        (0xdfab, 0xe00b), # battle things
    ]
}

POINTER_TABLE_SEPARATOR = {
    'POSM.EXE': '\\\\x1e\\\\x0a'
}

#BAD_POINTERS = [
#    (0xd0a8, )  # oops, this wasn't bad

    # Battle crashes from POS1.MSD
#    (0xe13, 0xc3b9), 
#    (0xdf2, 0x263d4),
#]

# This is a better idea
POINTER_DISAMBIGUATION = [
    ('P_HON1.MSD', 0x1ff, 0xf59f),
    ('POS1.MSD', 0xe13, 0xed59),
    ('POS1.MSD', 0xdf2, 0x1da35),
]

# default to dumping the whole file
for f in FILES:
    if f not in FILE_BLOCKS:
        FILE_BLOCKS[f] = [(0, 0xfffff)]

assert len(FILE_BLOCKS) == len(FILES), "%s %s" % (len(FILE_BLOCKS), len(FILES))