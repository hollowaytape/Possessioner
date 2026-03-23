## Possessioner
* Translation and hacking notes for Queen Soft's Possessioner, a visual novel/adventure/RPG for the PC-98.

### How to use
#### Pre-requisites
* Place your copy of Possessioner.hdi `original\` subfolder.
* `pip install requirements.txt`
* Dump the game script into an Excel sheet:
    * `python dump.py`
    * `python find_pointers.py`

#### Translating the game
* Translate the game by filling out the "English" column of each sheet.
* Edit the extracted images in `img\original` subfolder.

#### Reinserting the text
* Properly typeset all new text, and get warnings of any that overflow:
    * `python typeset.py` 
* Encode the edited images:
    * `python sel.py`
* Reinsert all translated/typesetted text:
    * `python reinsert.py`
* Test the game with Neko Project II.

#### Troubleshooting
* Issues usually have to do with pointers!
    * Run `python check_pointers.py`
    * Adjust pointer/text locations in `rominfo.py` based on what has gone wrong.
* To inspect `.MSD` dialog rows together with nearby `POS.EXE` pointer-command bytes:
    * Human-readable explanation for one row: `python analyze_msd_context.py --file P_HON1.MSD --offset 0x00163 --human`
    * JSON for one row: `python analyze_msd_context.py --file P_HON1.MSD --offset 0x00163 --pretty`
    * For a full JSON dump: `python analyze_msd_context.py --output msd_context.json`

#### Script viewer
* Build the browser viewer dataset:
    * `python build_script_viewer_data.py`
* Open `script_viewer\index.html` in your browser.
* The viewer lets you:
    * browse every `.MSD` row
    * preview lines in a mock ADV window using `screens\adv_scene.png`
    * filter by file, command, speaker, and search text
    * inspect pointer/parser context
    * save local draft edits in the browser and export them as JSON for future workbook write-back
