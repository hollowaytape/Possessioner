# TODO

## Re-setting up in 2023
* Check the current state of the game - what works? what doesn't? can text be added?
	* Document the current understanding of the game

## Script
* Need to revamp some of the verbs. "Behind" is really confusing in the maze
* Strings like "Well then, please be careful out there." have the period overflow out of the window.

## Tools
* Typesetter - what should it do about blank lines?
	* Just setting all blank lines to [BLANK] will make it harder to find missing/unknown context lines.
		* But we can still do that for lines that've been typeset, right?

## Pointers
* (?status unknown) Text at offset zero still needs to have its pointers edited, for line count purposes.
	* Corridor: "The only noise is a mechanical" (trails off)
	* Ward: I don't like coming here unless I'm at death's (trails off)
* Need to identify MSD pointer collisions... if there's a string at d7 in two different files, and they think it's the same pointer location, it will get edited twice and be incorrect for one.
	* P_SW1.MSD pointer (d7, 10269) is getting edited incorrectly.
		* Collides with a pointer in P_HON1.
* HI.MSD - Haven't determined the pointer for 0x2ff yet, there are a lot to disambiguate.
* (57 potential problems left) Need to use check_pointers for the rest of the files.
	* Could use some documentation - what is this actually checking?
	* Finds text that multiple pointers are pointing to.
* Need to check for extraneous pointers too.
* (fixed) Some kind of index-out-of-range error when editing DOCTOR.MSD (editing the first line, specifically)
	* Problem occurs when a string is added at 115 or earlier. (text loc 0xf53)
	* There's a pointer in POINTER_DISAMBIGUATION that's greater than the length of the file.
		* Fixed that and added a condition in find_pointers.py to throw an error if so.

### Pointer sheet improvements
* Instead of just showing the first few bytes, see how much we can interpret said bytes. (flag, speaker, beginning of line, command)

## Hacking
* Look at .CGX
	* Yep, looks hard.
* More .SEL images to edit
	* A_AR6.SEL - top secret thing that belongs to Nedra?
	* LM1.SEL-LM7.SEL - description text of possessioners
		* Encoder works fine - wait for real translation, translate those, edit the images, and add them to rominfo.py FILES_TO_REINSERT.
		* LM2.SEL is inserted as a PoC.

## More cheats
* Since I have more of the save file format doc'd, I could probably add a "cheat" to set Save File 1's start location to anywhere I want.

## Bugs in original version
* You select a target for Meryl's Grenade, but it hits all enemies.

## Save files
* 1: HQ after Alisa box
* 2: Maintenance room after Eris
* 3: Junk shop
* 4: Doctor's office (post scene)
* 5: Prim before battle

## Notes
* Battles look a lot like they're soft-locked. They are not! I just have cheats on to make all of the enemies not load. Attack once to win.