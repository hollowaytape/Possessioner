# TODO
* Can I reliably add another line to some dialogue? The [LN] control code doesn't seem to work.
	* Does each pointer have a number of lines it's expected to read?
* Reinsert and map more files.
	* Just gotta keep playing past the Meryl scene.
* P_HI.MSD is missing a string at 0xdf0 for some reason.
	* もう遅いしね。じゃあ、今日はここで解散
* Hack the intro text to be halfwidth
	* Already have a cursor-increment hack.
	* Also it doesn't display commas/apostrophes correctly?
* Look at .CGX
* More .SEL images to edit
	* A_AR6.SEL - top secret thing that belongs to Nedra?
	* LISTP.SEL - names of possessioners. (If the spellings change, change this too)
	* LM1.SEL-LM7.SEL - description text of possessioners. Definitely gotta translate this
* Any way to change the text speed?
	* Battles display text instantly. Might be nice to get instant text everywhere else
	* Nametags also display instantly...
	* Seems like more of a last-minute thing, but the sooner I do this the more time I'll save!
	* Check out E.V.O. again, since it has a modifiable text speed option. See where that gets written, see what the code does with it.