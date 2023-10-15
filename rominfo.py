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

FILES = ['POSM.EXE', 'POS.EXE', 'POS1.MSD', 'YUMI.MSD',
         'P_HON1.MSD', 'P_ROU1.MSD', 'P_SE.MSD', 'P_ENT.MSD',
         'P_BYO.MSD', 'P_HI.MSD', 'P_SW1.MSD', 'MERYL.MSD',
         'P_CITY.MSD', 'P_SYO.MSD', 'P_SUTE.MSD', 'P_KYU.MSD',
         'P_HOU.MSD', 'P_BILL.MSD', 'MISHA.MSD', 'ERIS.MSD', 'P_JUNK.MSD',
         'DOCTOR.MSD', 'P_ENT2.MSD', 'AYAKA.MSD', 'P_GYOTEI.MSD', 'MINS.MSD',
         'PLYM.MSD', 'P_BOX.MSD', 'HONHOA.MSD', 'P_GE.MSD', "RASU1.MSD",
         'RASU2.MSD', 'MAI.MSD', 'ARISA.MSD', 'P_SIRYO.MSD', 'NEDRA1.MSD',
         'NEDRA2.MSD', 'P_7.MSD', 'P_71.MSD', 'TINA.MSD', 'END.MSD',
         'POSE.EXE', "STAFF.TXT",
         'FONT.SEL', 'FONT2.SEL', 'P4.SEL', 'P5.SEL',
         'LM2.SEL',
         #'P_BILL.MLL', 'P_GYOTEI.MSG'
         ]

FILES_TO_REINSERT = ['POS.EXE', 'POSM.EXE', 'POS1.MSD', 'YUMI.MSD', 'P_HON1.MSD',
                     'P_SE.MSD', 'P_ENT.MSD', 'P_BYO.MSD', 'P_SW1.MSD',  'P_ROU1.MSD',
                       'P_HI.MSD', 'MERYL.MSD', 'P_CITY.MSD', 'P_SYO.MSD', 'P_SUTE.MSD',
                     'P_KYU.MSD', 'P_HOU.MSD',
                    'PLYM.MSD',

                     ] #'P_7.MSD',
#                     'P_71.MSD', 'P_BILL.MSD', 'P_BOX.MSD', 'P_GE.MSD', 'P_ENT2.MSD',
#                     'P_GYOTEI.MSD', 'P_JUNK.MSD', 'P_SIRYO.MSD',
#                      'RASU1.MSD', 'RASU2.MSD', 'TINA.MSD', 'ARISA.MSD',
#                     'AYAKA.MSD', 'ERIS.MSD', 'HONHOA.MSD', 'MAI.MSD', 'MINS.MSD',
#                     'MISHA.MSD', 'NEDRA1.MSD', "NEDRA2.MSD", 'DOCTOR.MSD', 'PLYM.MSD',
#                     'END.MSD',]
# .M files have song titles/descriptions in them, probably just internal

FILES_TO_REINSERT = FILES

