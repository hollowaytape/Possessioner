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
    * To summarize nearby flag operations for one or more files: `python analyze_flag_contexts.py --files POS1.MSD YUMI.MSD`
* To inspect `ff ff ff 01` room/action dispatch headers and map their relative targets back to workbook commands: `python analyze_dispatch_contexts.py --files POS1.MSD YUMI.MSD`
* Add `--json` to `analyze_dispatch_contexts.py` for machine-readable output you can post-process into command-context annotations later.
* To scan the `03 xx 00 01` handoff / event-transition opcode family across `POS.EXE`, label probable destination scene/map IDs from `docs\save_format.txt`, and map nearby text back to workbook commands: `python analyze_handoff_contexts.py`
* Add `--json` to `analyze_handoff_contexts.py` for machine-readable output you can cluster by event type or compare against emulator findings later.
* To scan the `01 xx 00 ff` room-transition opcode family across known `.MSD` script ranges, label destination IDs from `docs\save_format.txt`, and map nearby text back to workbook commands: `python analyze_transition_contexts.py`
* Add `--json` to `analyze_transition_contexts.py` for machine-readable output you can merge with dispatch / handoff / flag snapshots while building a walkthrough graph.
* To merge workbook annotations with dispatch / handoff / room-transition / flag snapshots into one machine-readable trigger model:
    * `python build_trigger_model.py --dispatch-json dispatch_all.json --flags-json flags_all.json --handoffs-json handoffs_all.json --transitions-json transitions_all.json --only-context-rows --output trigger_model.json`
    * This is intended for post-processing and walkthrough-graph work rather than workbook editing.
* To derive block-level nodes and dispatch / handoff / transition edges from the merged trigger model:
    * `python build_state_graph.py --trigger-model trigger_model.json --output state_graph.json`
* To turn the state graph into a walkthrough-readiness / gap outline:
    * `python build_walkthrough_acceptance.py --state-graph state_graph.json --output walkthrough_acceptance.json`
    * This highlights files with strong, partial, or weak current coverage and lists flag-heavy unattached hotspots for future emulator validation.
* To reshape the state graph into a walkthrough-friendly `action -> target -> block/destination` matrix:
    * `python build_command_matrix.py --state-graph state_graph.json --output command_matrix.json`
    * This is useful for seeing which command menus are already understood per file and which files still lack dispatch coverage.
* To annotate `PSSR_dump.xlsx` with text-group, display-context, dispatch, and handoff metadata:
    * Run `python annotate_command_groups.py`
    * This fills `Command Group Label`, `Command Group Start`, `Command Group Size`, `Command Display Type`, `Command Display Detail`, `Command Dispatch Action`, `Command Dispatch Target`, `Command Dispatch Header`, `Command Dispatch Detail`, `Command Handoff Type`, `Command Handoff Destination`, and `Command Handoff Detail` without changing the existing `Command` column.
    * Rows with a manual `?` block but no detected `0x02`, arrival, or direct-range trigger are labeled `no known display path`.
* To build a scratch `POS.EXE` / HDI that changes one `0x02 <ptr> <arg>` text-command byte for debugger testing:
    * List sample cases: `python experiment_text_arg.py --list-samples --limit 10`
    * Patch one known case by file + offset: `python experiment_text_arg.py --file POS1.MSD --text-offset 0x0008a --new-arg 0x03`
    * Patch by explicit pointer location only: `python experiment_text_arg.py --ptr-loc 0x0eb48 --new-arg 0x03`
    * If `patched\POS.EXE` no longer matches the original dump offsets, add `--skip-text-check` to patch the arg byte at the pointer site anyway.
    * Add `--launch --emulator "D:\Code\roms\romtools\np2debug\np21debug_x64.exe"` to boot the scratch HDI in np2debug.
    * By default this now patches the clean `original\POS.EXE` to match the clean source HDI, so a no-op arg change will not silently swap in the debug/patched EXE.
