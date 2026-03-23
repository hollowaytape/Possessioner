# Possessioner repository instructions

## Build, test, and validation commands

- Install Python dependencies with `python -m pip install -r requirements.txt`.
- Put a clean `Possessioner.hdi` in `original\` before running the content pipeline.
- Dump translatable text into `PSSR_dump.xlsx` with `python dump.py`.
- Generate the pointer workbook `PSSR_pointer_dump.xlsx` with `python find_pointers.py`.
- Reflow translated `.MSD` text into the `English (Typeset)` column with `python typeset.py`.
- Encode the hard-coded edited `.SEL` images and copy them into `patched\` with `python sel.py`.
- Reinsert text, image replacements, and binary hacks into `patched\Possessioner.hdi` with `python reinsert.py`.
- Run pointer diagnostics with `python check_pointers.py`.
- There is no dedicated lint configuration or automated test suite in this repository. Validation is script-driven: rerun `python find_pointers.py` and `python check_pointers.py` after pointer-related edits, then test the patched HDI in Neko Project II as described in `README.md`. In this development setup, the emulator executable is `D:\Code\roms\romtools\np2debug\np21debug_x64.exe`.

## High-level architecture

- `rominfo.py` is the central manifest for the whole project. It defines the source/target HDI paths, the canonical file lists, per-file text block ranges, control-code mappings, pointer constants, pointer tables, pointer disambiguation, and manual extra-pointer overrides.
- `dump.py` is the extraction stage. It scans the files listed in `rominfo.py`, decodes Shift-JIS plus game-specific control codes, and creates `PSSR_dump.xlsx` with one worksheet per file.
- Translation happens in `PSSR_dump.xlsx`. The workbook is not just output data; later scripts treat it as a structured database keyed by sheet name and header text.
- `find_pointers.py` is the pointer-discovery stage. It builds `PSSR_pointer_dump.xlsx` by combining regex-based pointer discovery, table scanning, range filters, and the manual overrides in `rominfo.py`.
- For `.MSD` files, the text lives in the `.MSD`, but the pointer data is stored in `POS.EXE`. `find_pointers.py`, `reinsert.py`, and `check_pointers.py` all rely on that split.
- `typeset.py` is a workbook post-processor for translated `.MSD` dialogue. It wraps English text to the game window width, writes the result into `English (Typeset)`, and uses `[LN]` and `[BLANK]` markers to fit multi-line windows.
- `reinsert.py` is the final build step. It loads the dump workbook and pointer workbook through `romtools`, patches executable code in `POS.EXE` and `POSM.EXE`, rewrites text blocks, updates pointers, and writes files back into `patched\Possessioner.hdi`.
- Static image replacements are handled separately from text. `sel.py` encodes selected PNGs from `img\edited\` into `.SEL` files, copies them into `patched\`, and inserts them into the target disk image.
- `docs\notes.txt` and `docs\TODO.md` contain reverse-engineering context that explains many of the assembly hacks and pointer edge cases reflected in the scripts.

## Key conventions

- Treat `rominfo.py` as the single source of truth for game structure. If a text block, pointer range, collision, or manual pointer needs to change, update `rominfo.py` instead of scattering special cases across multiple scripts.
- Do not rename workbook sheets or headers casually. The scripts look up worksheets by filename and depend on literal header names such as `Command`, `Ctrl Codes`, `English`, and `English (Typeset)`.
- Keep the original/patched split intact: `original\` holds the extracted source files and clean HDI, while `patched\` holds generated replacements and the output HDI.
- `.SEL` and `.CGX` files are treated as static asset replacements during reinsertion; `reinsert.py` copies the versions from `patched\` directly into the target disk image.
- `FILES_TO_REINSERT` in `rominfo.py` is currently overwritten to `FILES`, so changing the active subset means editing `rominfo.py` intentionally rather than assuming the earlier partial list is still in effect.
- `typeset.py` mutates the imported `FILES_TO_REINSERT` list in place when it removes `POS.EXE`, `POSM.EXE`, and `POSE.EXE`. Run it as a top-level script; do not assume it is safe to reuse as a library helper.
- `reinsert.py` has intentionally enabled debug/hacking behavior: `MAPPING_MODE = True` appends IDs to untranslated `.MSD` strings, and `CHEATS_ON = True` applies one-hit-kill and instant-text patches for testing. Preserve those flags unless the task explicitly changes gameplay/debug behavior.
- `sel.py` is not a general asset pipeline yet; it only processes the hard-coded filenames in its `__main__` block (`p4.png`, `p5.png`, and `lm2.png`).
- The Python scripts depend on an external `romtools` package/module that is imported throughout the repository but is not vendored here. In this development setup it lives at `D:\Code\roms\romtools`, so tasks that touch dump/reinsert/pointer behavior should assume this sibling checkout is part of the working environment.
- The established troubleshooting loop is: update `rominfo.py` metadata or workbook content, rerun `python find_pointers.py`, rerun `python reinsert.py`, run `python check_pointers.py`, then verify behavior in the emulator.
