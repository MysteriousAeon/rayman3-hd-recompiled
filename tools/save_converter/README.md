# Rayman 3 PC save converter

Converts a save from the original Rayman 3: Hoodlum Havoc PC release (2003) into a save slot of
Rayman 3 HD Recompiled v1.1.0 or v1.2.0 on Windows. One Python 3.8+ file, standard library only, no administrator
rights. It reads only the save files you give it; it contains no game data.

**Status: experimental.** It has been tested with three public PC sample saves (one edited, completed
game), with one real, unedited early-campaign PC save (Bog of Murk, 10 cages), and with the real game. A player has also reported converting their own PC save and continuing to
play (a report; that save was not examined). It has not been tested against a set of unedited PC saves
from different points of the campaign.
Read [Limitations](#limitations) before you use it, and keep a backup of your `profiles` folder.

## Easiest: R3SaveConverter.exe

Double-click `R3SaveConverter.exe` (no Python needed) and follow the dialogs. It asks for the PC `.sav`
and finds the HD slot (installed edition, or the portable folder it sits in or beside), or lets you pick
it. It shows the progress it will import, asks for confirmation, refuses while the game runs, and keeps a
copy of the old slot in `save_converter_backups` (see step 5). Do step 1 below first and back up
`profiles`. For a portable edition, put the exe in the extracted portable folder (the one that contains
`profiles`). From source, build it with `build_exe.bat` (needs `python -m pip install pyinstaller`).

## Use (command line)

1. **In Rayman 3 HD Recompiled, create a save slot:** start a **New Game**, confirm the player name
   (the game saves at that moment), then quit the game. The game also writes the slot's header file;
   the converter needs this slot and never creates one itself.
2. **Find the slot file.** It is in your Rayman 3 HD Recompiled home folder
   (installed: `%LOCALAPPDATA%\Rayman3HDRecomp`; portable: inside the portable folder):

   ```
   profiles\default\user\B13EBABEBABEBABE\5841123F\00000001\<NAME>\<NAME>
   ```

   `<NAME>` is your player name, e.g. `RAY\RAY`. The file has no extension. Leave the `Headers` folder alone.
3. **Back up** the whole `profiles` folder (copy it somewhere safe).
4. **Check the PC save first** (writes nothing):

   ```bat
   python convert.py --input "C:\path\to\your.sav" --dry-run
   ```

   It prints the resume level, cages, scores and life, and refuses files it does not understand.
5. **Convert into the slot** (the game must be closed):

   ```bat
   python convert.py --input "C:\path\to\your.sav" --donor "...\00000001\RAY\RAY" --output "...\00000001\RAY\RAY" --force
   ```

   `--donor` keeps the HD slot's own settings bytes (volumes etc.); no progress is taken from it.
   `--force` is needed because the slot exists. The old slot file is first copied to
   `<home>\save_converter_backups\RAY.bak-<date>-<time>` (the home is the folder that contains
   `profiles`); `--backup-dir` chooses another folder. The backup is never put inside the slot folder:
   the game deletes every unknown file there when it next saves. Without `--force` nothing is overwritten.
   The PC `.sav` is only read, and the slot's header file is not touched.
6. Start the game, choose **Load**, pick the slot. You resume in the level the PC save names.

To inspect any HD slot file (for example after the game saved again):
`python convert.py --input "...\RAY\RAY" --dry-run`. Writing to a new file
(`python convert.py --input your.sav --output converted_RAY`) is for inspection only: copying such a file
into a slot folder you created yourself, without the header file the game writes, is not tested.

## What is converted

Both games store the same save record (same fields, same order, same three data elements). The PC file is
encoded, little-endian and has PC key bindings; the HD file is big-endian and has an extra award-progress
block. Neither has a checksum, so the game cannot detect a bad conversion: the converter checks the record
instead and refuses what it does not recognise.

| Kept exactly | Not converted |
|---|---|
| Resume level, after-revisit level, revisit state | PC key/pad bindings (HD has none) |
| Highest world reached, end-of-game flag | PC options/volumes (different scale; HD settings kept) |
| Cages per world and total, scores per world and total | HD per-area award progress (not in PC saves; starts at zero) |
| Max / current life | |
| All 45 `global save` progression words (includes the cage bitmask) | |
| Autosave-warning flag, Hall-of-Fame key words | |

HD award word 2 (worlds with all cages) is rebuilt from the cage counts. Other HD achievement progress for
per-area goals and bonus maps restarts. Achievements already earned in HD are not touched. With every cage
freed, the game awards the "all cages" achievement on the first play after the import (observed in testing;
expected and harmless).

The tool refuses (writes nothing) when: the file is not a PC save, is already an HD save, or is larger than
64 KiB; it does not decode to a complete record; the data elements differ; the resume level is not an HD
level; cage totals or scores do not add up, exceed a world's maximum, or disagree with the cage bitmask;
revisit fields are invalid. It warns when life differs from the usual rule (40 + 10 per 6 cages) or the
save resumes in revisit mode.

## Limitations

- **Life after playing the first levels.** Converted saves with all 60 cages (life 140, the value the HD
  game itself uses for 60 cages) were played from Intro_10 to Intro_15, once in revisit mode and once not;
  both times the game's own save then had maximum life 40. Whether the game raises it again later, and
  whether the original PC game does the same, is unknown. Saves that resume in later levels were not tested
  for this. The converter itself writes the life values of the PC save unchanged.
- **Revisit mode.** A save that resumes in revisit mode (replaying a world after finishing the game) loads
  and plays; returning from the revisited world to the end of the game has not been tested.
- **Cage-gated bonus content** has not been checked in game with a converted save.
- **Award progress** for per-area goals and bonus maps restarts (see above).
- **PC releases:** only one PC save layout is known; saves from other PC versions or patches are refused if
  they do not match it.

## Tests

`python -I tools/save_converter/test_convert.py` runs the unit tests on synthetic records (no game data
needed). Results recorded for v1.1.0 on Windows, with hidden automated test runs (no visible window, no
desktop input):

- The three public PC samples convert to files that load in game (Intro_10, Moor_00, lept_15).
- A converted save was loaded, Intro_10 was played to its end, and the game wrote its own save at Intro_15.
  That save keeps the cages, cage bitmask, scores, highest world, end-of-game and revisit state and all 45
  `global save` words; a new game process loads it and resumes in Intro_15.
- A real, unedited PC save (Bog of Murk, 10 cages, non-zero scores) converted in place loads, reloads from the
  pause menu, and opens the revisit of Clearleaf Forest and the return to the game, as a genuine HD save at the
  same level does; the game holds the save's cages and scores. A save written by the game afterwards was not
  tested for this save.
- The in-place `--donor ... --output ... --force` flow above was run the same way; the backup outside the
  slot folder survived the game's save, and a file left inside the slot folder was deleted by it.

These game runs used v1.1.0. v1.2.0 keeps the same save format and save locations; a converted save has
not been run separately on v1.2.0.