* To build a scratch `POS.EXE` / HDI that changes one `03 xx 00 01` handoff destination byte for emulator testing:
    * List the unique handoff destination bytes currently used: `python experiment_handoff_code.py --source-pos-exe original\POS.EXE --list-destinations`
    * List every handoff site with its current destination byte: `python experiment_handoff_code.py --source-pos-exe original\POS.EXE --list-occurrences`
    * Describe one existing handoff site and its owning workbook command: `python experiment_handoff_code.py --source-pos-exe original\POS.EXE --describe-loc 0x1eafb`
    * Patch one known handoff site: `python experiment_handoff_code.py --handoff-loc 0x1eafb --new-code 0x0f`
    * To test whether the first byte controls battle-vs-transition behavior, patch that byte directly: `python experiment_handoff_code.py --handoff-loc 0x10f46 --new-kind 0x01`
    * For a simpler early-game probe, prefer `0x0eafc` (`POS1.MSD 0x013fc`, `Move - Appearance Site`) over deeper scene-specific sites like `0x1eafb`.
    * Add `--launch --emulator "D:\Code\roms\romtools\np2debug\np21debug_x64.exe"` to boot the scratch HDI in np2debug.
    * By default this now patches the clean `original\POS.EXE` to match the clean source HDI, so a no-op handoff change will not silently swap in the debug/patched EXE.
    * These experiment builds also apply the same instant-text hack as `reinsert.py` (`POS.EXE` edit `0x0a3bf -> a8 03`) to make testing faster.
    * Avoid loading old emulator save states while testing scratch HDIs; states restore RAM from the earlier run and can produce mixed translated/original behavior even when the disk image itself is clean.
* To build a scratch `POS.EXE` / HDI that patches arbitrary `POS.EXE` bytes for cases that do not appear to use the normal handoff family:
    * Patch one raw site directly: `python experiment_pos_bytes.py --patch 0x0f06d:01`
    * Apply multiple raw patches in one build: `python experiment_pos_bytes.py --patch 0x0f06d:01020304 --patch 0x0f084:ff`
    * Add `--dry-run` first to confirm the old/new byte values before writing files.
    * These builds also start from clean `original\POS.EXE`, copy a clean source HDI, and apply the same instant-text hack as the other experiment helpers.
* To automate an emulator route and capture the result:
    * Boot the shared patched image and run one menu pick: `python experiment_emulator_route.py --hdi patched\Possessioner.hdi --load-state 0 --step 1:1 --output route.png --close`
    * Repeat menu picks, e.g. `Talk -> Friends` twice: `python experiment_emulator_route.py --hdi patched\Possessioner.hdi --load-state 0 --step 1:1 --step 1:1 --output route.png --close`
    * Add an inline post-step advance count when a step needs to advance into the next scene before the next action, e.g. `python experiment_emulator_route.py --hdi patched\Possessioner.hdi --load-state 0 --file-index 2 --step 0:0:1 --output route.png --close` for `Move -> first option -> Space`
    * Add `--post-space-count 1` when the game needs an extra `Space` press after all steps to advance from text into the next state.
    * `--post-focus-left-click-count` still exists as a fallback, but `Space` is now the preferred path for those advances.
    * Add `--trace-dir some\folder` to save intermediate screenshots after each step for debugging route drift.

#### Script viewer
* Build the browser viewer dataset:
    * `python build_script_viewer_data.py`
* Open `script_viewer\index.html` in your browser.
* The viewer lets you:
    * browse every `.MSD` row
    * preview lines in a mock ADV window using `screens\adv_scene.png`
    * filter by file, command, speaker, and search text
    * inspect pointer/parser context
    * browse a file-level navigation map built from the state graph
    * explore `action -> target -> block` links from the command matrix
    * inspect a walkthrough-readiness heatmap
    * inspect a per-file block graph with dispatch / flag / transition emphasis
    * inspect flag-gated hotspots by file
    * build route hypotheses from known action/target links and outgoing transitions/handoffs
    * save local draft edits in the browser and export them as JSON for future workbook write-back