CONCISE_CONTROL_CODES = {
    b'[White][Alisa][P-Same][Start]': b'[Alisa-Start]',
    b'[White][Alisa][P-Same][Continue]': b'[Alisa-Continue]',
    b'[White][Alisa][P-Al-Neutral][Start]': b'[Alisa-Neutral]',
    b'[White][Alisa][P-Al-Energetic][Start]': b'[Alisa-Energetic]',
    b'[White][Alisa][P-Al-Upset][Start]': b'[Alisa-Upset]',
    b'[White][Alisa][P-Al-Surprised][Start]': b'[Alisa-Surprised]',

    b'[Cyan][Honghua][P-Same][Start]': b'[Honghua-Start]',
    b'[Cyan][Honghua][P-Same][Continue]': b'[Honghua-Continue]',
    b'[Cyan][Honghua][P-Ho-Neutral][Start]': b'[Honghua-Neutral]',
    b'[Cyan][Honghua][P-Ho-Happy][Start]': b'[Honghua-Happy]',
    b'[Cyan][Honghua][P-Ho-Upset][Start]': b'[Honghua-Upset]',
    b'[Cyan][Honghua][P-Ho-Sad][Start]': b'[Honghua-Sad]',

    b'[Green][Meryl][P-Same][Start]': b'[Meryl-Start]',
    b'[Green][Meryl][P-Same][Continue]': b'[Meryl-Continue]',
    b'[Green][Meryl][P-Me-Neutral][Start]': b'[Meryl-Neutral]',
    b'[Green][Meryl][P-Me-Excited][Start]': b'[Meryl-Happy]',
    b'[Green][Meryl][P-Me-Upset][Start]': b'[Meryl-Upset]',
    b'[Green][Meryl][P-Me-Sad][Start]': b'[Meryl-Sad]',

    b'[Purple][Nedra][P-Same][Start]': b'[Nedra-Start]',
    b'[Purple][Nedra][P-Same][Continue]': b'[Nedra-Continue]',
    b'[Purple][Nedra][P-Ne-Neutral][Start]': b'[Nedra-Neutral]',
    b'[Purple][Nedra][P-Ne-Happy][Start]': b'[Nedra-Happy]',
    b'[Purple][Nedra][P-Ne-Upset][Start]': b'[Nedra-Upset]',
    b'[Purple][Nedra][P-Ne-Sad][Start]': b'[Nedra-Sad]',

    b'[Yellow][Kumiko][P-Blue][Start]': b'[Kumiko-Start]',
    b'[Yellow][Kumiko][P-Blue][Continue]': b'[Kumiko-Continue]',

    b'[Green][Eris][P-Blonde][Start]': b'[Eris-Start]',
    b'[Green][Eris][P-Blonde][Continue]': b'[Eris-Continue]',

    b'[Cyan][Deal][P-Brun][Start]': b'[Deal-Start]',
    b'[Cyan][Deal][P-Brun][Continue]': b'[Deal-Continue]',

    b'[Yellow][Yumi][P-Same][Start]': b'[Yumi-Start]',
    b'[Yellow][Yumi][P-Same][Continue]': b'[Yumi-Continue]',
    b'[Yellow][Ayaka][P-Same][Start]': b'[Ayaka-Start]',
    b'[Yellow][Ayaka][P-Same][Continue]': b'[Ayaka-Continue]',
    b'[Yellow][Misha][P-Same][Start]': b'[Misha-Start]',
    b'[Yellow][Misha][P-Same][Continue]': b'[Misha-Continue]',

    b'[Yellow][Prim][P-Same][Start]': b'[Prim-Start]',
    b'[Yellow][Prim][P-Same][Continue': b'[Prim-Continue]',

    b'[White][P-Same][Start][Clear]': b'[Narration]',
    b'[White][Possessioner][P-Same][Start]': b'[Possessioner-White-Start]',
    b'[Cyan][Possessioner][P-Same][Start]': b'[Possessioner-Cyan-Start]',

    b'[Cyan][Mechanic 1][P-Same][Start]': b'[Mechanic1-Start]',
    b'[Cyan][Mechanic 2][P-Same][Start]': b'[Mechanic2-Start]',
    b'[Cyan][Mechanic 3][P-Same][Start]': b'[Mechanic3-Start]',

    b'[Yellow][Doctor][P-Same][Start]': b'[Doc-Start]',
    b'[Yellow][Doctor][P-Same][Continue]': b'[Doc-Continue]',

    b'[Cyan][Passerby 1][P-Same][Start]': b'[Passerby1-Cyan-Start]',
    b'[White[Passerby 1][P-Same][Start]': b'[Passerby1-White-Start]',
    b'[Cyan][Passerby 2][P-Same][Start]': b'[Passerby2-Cyan-Start]',
    b'[White[Passerby 2][P-Same][Start]': b'[Passerby2-White-Start]',
    b'[Cyan][Passerby][P-Same][Start]': b'[Passerby-Start]',

    b'[Cyan][Carmine][P-Same][Start]': b'[Carmine-Start]',
    b'[Cyan][Carmine][P-Same][Continue]': b'[Carmine-Continue]',
    b'[Yellow][Iris][P-Same][Start]': b'[Iris-Start]',
    b'[Yellow][Iris][P-Same][Continue]': b'[Iris-Continue]',

    b'[Yellow][May][P-Same][Start]': b'[May-Start]',
    b'[Yellow][May][P-Same][Continue]': b'[May-Continue]',

    b'[Cyan][Rashmar][P-Same][Start]': b'[Rashmar-Start]',
    b'[Cyan][Rashmar][P-Same][Continue]': b'[Rashmar-Continue]',

    b'[Yellow][Fairy][P-Same][Start]': b'[Fairy-Start]',
    b'[Yellow][Fairy][P-Same][Continue]': b'[Fairy-Continue]',

    b'[Yellow][Tina][P-Same][Start]': b'[Tina-Start]',
    b'[Yellow][Tina][P-Same][Continue]': b'[Tina-Continue]',

    b'[White][Clerk][P-Same][Start]': b'[Clerk-Start]',
    b'[Cyan][Owner][P-Same][Start]': b'[Owner-Start]',
    b'[Cyan][Master][P-Same][Start]': b'[Master-Start]',
    b'[Cyan][Assistant][P-Same][Start]': b'[Assistant-Start]',
    b'[Cyan][Person][P-Same][Start]': b'[Person-Start]',

}

CONTROL_CODES = {
    b'\x0d\xf3': b'[LN]',
    b'': b'[BLANK]',

    b'\x0d': b'[0d]',
    b'\x00': b'[00]',

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
    b'\xf2\x09': b'[Prim]',
    b'\xf2\x0a': b'[Eris]',
    b'\xf2\x0b': b'[Deal]',
    b'\xf2\x0c': b'[Kumiko]',
    b'\xf2\x0d': b'[Message]',
    b'\xf2\x0e': b'[Voice]',
    b'\xf2\x0f': b'[Mechanic 1]',
    b'\xf2\x10': b'[Mechanic 2]',
    b'\xf2\x11': b'[Mechanic 3]',
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
    b'\xf2\x1d': b'[Misha]',
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

    b'\xf3': b'[Clear]',

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
    b'\xf4\x12': b'[P-Brun]',
    b'\xf4\x13': b'[P-Blue]',

    # Text things
    b'\xf5\x00': b'[Start]',
    b'\xf5\x01': b'[Continue]',
    b'\xf5\x02': b'[f502?]',
    b'\xf5\x03': b'[f503?]',

    # Weird quote thing in the intro
    b'\x85\x41': b'[Quote]',
}

