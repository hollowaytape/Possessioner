# TODO
* Need a good solution to various POS.EXE pointer related problems, since they'll compound as I add more files
	* POS1.MSD mostly tend to be between eaf6-ee2f.
	* P_BYO: mostly 1a81a-1c000
	* YUMI: Pretty difficult to say
		* Oh right, because text 0-3cf are all in adventure mode and the rest are Yumi scene
		* adv scene: (0xefcc, 0xf06a)
		* Yumi scene: (0x2776e, 0x28aac)
	* P_SE: 0x28700 - 0x291e1?
	* MERYL: (0x1c252, 0x1e10e)
	* So, what I should do is: if there are MULTIPLE pointers to a text location, throw out ones that aren't in the zone.
	That will save some headaches with the random outside pointers that are for differnet kinds of scenes
* P_HON1.MSD has a text thing at 0x1ff, which means it's falsely identified 200 pointers for that location.
* Hilarious Yumi eyelash-fluttering glitch
	* Begins with the line "When I called my friend"
	* See if it's a odd-even glitch.
		* Likely not - it also appears in the unhacked Meryl scene.
* Hack the intro text to be halfwidth
	* Already have a cursor-increment hack.
	* Also it doesn't display punctuation correctly?
* Look at .CGX
* More .SEL images to edit
	* A_AR6.SEL - top secret thing that belongs to Nedra?
	* LISTP.SEL - names of possessioners. (If the spellings change, change this too)
	* LM1.SEL-LM7.SEL - description text of possessioners. Definitely gotta translate this
* Any way to change the text speed?
	* Battles display text instantly. Might be nice to get instant text everywhere else
	* Nametags also display instantly...
	* Seems like more of a last-minute thing, but the sooner I do this the more time I'll save!