# Remix editor example projects (G6-P35, D-291)

Two `r3hd-level-editor-project-v2` projects for the level editor's actor and waypoint remix. They hold edit
declarations only: model keys, instance and node numbers, SHA-256 hashes of the original matrix / waypoint bytes, and
float32 positions. They contain no level data. At export the editor reads your own legally obtained game files,
checks they are the exact supported originals, and compiles the edits with the mod manager's compiler
(`actor-position` / `waypoint-position` overrides).

| File | Level | What it changes | Evidence |
|---|---|---|---|
| `intro10_lums_on_flight_path.r3hdmap.json` | intro_10 | Red lums #1 and #3 moved onto Rayman's flight path | **VERIFIED** (E-523): in a production run each was collected at its new position |
| `intro20_fairy_loop_and_actors.r3hdmap.json` | intro_20 | FairyLight 2's loop (graph C nodes 0 / 3 / 5) reshaped; Chameleon #0, Powerz #1 and Boing2 #11 moved 3 units | Route **SUPPORTED**, actors **PLACEMENT VERIFIED** (E-523): they appeared at and kept their new positions; behaviour there not observed |

Neither example is a complete custom map. The evidence covers these exact items at these exact positions, not other
actors of the same type.

Use: open the file in the editor (File > Open project), then Validate, Export mod folder, and Import + enable. The same
edits are also available as presets (the Presets menu). Regenerate both files from the presets with
`python -I tools/experiments/modding_feasibility/g6p35_playable_check.py examples`; the acceptance check (A3) verifies
the committed bytes match.