inverse_CTRL = {v: k for k, v in CONTROL_CODES.items()}
inverse_CONCISE_CTRL = {v: k for k, v in CONCISE_CONTROL_CODES.items()}


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
        (0x16c22, 0x16c32), # BC 1

        (0x17338, 0x17348),
        (0x17385, 0x17395),
        (0x173d2, 0x173e2),
        (0x1741f, 0x1742f),

        (0x17596, 0x175a6), # BC 1
        (0x175e3, 0x175f3),
        (0x17630, 0x17640),
        (0x17900, 0x17910), # BC 1
        (0x1794d, 0x1795d),
        (0x1799a, 0x179aa),

        (0x17ce1, 0x17cf1), # BC 1
        (0x17d2e, 0x17d3e), # BC 1

        (0x1814a, 0x1815a),
        (0x18380, 0x18390),
        (0x183cd, 0x183dd), # BC 1

        (0x186f8, 0x18708), # BC 1
        (0x18745, 0x18755),
        (0x18792, 0x187a2),
        (0x187df, 0x187ef), # Tina

        (0x18a5b, 0x18a6b), # BC 1
        (0x18aa8, 0x18ab8),
        (0x18af5, 0x18b05),

        (0x18f7c, 0x18f8c), # BC 1
        (0x18fc9, 0x18fd9),

        (0x19016, 0x19026), # Fairy

        (0x23743, 0x23753), # BC 1
        (0x23790, 0x237a0), # BC 2

        (0x2382a, 0x2383a), # Ayaka

        (0x23b9c, 0x23bac), # BC 1
        (0x23be9, 0x23bf9), # BC 2
        (0x23c36, 0x23c46), # Carmine
        (0x23c83, 0x23c93), # Iris

        (0x23eb0, 0x23ec0), # BC1
        (0x23efd, 0x23f0d), # BC2
        (0x23f4a, 0x23f5a), # BC3
        (0x23f97, 0x23fa7), # BC4
        (0x23fe4, 0x23ff4), # BC5

        (0x2442a, 0x2443a), # Empress
        (0x24477, 0x24487), # BC3
        (0x244c4, 0x244d4), # BC1
        (0x24511, 0x24521), # BC2

        (0x24759, 0x24769), # BC1
        (0x247a6, 0x247b6), # BC2
        (0x247f3, 0x24803), # Nedra (o shit spoilers!)

        (0x25747, 0x25757), # BC1
        (0x25794, 0x257a4), # BC2
        (0x257e1, 0x257f1), # BC3

        (0x25c0e, 0x25c1e), # BC1
        (0x25c5b, 0x25c6b), # BC2
        (0x25ca8, 0x25cb8), # BC3
        (0x25cf5, 0x25d05), # BC4
        (0x25d42, 0x25d52), # BC5

        (0x2681e, 0x2682e), # BC1
        (0x2686b, 0x2687b), # BC2
        (0x268b8, 0x268c8), # May
        (0x26905, 0x26915), # BC3

        (0x26d97, 0x26da7), # Rashmar
        (0x26de4, 0x26df4), # BC1
        (0x26e31, 0x26e41), # BC2
        (0x26e7e, 0x26e8e), # BC3

        (0x27f8c, 0x27f9c),
        (0x27fd9, 0x27fe9), # BC2
        (0x28026, 0x28036),
        (0x28073, 0x28083), # Misha
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

    'P_CITY.MSD': 0,  # City
    'P_SYO.MSD': 0,   # Commercial District
    'P_SUTE.MSD': 0,  # "Stella" clothing shop
    'P_KYU.MSD': 0,   # Old Town
    'P_HOU.MSD': 0,   # Abandoned Area
    'P_BILL.MSD': 0,  # Abandoned Building
    'MISHA.MSD': 0,

    'ERIS.MSD': 0,    # Operators
    'P_JUNK.MSD': 0,  # Junk Shop
    'DOCTOR.MSD': 0,
    'P_ENT2.MSD': 0,  # Entrance during Ayaka attack
    'AYAKA.MSD': 0,

    'P_GYOTEI.MSD': 0,  # Communications Point/Temple
    'MINS.MSD': 0,      # Minskys
    'PLYM.MSD': 0,      # Empress

    'P_BOX.MSD': 0,    # Nedra's Box Crisis
    'HONHOA.MSD': 0,
    'P_GE.MSD': 0,     # Sewer Entrance
    'RASU1.MSD': 0,    # Sewer
    'RASU2.MSD': 0,    # More sewer
    'MAI.MSD': 0,

    'ARISA.MSD': 0,    # Fixing the Box
    'P_SIRYO.MSD': 0,  # Data Room/Library
    'NEDRA1.MSD': 0,
    'NEDRA2.MSD': 0,

    'P_7.MSD': 0,      # Tower
    'P_71.MSD': 0,     # Tower, after bullshit maze
    'TINA.MSD': 0,
    'END.MSD': 0,      # Fairy

    'POSE.EXE': 0x9480,
    'STAFF.TXT': 0,

    # Unused?
    'P_BILL.MLL': 0,
    'P_GYOTEI.MSG': 0,
})

