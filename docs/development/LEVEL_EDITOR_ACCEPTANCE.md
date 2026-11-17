# Level Remix Editor: manual Windows acceptance checklist (G6-P36 release candidate)

Automated checks drive the packaged editor with its window hidden (E-520, E-525). These steps need a person at the
desktop and the private candidate in `private\work\e525\candidate` (setup and portable ZIP of the same stage). They
take about 25 minutes. Only steps 13 and R8 start the game, and only if you choose to.

Install the candidate setup into a new folder (or extract the portable ZIP into a new folder and use its `.cmd` files).
Do not set `R3HD_DEV_STRUCTURAL_TX`.

| # | Do | Expect |
|---|---|---|
| 1 | Start menu **Rayman 3 HD Recompiled - Level Editor** (portable: `Level Editor.cmd`) | No console window stays open. One window titled `Level Remix Editor - unsaved project`. No focus jumps after it opens. |
| 2 | Also open Settings > Mods and click **Level editor...** | A second editor window opens; the status line in Settings says it is opening. Close that second editor. |
| 3 | Look at the map | The intro_20 floor in slate-to-sand shading. Green circles v0 / v2 / v4 / v6, magenta loop C0-C5, cyan graph A, violet graph B, a yellow diamond and two red crosses. Grid labels at the edges. |
| 4 | **Help > What can this editor change?** | A text that starts "Level Remix Editor": the existing levels intro_10, intro_15 and intro_20, no new levels or maps; no new achievements while such a mod is on; then the intro_20 patch limits (start floor + graph A production-supported; graph B and moved graph C waypoints development-only) and the remix limits (EXPERIMENTAL / LOCKED). |
| 5 | Wheel over the map; drag empty space; switch **Side (X-Z)** with height x20 | Zoom follows the cursor; the map pans; the side view is readable. |
| 6 | Click v6, move the slider, click "Lower 0.01" | v6 turns orange with a label like `v6 -0.15`; its triangles get orange outlines; the title gains `*`. Status **PRODUCTION-SUPPORTED** (green). |
| 7 | Drag waypoint C3 | The loop bends; status turns amber **DEVELOPMENT-ONLY**. Press `Del`: C3 returns, status green again. |
| 8 | Choose graph B, then graph A | B: DEVELOPMENT-ONLY. A: PRODUCTION-SUPPORTED. |
| 9 | Choose graph B and click **Validate** | A red refusal explaining that the content is development-only. Choose graph A again. |
| 10 | Click **Validate** | A green VALID line with a transaction id and "Production-supported content". |
| 11 | **File > Save project as...**, close the editor, start it again from the Start menu, **File > Open project...** | The same edits, with no `*`. |
| 12 | **Export mod...** to a new empty folder, then **Import + enable mod...** with that folder | "EXPORTED ... NOT imported or enabled yet", then "IMPORTED and ENABLED in ...\mods". Settings > Mods lists the mod, on. |
| 13 | Optional: Play | The game starts with the modified start floor in intro_20 (the floor near the start is slightly lower). Exit normally. |
| 14 | Close the editor with unsaved changes; start it again | Closing asks whether to discard; the relaunch opens normally. |
| 15 | Installer only: with the editor still open, run **Rayman 3 HD Recompiled - Uninstall** | Refused: "cannot be uninstalled right now ... The Rayman 3 HD Level Editor is open". Nothing is removed and the editor stays open. |
| 16 | Optional: close the editor; Settings > Mods > Remove the mod; uninstall (or delete the portable folder) | The mod is gone; uninstall keeps saves and settings as before. |
| 17 | Settings > Mods at 150 % display scaling (if available) | The page fits without a scroll bar; the seven buttons on the right have one size; the details box shows five lines and scrolls. |

Remix mode (G6-P33 / G6-P35). The G6-P36 candidate contains this editor.

| # | Do | Expect |
|---|---|---|
| R1 | Selector: **intro_15 - actor and waypoint remix** | The whole intro_15 collision, shaded by height. Yellow circles (experimental actors), magenta graphs with arrows. The level box shows its counts and hashes. |
| R2 | Tick **locked actors**; click a grey circle | The inspector shows LOCKED and the reason. No position controls. |
| R3 | Find "Lums" (or any yellow actor); select it in the list | The map zooms to it. The inspector shows EXPERIMENTAL with the original and proposed positions. |
| R4 | Drag it; then type a Z value and **Apply position**; then `Del` | It follows the mouse along the view's axes, with a dashed line back to the hollow original. Z changes. `Del` returns it. |
| R5 | Drag a waypoint far away | It stops at 6 units. Its graph's arrows follow, and the original edges show dashed. |
| R6 | **intro_10 - actor and waypoint remix**: find NIN_m_Lums_Int10 #0 | Green (VERIFIED). |
| R7 | Save as, reopen, Validate, Export mod..., Import + enable mod... | Same edits. VALID with N ranges. Exported, then imported and enabled; Settings > Mods lists it, marked as changing game logic. |
| R8 | Optional: Play intro_10 / intro_15 | Moved items appear at their new places. Report what happens to EXPERIMENTAL items. |
| R9 | G6-P35: intro_20 remix, select YAM_mPowerz #1, nudge X+ a few times, **Snap to ground: preview**, then **Apply snap**, then `Ctrl+Z` | The ground line reads GROUND BELOW with a height. The preview shows a cyan cross and a Z change, without moving the actor. Apply moves it; Ctrl+Z puts it back. |
| R10 | Select a lum in intro_10 and press **Snap to ground: preview** | Refused (NO_REFERENCE: the original floats); Apply stays disabled. |
| R11 | Presets > intro_20 graph C reshape; Route list: FairyLight #2 var 2 | Three nodes are marked moved; the original loop is dashed; the panel says "Followed by: original FairyLight instance 2" and ROUTE SUPPORTED. **Revert whole route** removes the edits. |
| R12 | Presets > intro_20: Chameleon #0, Powerz #1 and Boing2 #11 moved 3 units (the packaged form of the intro_20 example project); Validate | VALID, then advisory warnings listed after the compiler output. |

Report any step that differs, with a screenshot if you want. Record the result in CURRENT_TASK.md.

From a repository checkout the same editor starts with `python -I tools\r3hd_level_editor.py` (game data in
`private\extracted\5841123F`, or **File > Game data folder...**).
