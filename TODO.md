# TODO
## Script
* Need to revamp some of the verbs. "Behind" is really confusing in the maze
* Strings like "Well then, please be careful out there." have the period overflow out of the window.

## Tools
* Typesetter - what should it do about blank lines?
	* Just setting all blank lines to [BLANK] will make it harder to find missing/unknown context lines.

## Pointers
* Offset-zero pointers still need to be edited, for line count purposes.
	* Corridor: "The only noise is a mechanical" (trails off)
	* Ward: I don't like coming here unless I'm at death's (trails off)
* Need to identify MSD pointer collisions... if there's a string at d7 in two different files, and they think it's the same pointer location, it will get edited twice and be incorrect for one.
	* P_SW1.MSD pointer (d7, 10269) is getting edited incorrectly.
		* Collides with a pointer in P_HON1.
* HI.MSD - Haven't determined the pointer for 0x2ff yet, there are a lot to disambiguate.
* Need to use check_pointers for the rest of the files.
* Need to check for extraneous pointers too.
* Some kind of index-out-of-range error when editing DOCTOR.MSD.

## Hacking
* Look at .CGX
	* Yep, looks hard.
* More .SEL images to edit
	* A_AR6.SEL - top secret thing that belongs to Nedra?
	* LISTP.SEL - names of possessioners. (If the spellings change, change this too)
	* LM1.SEL-LM7.SEL - description text of possessioners. Definitely gotta translate this
		* SEL encoder works on them, good.
* Check if there are uncensored images in the .SEL files.

## Bugs in original version
* You select a target for Meryl's Grenade, but it hits all enemies...
	* Maybe Meryl just likes to fuck shit up