MSD_POINTER_RANGES = {
    'POS1.MSD': [                 # Good
        (0xeaf6, 0xee2f)
    ],
    'P_HON1.MSD': [               # Good
        (0xf2fe, 0x10c8e),
    ],
    'YUMI.MSD': [                 # Good
        (0xefcc, 0xf06a),
        (0x27670, 0x28aac)
    ],
    'P_ROU1.MSD': [               # Good
        (0x21061, 0x24000),
    ],
    'P_SE.MSD': [                # Good
        (0x28700, 0x291e1)
    ],
    'P_ENT.MSD': [              # Good
        (0x1b115, 0x1ff00), # This range might be too broad...
    ],
    'P_BYO.MSD': [              # Good
        (0x1a81a, 0x1c000),
    ],
    'P_HI.MSD': [              # Good
        (0x128a2, 0x13d19),
    ],
    'P_SW1.MSD': [
        (0xffc2, 0x10ebe),
    ],
    'MERYL.MSD': [             # Missing 0xdf6, 0x231f
        (0x1c252, 0x1e10e),
    ],
    'P_CITY.MSD': [
        (0x13fb2, 0x16605),
    ],
    'P_SYO.MSD': [            # Missing 0xdbb, 0x1e80
        (0x1f33d, 0x20086),
    ],
    'P_SUTE.MSD': [
        (0x1b2c8, 0x1beba),
    ],
    'P_KYU.MSD': [
        (0x1f761, 0x20e0f),
    ],
    'P_HOU.MSD': [             # Missing 0x69e, 0x1b36, 0x2043, 0x22a3
        (0x2026a, 0x208f5),
    ],
    'P_BILL.MSD': [
        (0x14811, 0x159a8),
        (0x27a2d, 0x28d5c),
    ],
    'MISHA.MSD': [             # Missing 0x1432
        (0x21f50, 0x2231f),
        (0x222a0, 0x224a0,)
    ],
    # 1e40: not found
    'ERIS.MSD': [
        (0x1eaf5, 0x1ef52),
    ],
    'P_JUNK.MSD': [               # Good
        (0x28134, 0x283b8),
    ],
    'DOCTOR.MSD': [             # Missing b5
        (0x118c0, 0x11f90),
    ],
    'P_ENT2.MSD': [
        (0x234a6, 0x238e2),
    ],
    'AYAKA.MSD': [              # Missing 340f (might be mislabeled)
        (0x216b0, 0x21b85),
    ],
    'P_GYOTEI.MSD': [
        (0x22acf, 0x2508b),
        # probably others
    ],
    'MINS.MSD': [            # MIssing 375f, maybe mislabeled?
        (0x1d102, 0x1d6a5),
    ],
    'PLYM.MSD': [                 # Good
        (0x1e7a0, 0x1e7b0),       # Just for 1e51... can that be right?
        (0x20f60, 0x21444),
    ],
    'P_BOX.MSD': [
        (0x25270, 0x25331),
        # probably more
    ],
    'HONHOA.MSD': [
        (0x1d904, 0x1dd9f),
    ],
    'P_GE.MSD': [
        (0x1530a, 0x1553f),
    ],
    'RASU1.MSD': [                  # Good
        (0x253ce, 0x26138),
    ],
    'RASU2.MSD': [                 # Good
        (0x261d4, 0x26d5b),
    ],
    'MAI.MSD': [
        (0x1caaf, 0x1cf30),
    ],
    'ARISA.MSD': [              # Missing 0x324d
        (0x1e455, 0x1ef52),
        (0x209e8, 0x20a53),
    ],
    'P_SIRYO.MSD': [            # Good
        (0x245aa, 0x246e8)
    ],
    'NEDRA1.MSD': [             # Good
        (0x10f30, 0x112ab),
        (0x11630, 0x1164a),
    ],
    'NEDRA2.MSD': [            # Just missing string at 0x854... maybe it is mislabeled
        (0x11282, 0x11ef8),
    ],
    'P_7.MSD': [                 # Good
        (0x15aa2, 0x17559),
    ],
    'P_71.MSD': [                 # Good
        (0x17700, 0x1943a),
    ],
    'TINA.MSD': [                # Good
        (0x121d0, 0x1290b),
        (0x13520, 0x13890),
        (0x12480, 0x12670),
    ],
    'END.MSD': [                # Good
        (0x13115, 0x13dff),
    ],
}

# Plain, continuous pointer tables with no distinguishing prefix/suffix/separator.
POINTER_TABLES = {
    'POS.EXE': [
        (0x88bf, 0x8b03),
        (0xdfab, 0xe00b), # battle things
    ]
}

