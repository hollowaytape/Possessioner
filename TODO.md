# TODO
* Need to revamp some of the verbs. "Behind" is really confusing in the maze
* Can I reliably add another line to some dialogue? The [LN] control code doesn't seem to work.
	* Does each pointer have a number of lines it's expected to read?
		* Seems like it... I should be harvesting pointers and filling in the ?s with that.
		* I also would need to keep that in mind for the reinserter if I want to change the number of lines...
* Hack the intro text to be halfwidth
	* Already have a cursor-increment hack described in notes.txt.
	* Also it doesn't display commas/apostrophes correctly?
* Look at .CGX
* More .SEL images to edit
	* A_AR6.SEL - top secret thing that belongs to Nedra?
	* LISTP.SEL - names of possessioners. (If the spellings change, change this too)
	* LM1.SEL-LM7.SEL - description text of possessioners. Definitely gotta translate this
* I think my model might have some problems if pointers can point to the middle of a string...
	* Currently those pointers aren't getting picked up. 
	* How about if I just remove the pointer_lines thing entirely?
	* This seems good. Use check_pointers.py to figure out which important strings are missing.
	* Also need to look for extraneous pointers at some point.

## Bugs in original version
* You select a target for Meryl's Grenade, but it hits all enemies...
	* Maybe Meryl just likes to fuck shit up