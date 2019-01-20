"""
    Replaces the title screen with a GEM image provided as a CL argument.
    Useful for quick viewing, and works better than MLD.
"""

import sys
import os
from shutil import copyfile
from romtools.disk import Disk
from rominfo import TARGET_ROM_PATH

TARGET_ROM_PATH = "DOS 6.2 Bootdisk.hdi"

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Usage: python replace_title.py ImageToView.GEM")
    gem_filename = sys.argv[1]

    # View an image from the FD game
    #gem_filename = os.path.join("original", gem_filename)

    # View an image from the CD game
    #gem_filename = os.path.join("original", "CD", gem_filename)

    # View an edited image
    gem_filename = os.path.join("patched", gem_filename)

    #copyfile(gem_filename, "MENU.CGX")
    copyfile(gem_filename, 'FONT2.SEL')

    #with open("ORTITLE.GEM", 'rb+') as f:
    #    # Red/grey   are between 4000-5000
    #    # Green/blue are between 5000-6000.
    #    N = 0x5504
    #    f.seek(N)
    #    f.write(b'\x00'*(0x8721 - N))

    d = Disk(TARGET_ROM_PATH)
    # d.insert("MENU.CGX", path_in_disk='PSSR')
    d.insert('FONT2.SEL', path_in_disk='MLD')

   #d.insert(gem_filename, path_in_disk='TGL/OR')