POINTER_TABLE_SEPARATOR = {
    'POSM.EXE': '\\\\x1e\\\\x0a',
    'POSE.EXE': '\\\\xa8\\\\x08',
}


POINTER_DISAMBIGUATION = [
    # Some text locations have hundreds of possible locations - disambiguate them here
    # (filename, text_location, true_pointer_location)
    # TODO: Would be useful to make sure pointer_location is either none or less than the length of the file (0x2966)
    ('POS1.MSD', 0xe13, 0xed59),
    ('POS1.MSD', 0xdf2, 0x1da35),
    ('POS1.MSD', 0x354, None),
    ('POS1.MSD', 0xfb0, None),
    ('POS1.MSD', 0x123a, None),
    ('P_SIRYO.MSD', 0x1b, None),

    ('YUMI.MSD', 0x40, None),
    ('YUMI.MSD', 0x40f, None),
    ('YUMI.MSD', 0x71c, None),
    ('YUMI.MSD', 0x8bb, 0x277b7),
    ('YUMI.MSD', 0xb40, None),
    ('YUMI.MSD', 0xba0, 0x27826),
    ('YUMI.MSD', 0x11e8, 0x27931),
    ('YUMI.MSD', 0x1d7a, None),
    ('YUMI.MSD', 0x1407, None),

    ('P_SW1.MSD', 0x94, 0x10272),
    ('P_SW1.MSD', 0x1a71, 0x0ffe2),

    ('MERYL.MSD', 0x45f, None),
    ('MERYL.MSD', 0x6f8, None),
    ('MERYL.MSD', 0x152d, 0x1c44f),
    ('MERYL.MSD', 0x1d75, None),
    ('MERYL.MSD', 0x01e60, 0x1c5ce),

    ('P_HON1.MSD', 0xd7, None),
    ('P_HON1.MSD', 0x1ff, 0xf59f),
    ('P_HON1.MSD', 0x1526, None),
    ('P_HON1.MSD', 0x3610, None),
    ('P_HON1.MSD', 0x366c, None),
    ('P_HON1.MSD', 0x12bd, 0xf580),
    ('P_HON1.MSD', 0x1a71, 0xffe2),
    ('P_HON1.MSD', 0x3133, 0xf879),   # or maybe f86c
    ('P_HON1.MSD', 0x3980, 0xf6b7),   # or maybe f6c9

    ('P_HI.MSD', 0x94, None),
    ('P_HI.MSD', 0xe1, None),
    ('P_HI.MSD', 0x221, 0x12937),
    ('P_HI.MSD', 0x2ff, 0x12aa1),  # Really important, there were like 20 0x2ff's
    ('P_HI.MSD', 0xc06, None),
    ('P_HI.MSD', 0xc56, None),
    ('P_HI.MSD', 0xe77, None),
    ('P_HI.MSD', 0x258a, None),
    ('P_HI.MSD', 0x320d, None),
    ('P_HI.MSD', 0x3479, None),
    ('P_HI.MSD', 0x02d02, 0x12a30),

    ('P_SE.MSD', 0x94, 0x2896d),
    ('P_SE.MSD', 0x10e0, 0x28fd2),

    ('P_ENT.MSD', 0x221, None),
    ('P_ENT.MSD', 0x428, None),
    ('P_ENT.MSD', 0x4ad, None),
    ('P_ENT.MSD', 0x2fff, None),
    ('P_ENT.MSD', 0xfd0, 0x1b4fc),
    ('P_ENT.MSD', 0x1350, 0x1ba1d),
    ('P_ENT.MSD', 0x1c81, 0x1ba8e),
    ('P_ENT.MSD', 0x2fff, None),
    ('P_ENT.MSD', 0x2eff, None),
    ('P_ENT.MSD', 0x1b5c, None), # Collision with a pointer to the same location in BYO

    ('P_CITY.MSD', 0x4cf, None),
    ('P_CITY.MSD', 0x204, None),
    ('P_CITY.MSD', 0x647, None),
    ('P_CITY.MSD', 0xf0f, None),
    ('P_CITY.MSD', 0x856, 0x144ed),
    ('P_CITY.MSD', 0x1b9b, None),
    ('P_CITY.MSD', 0x291e, 0x14178),
    ('P_CITY.MSD', 0x2b21, None),
    ('P_CITY.MSD', 0x3043, 0x13fba),
    ('P_CITY.MSD', 0x00bc7, 0x1457b),

    ('P_SYO.MSD', 0x385, None),   # It's normally 385; moving it one up to avoid a text glitch
    ('P_SYO.MSD', 0x83c, 0x1fc6b),
    ('P_SYO.MSD', 0xa3a, 0x1f520),
    ('P_SYO.MSD', 0xc14, 0x1f850),
    ('P_SYO.MSD', 0xb81, 0x1f761),
    ('P_SYO.MSD', 0x12c8, None),
    ('P_SYO.MSD', 0x1a30, 0x1f355),
    ('P_SYO.MSD', 0x8ec, None),

    ('P_BYO.MSD', 0x1e7d, 0x1ad07),

    ('P_BILL.MSD', 0x94, 0x157bd),   # This might just be None
    ('P_BILL.MSD', 0xfd, None),
    ('P_BILL.MSD', 0x25b, 0x157bd),
    ('P_BILL.MSD', 0x585, None),
    ('P_BILL.MSD', 0x6f8, None),
    ('P_BILL.MSD', 0x8c8, None),
    ('P_BILL.MSD', 0xba0, 0x14c69),
    ('P_BILL.MSD', 0xf17, None),
    ('P_BILL.MSD', 0xf69, 0x14ae3),
    ('P_BILL.MSD', 0xfc0, None),
    ('P_BILL.MSD', 0x1017, None),
    ('P_BILL.MSD', 0x1390, 0x150e1),
    ('P_BILL.MSD', 0x1500, 0x151f1),

    ('P_ENT2.MSD', 0x4ff, 0x235f6),


    ('P_7.MSD', 0x994, None),
    ('P_7.MSD', 0x4e20, 0x17299),
    ('P_7.MSD', 0x1b5c, None),
    ('P_7.MSD', 0x1b9b, 0x161c3),

    ('P_END.MSD', 0x33f5, 0x13cb0),

    ('P_71.MSD', 0x742, 0x1788c),
    ('P_71.MSD', 0x8bb, None),
    ('P_71.MSD', 0xc2a, 0x17a98),
    ('P_71.MSD', 0x2673, 0x1a318),
    ('P_71.MSD', 0x33f5, None),
    ('P_71.MSD', 0x3610, 0x1a5ac),

    ('P_BOX.MSD', 0x609, None),
    ('P_BOX.MSD', 0x9f4, None),
    ('P_BOX.MSD', 0xb5c, None),

    ('P_GE.MSD', 0x622, None),
    ('P_GE.MSD', 0xb5c, None),

    ('P_HOU.MSD', 0x4b, None),
    ('P_HOU.MSD', 0x11f5, None),
    ('P_HOU.MSD', 0x234e, 0x208ef),
    ('P_HOU.MSD', 0x742, 0x20297),

    ('P_JUNK.MSD', 0x4ec, None),
    ('P_JUNK.MSD', 0xa64, None),

    ('P_KYU.MSD', 0x370, 0x1fe9f),
    ('P_KYU.MSD', 0x774, 0x2005b),
    ('P_KYU.MSD', 0x8ec, 0x1fc6b),
    ('P_KYU.MSD', 0x00b81, 0x1ff81),
    ('P_KYU.MSD', 0x385, None),
    ('P_KYU.MSD', 0x1035, None),
    ('P_KYU.MSD', 0x2826, 0x201ab),
    ('P_KYU.MSD', 0xc14, 0x20085),
    ('P_KYU.MSD', 0xcea, 0x200a2),
    ('P_KYU.MSD', 0xef6, 0x1fd7b),
    ('P_KYU.MSD', 0x17e6, 0x20104),
    #('P_KYU.MSD', 0x774, 0x2005b), # not sure, this could also be 1fc29

    ('P_SUTE.MSD', 0xfc0, 0x1c1ae), # also not sure, could be 0x157e8
    ('P_SUTE.MSD', 0xf71, None),
    ('P_SUTE.MSD', 0x1164, None),
    #('P_SUTE.MSD', 0x542, 0x1b50a),  # This collides with a pointer in P_ENT. It is the other value, not 1b50a
    ('P_SUTE.MSD', 0x542, 0x1bdeb),
    ('P_SUTE.MSD', 0xafd, None),

    ('ERIS.MSD', 0x4b, 0x1ef0a),
    ('ERIS.MSD', 0xe6f, None),
    ('ERIS.MSD', 0x10e0, 0x1ec52),
    ('ERIS.MSD', 0x11e8, None),
    ('ERIS.MSD', 0x14de, None),
    ('ERIS.MSD', 0x17b9, None),

    ('HONHOA.MSD', 0x4cf, None),
    ('HONHOA.MSD', 0x585, None),
    ('HONHOA.MSD', 0xe6f, None),
    ('HONHOA.MSD', 0x2efa, None),
    ('HONHOA.MSD', 0x324c, None),

    ('MAI.MSD', 0x7a5, None),
    ('MAI.MSD', 0x9f4, None),
    ('MAI.MSD', 0x1a71, None),
    ('MAI.MSD', 0x297c, 0x1ceba),
    ('MAI.MSD', 0x2b82, 0x1cf04),
    ('MAI.MSD', 0x3117, None),

    ('MINS.MSD', 0x1ff, None),
    ('MINS.MSD', 0x741, None),
    ('MINS.MSD', 0x97c, None),
    ('MINS.MSD', 0xe13, None),
    ('MINS.MSD', 0x1680, None),
    ('MINS.MSD', 0x258a, None),
    ('MINS.MSD', 0x326e, None),
    ('MINS.MSD', 0x366c, None),

    ('MISHA.MSD', 0xf69, 0x22118),
    ('MISHA.MSD', 0xfc0, None),
    ('MISHA.MSD', 0x1152, 0x15702),
    ('MISHA.MSD', 0x1301, None),

    ('DOCTOR.MSD', 0x29, 0x118d8),
    ('DOCTOR.MSD', 0xcea, None),
    ('DOCTOR.MSD', 0xf71, 0x11a33),
    ('DOCTOR.MSD', 0x21ad, None),
    ('DOCTOR.MSD', 0x3610, 0x1349b),   # or maybe None

    ('RASU1.MSD', 0x4b, 0x25431),
    ('RASU1.MSD', 0xe2, 0x2544e),
    ('RASU1.MSD', 0x123a, 0x25ae8),
    ('RASU1.MSD', 0x64e, 0x225f2),

    ('RASU2.MSD', 0x2e9, None),  # unsure; points to a Honghua line inculded somewhere already
    ('RASU2.MSD', 0x474, None),
    ('RASU2.MSD', 0xa56, 0x264ca),
    ('RASU2.MSD', 0x1e7d, None),
    ('RASU2.MSD', 0x3117, 0x26d50),

    ('ARISA.MSD', 0x2c3, None),
    ('ARISA.MSD', 0x11e, 0x1e4f1),

    ('TINA.MSD', 0x86a, None),
    ('TINA.MSD', 0xa64, None),
    ('TINA.MSD', 0xbb2, None),
    ('TINA.MSD', 0x2673, None),
    ('TINA.MSD', 0x291e, None),
    ('TINA.MSD', 0x3c54, 0x12688),

    ('END.MSD', 0x20c5, None),
    ('END.MSD', 0x3b56, None),
    ('END.MSD', 0x3b84, 0x13d5a),
    ('END.MSD', 0x4b6f, None),
    ('END.MSD', 0x4dd6, None),

    ('PLYM.MSD', 0x8bb, None),
    ('PLYM.MSD', 0x14de, None),

    ('NEDRA1.MSD', 0x752, 0x10fca),
    ('NEDRA1.MSD', 0x781, None),
    ('NEDRA1.MSD', 0xc56, None),
    ('NEDRA1.MSD', 0xc79, None),
    ('NEDRA1.MSD', 0x1ec6, None),

    ('NEDRA2.MSD', 0x6dd, None),
    ('NEDRA2.MSD', 0x742, None),
    ('NEDRA2.MSD', 0x1390, None),
    ('NEDRA2.MSD', 0x15e4, None),
    ('NEDRA2.MSD', 0x2ca7, None),

    ('AYAKA.MSD', 0x3021, None),
    ('AYAKA.MSD', 0x34fc, None),

    ('P_GYOTEI.MSD', 0x11ab, 0x24f1b),
    ('P_GYOTEI.MSD', 0x11f4, 0x240ef),


    ('P_ROU1.MSD', 0x272, 0x22ac7),
    ('P_ROU1.MSD', 0x34d, None),
    ('P_ROU1.MSD', 0x479, None),
    ('P_ROU1.MSD', 0x8d3, None),
    ('P_ROU1.MSD', 0xa9d, None),
    ('P_ROU1.MSD', 0xfb1, None),
    ('P_ROU1.MSD', 0x2520, None),
    ('P_ROU1.MSD', 0x2730, None),
    ('P_ROU1.MSD', 0x2afc, None),
    ('P_ROU1.MSD', 0x1127, 0x22919),
    ('P_ROU1.MSD', 0x11ab, 0x22b7a),
    ('P_ROU1.MSD', 0x11f4, 0x22b82),
    ('P_ROU1.MSD', 0x14af, 0x22fb9),
    ('P_ROU1.MSD', 0x1e0f, 0x23043),
    ('P_ROU1.MSD', 0x216d, 0x22a19),
    ('P_ROU1.MSD', 0x2385, 0x22c31),

    #('P_SE.MSD', 0x10e0, None),
    ('P_SE.MSD', 0x22f0, None),
    ('P_SE.MSD', 0xef8, 0x1b394),

    ('P_ENT.MSD', 0x683, 0x1b5f8),
    ('P_ENT.MSD', 0x542, 0x1b50a),
    ('P_ENT.MSD', 0xa56, 0x1b9e1),
    ('P_ENT.MSD', 0x01b5c, 0x1b115),
    ('P_ENT.MSD', 0x02141, 0x1b7c3),
    ('P_ENT.MSD', 0x86a, None),
    ('P_ENT.MSD', 0xc64, None),
    ('P_ENT.MSD', 0xef8, 0x1b394),
    ('P_ENT.MSD', 0x10f7, None),
    ('P_ENT.MSD', 0x1494, None),
    ('P_ENT.MSD', 0x22a6, None),
    ('P_ENT.MSD', 0x282a, None),
    ('P_ENT.MSD', 0x3f34, None),
    ('P_ENT.MSD', 0xb5c, 0x1c11b),
    ('P_ENT.MSD', 0xf89, 0x1b4f4),
    ('P_ENT.MSD', 0x2a92, 0x1b365),

    ('P_BYO.MSD', 0x41e, None),
    ('P_BYO.MSD', 0x60b, None),
    ('P_BYO.MSD', 0x83a, 0x1ae27),
    ('P_BYO.MSD', 0xb5c, 0x1bf8f),
    ('P_BYO.MSD', 0xfb0, None),
    ('P_BYO.MSD', 0x1b5c, 0x1b115),
    ('P_BYO.MSD', 0x24c2, 0x1acd8),
    ('P_BYO.MSD', 0x2673, None),
    ('P_BYO.MSD', 0x83a, 0x1ae27),
    ('P_BYO.MSD', 0x0258a, 0x1acdd),
    #('P_BYO.MSD', 0xb5c, 0x1ae27),   # Either 0x1bf8f or 0x1c11b


    # NEDRA1 is missing 0x752 (ptr at 10fca), 
]

