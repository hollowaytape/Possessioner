# TODO
## Script
* Corridor: "The only noise is a mechanical" (trails off)
* Ward: I don't like coming here unless I'm at death's (trails off)
* Need to revamp some of the verbs. "Behind" is really confusing in the maze
* Meryl: "(Hmph. I thought this would happen.)(LF)*Sigh*"
	* Where's the LF coming from?

## Tools
* Typesetter - what should it do about blank lines?
	* Just setting all blank lines to [BLANK] will make it harder to find missing/unknown context lines.

## Pointers
* HI.MSD - Haven't determined the pointer for 0x2ff yet, there are a lot to disambiguate.
* Need to use check_pointers for the rest of the files.
* Need to check for extraneous pointers too.

## Hacking
* Look at .CGX
	* Yep, looks hard.
* More .SEL images to edit
	* A_AR6.SEL - top secret thing that belongs to Nedra?
	* LISTP.SEL - names of possessioners. (If the spellings change, change this too)
	* LM1.SEL-LM7.SEL - description text of possessioners. Definitely gotta translate this

## Bugs in original version
* You select a target for Meryl's Grenade, but it hits all enemies...
	* Maybe Meryl just likes to fuck shit up