# TODO: What are these??
EXTRA_POINTERS = {
    'END.MSD': [
        (0x3b84, 0x13d5a),
    ],

    'P_SYO.MSD': [
        (0x386, 0x1f788),
    ],

    'P_BYO.MSD': [
        # Added this in 2023, might be wrong)
        (0x1f2f, 0x12e4c), 
    ],

    #'AYAKA.MSD': [
    #    (0x50c, 0x216b9),
    #]
}

# Hard-coded pointers for when offset ix 0.
# The pointer location is 2 before the line-count position, so it can be used with normal pointer tools.
ARRIVAL_POINTERS = {
    'P_CITY.MSD': [
        (0x0, 0x26fa9),
    ],

    'P_SE.MSD': [
        (0x0, 0x291fa),   # Doesn't need to be changed, but I am aware of its location
    ],

    'P_HI.MSD': [
        (0x0, 0x13667), # Incorrect maybe? Doesn't need to change though
    ],

    'P_ENT.MSD': [
        (0x00, 0x1c130), # Also ok (overlaps with P_JUNK, it's probably wrong)
    ],

    'P_BYO.MSD': [
        (0x00, 0x291fa),
    ],

    'P_JUNK.MSD': [
        (0x00, 0x286b7)  # at 44fb8  (offset is 1c901?)
    ],

    'P_ERIS.MSD': [
        (0x00, 0x20ac2)      # 3d3c3
    ],

    'P_SYO.MSD': [
        (0x00, 0x20c33)
    ],

    # something - 3fd43, 41636, 38ab0, 41636, (crash)

    # 4181d - malformed text in Gyotei

    # 35ea4 - malformed text in P_7

    # 360bc - something else in P_7

    # 36d71 - P_7, Meryl and Honghua get one line each

    # P_ENT - 38a31

    # Ayaka attack - 41176
}

# Wow, I don't know what this means anymore
SKIP_TARGET_AREAS ={
    'YUMI.MSD': [
        0x17,
        0x40
    ],

    #'NEDRA1.MSD': [0x29,],

    'NEDRA2.MSD': [ 0x81,],

    'ARISA.MSD': [0xe1, ],

    'AYAKA.MSD': [0x45f, ],

    'END.MSD': [0x19, 0x609,],

    'TINA.MSD': [0x43, ],
}

# Name locations, used for locating their stats (for cheats)
ENEMY_NAME_LOCATIONS = [
    0x0f0ac,
    0x0f0f9,
    0x0f146,
    0x0f193,
    0x162a4,
    0x162f1,
    0x1633e,
    0x1638b,
    0x166b3,
    0x16700,
    0x1674d,
    0x1679a,
    0x16c22,
    0x17338,
    0x17385,
    0x173d2,
    0x1741f,
    0x17596,
    0x175e3,
    0x17630,
    0x17900,
    0x1794d,
    0x1799a,
    0x17ce1,
    0x17d2e,
    0x1814a,
    0x18380,
    0x183cd,
    0x186f8,
    0x18745,
    0x18792,
    0x187df,
    0x18a5b,
    0x18aa8,
    0x18af5,
    0x18f7c,
    0x18fc9,
    0x19016,
    0x23743,
    0x23790,
    0x2382a,
    0x23b9c,
    0x23be9,
    0x23c36,
    0x23c83,
    0x23eb0,
    0x23efd,
    0x23f4a,
    0x23f97,
    0x23fe4,
    0x2442a,
    0x24477,
    0x244c4,
    0x24511,
    0x24759,
    0x247a6,
    0x247f3,
    0x25747,
    0x25794,
    0x257e1,
    0x25c0e,
    0x25c5b,
    0x25ca8,
    0x25cf5,
    0x25d42,
    0x2681e,
    0x2686b,
    0x268b8,
    0x26905,
    0x26d97,
    0x26de4,
    0x26e31,
    0x26e7e,
    0x27f8c,
    0x27fd9,
    0x28026,
    0x28073
]

# If blocks not defined, just dump the whole file
for f in FILES:
    if f not in FILE_BLOCKS:
        FILE_BLOCKS[f] = [(0, 0xfffff)]

assert len(FILE_BLOCKS) == len(FILES), "%s %s" % (len(FILE_BLOCKS), len(FILES))