# Level-patch authoring (private, development only)

This guide covers the private `level-patch-v1` workflow in `tools/r3hd_mods.py` (D-277 / D-278 / D-280 / D-284). It is a
developer tool for this repository. It is **not** a public mod format, a custom-map editor, or part of any release
or public export.

## 1. What it supports today

One declaration changes one level, `intro_20`. It always holds the two required components below and may add one
optional `route` component (G6-P28):

| Component | What you can choose | Fixed by the tool |
|---|---|---|
| `terrain` | Either the verified preset `start-two-step-v1`, or an embedded `terrain-patch-v1` for region `start-floor-v1` or `start-floor-v2`. In `start-floor-v1` the patch has 2–3 named groups of collision vertices **0, 2, 4**. `start-floor-v2` (G6-P25) adds vertex **6**, the west pit-floor corner, with 2–4 groups. Each group has one `delta_z` from **−0.30 to −0.05** (lowering only); vertex 6 is limited to −0.20. | Each vertex's visual twin, every derived normal and scalar, and the octree and bounds checks |
| `fairylight` | `follow_graph_of`: **0 = graph A**, **1 = graph B** | The source FairyLight (instance 2) and the copy's construction |
| `route` (optional) | 1–6 moves of **graph C**, the loop the original FairyLight instance 2 flies: each move is a `node` (0–5) and an `offset` `[dx, dy, dz]` of at most **6 units** | The graph, its nodes, radius and flags, and the transaction merge |

The tool compiles all components into **one atomic version-2 level transaction**. The guest applies all of it or
none of it.

Nothing else can be expressed: no other levels, vertices, regions, actors, graphs, new graph nodes, file offsets or
addresses.

## 1a. Visual editor (G6-P29)

The same workflow has a visual editor. You don't need to edit JSON:

```powershell
python -I tools\r3hd_level_editor.py [my_map.r3hdmap.json] [--game-dir DIR] [--home INSTALLATION]
```

**Packaged (G6-P31, D-287).** The installer and the portable ZIP ship the editor with the Tk runtime of the bundled
CPython 3.11.4. All entries run `app\r3hd_launcher.exe --level-editor`, which starts
`app\python\pythonw.exe -B app\tools\r3hd_level_editor.py --home HOME`:
- the Start menu item **Rayman 3 HD Recompiled - Level Editor**;
- **Level editor...** on Settings > Mods;
- `Level Editor.cmd` in the portable folder.

With `--home`, the game data is `HOME\data\content` and mods go to `HOME\mods`. This is the mod manager's own
resolution.

**Production policy (G6-P30, D-286).** Some content needs no development variable:

- **Production-supported:** start-floor terrain plus the inserted FairyLight on graph A. It validates, exports,
  imports (**Import + enable mod...**) and runs on a production game build.
- **Development-only:** a graph C route or graph B. The editor labels it as such, and the production game refuses it.
  Validating or exporting it needs `R3HD_DEV_STRUCTURAL_TX=intro_20`, and running it needs a development runtime
  build.

The production runtime checks the content itself:
- the pinned `.ptr` / `transit.lvl` results;
- the FairyLight-A base image of the `.lvl`;
- 22 terrain windows, with every word in them bounded.

A plan that is merely labelled as production content is not enough.

- **Map.** The map shows the intro_20 static collision decoded from your files. Views: top, side X-Z and side Y-Z,
  with a grid and an exaggeration control for side-view heights. Wheel zooms, dragging empty space pans, `F` zooms to
  the selection.
- **Terrain.** Green circles are the editable terrain vertices of the chosen region; grey dots are not editable. Click
  one and use the slider. Lower at least 2 vertices: the format needs 2 or more terrain groups, and the editor makes
  one group per vertex.
- **Route.** Magenta circles are graph C. Drag one, or type dX / dY / dZ (at most 6 units).
- **FairyLight.** Choose graph A or B for the inserted FairyLight.
- **Projects.** File > Save writes an editable project (`r3hd-level-editor-project-v1`, no game data). **Validate**
  runs the compiler's `--check`. **Export mod...** writes `mod.json` into a new folder. **Import + enable mod...**
  hands that folder to the mod manager. The game applies enabled mods at its next start.

## 1b. Actor and waypoint remix (G6-P33, D-289)

Choose **intro_10 / intro_15 / intro_20 - actor and waypoint remix** in the selector at the top right. One project
(`r3hd-level-editor-project-v2`) holds one level; make a separate project for each level.

- **Map.** The level's whole static collision, read-only. It is shaded by height in the top view. Actors are circles
  and waypoints are squares; arcs are drawn as arrows. Layer toggles hide collision, actors, locked actors or graphs.
  **Find** lists actors and graphs; tick "editable only" to hide locked ones.
- **Status.** Each item is one of:
  - **VERIFIED** (green): runtime evidence exists. That is the intro_10 lum #0 (E-461) and the intro_10 flight graph
    (E-464).
  - **EXPERIMENTAL** (yellow): the compiler accepts the edit byte for byte, but nobody has measured how the item
    behaves at its new position.
  - **LOCKED** (grey): the item cannot move. The inspector says why, for example "the model's scripts set the
    position".
- **Editing.** Drag an item in any view, type X / Y / Z, or nudge it by the step. Actors move at most 25 units and
  waypoints at most 6 units from their original positions; these are the largest moves with runtime evidence. `Del`
  reverts the selected item, and `Ctrl+Z` undoes.
- **Export.** **Validate** and **Export mod...** run the mod manager's own compiler (`actor-position` /
  `waypoint-position` overrides) and produce the same `mod.json` from the same project every time. The mod is
  production-compatible: it is made of same-size in-place ranges with no level transaction. It is marked as changing
  game logic, so the game records no new achievements while it is enabled.
- **Limits.**
  - No new actors, rotation, new waypoints or arcs.
  - The terrain and FairyLight of intro_20 stay in the level-patch mode, as a separate project and a separate mod.
    The mod manager accepts both mods together when their bytes do not overlap; no editable remix item overlaps the
    production intro_20 transaction. That combination has not been run in the game.

G6-P34 (D-290) added two statuses: **PLACEMENT VERIFIED** (the item appeared at and kept its new position in a
production run; behaviour there not observed) and **ROUTE SUPPORTED** (graph C: the follower reached the moved
waypoints, but the pre-registered judgement was not fully met). G6-P34 ran the intro_20 terrain + remix combination
once; it is SUPPORTED, not verified.

## 1c. Placement help, presets and routes (G6-P35, D-291)

- **Ground readout.** For the selected actor or waypoint, the inspector reports what the level's static collision
  shows under the proposed position. It also reports the same for the original position. The four states:
  - **GROUND BELOW**: the height above the surface below.
  - **AMBIGUOUS (stacked surfaces)**: two or more surfaces lie within 4 units below or 1 unit above.
  - **UNDER A SURFACE**: there is a surface above the point and none below it.
  - **NO SURFACE FOUND**: no known collision at this x / y. This is not a safety verdict: flying content and
    script-placed geometry are normal here.

  The readout is a geometric prediction from static collision only. Triangle orientation is not trusted, and dynamic
  platforms and terrain-patch heights are not included.
- **Snap to ground.**
  - **Preview** proposes a new Z and draws it on the map (cyan cross). **Apply snap** sets it; `Ctrl+Z` undoes it.
  - The snap keeps x / y and puts the item at the same height above the new ground as the original had above its
    own. The editor does not know whether an actor's origin is at its feet or its centre.
  - It refuses rather than guessing:
    - `NO_REFERENCE`: the original is not standing on a single surface.
    - `NO_SURFACE`: no surface within reach.
    - `AMBIGUOUS`: stacked floors.
    - `STEEP`: the surface's normal z is below 0.7.
    - `BLOCKED`: the snapped height lands in a different stack of surfaces.
    - `OUT_OF_BOUND`: the snapped point would exceed the 25 / 6-unit bound. Nothing is clamped.
- **Typed positions** beyond the bound are refused and left unchanged; they are not pulled back. Dragging still stops
  at the bound.
- **Presets** (the Presets menu). Each preset holds edits taken from accepted runtime evidence, and each states its
  evidence limit:
  - intro_10 lums #1 / #3 on the flight path: VERIFIED.
  - intro_10 flight node 13: VERIFIED.
  - intro_20 graph C reshape: ROUTE SUPPORTED.
  - intro_20 Chameleon / Powerz / Boing2 moves: PLACEMENT VERIFIED.
  - intro_20 west-basin terrain + FairyLight: the production level patch.

  Presets go through the same checks and compiler as manual edits. Example projects are in
  `tools/experiments/modding_feasibility/remix_examples/`.
- **Routes.** The **Route** list names every graph of the level with its status. Selecting a graph or one of its
  waypoints shows:
  - where the graph is stored (the actor and designer variable);
  - who is measured following it, or **UNKNOWN**;
  - the waypoint sequence (for example `0 -> 1 -> ... -> 5 -> 0`);
  - a node list with each node's move.

  The selected route is drawn thick, with its original drawn dashed. Use **Zoom to route**, **Revert this waypoint**
  or **Revert whole route** (undoable). Only waypoint positions are edited. Node insertion stays a development-only
  level transaction.
- **Warnings.** **Validate** prints the compiler's verdict first. Advisory warnings follow it:
  - moved away from any known collision;
  - under a surface;
  - stacked surfaces;
  - a move above 80 % of its bound;
  - behaviour unverified;
  - a route with no measured follower;
  - graph C only SUPPORTED.

  Warnings never change what the compiler accepts. A refusal shows the compiler's own reason.

## 2. What you need

- Your own legally obtained Xbox 360 HD files, extracted to the repository layout (`private/extracted/5841123F`) or
  given with `--game-dir`. The tool reads `GAMEDATAbin/.../intro_20.lvl`, `intro_20.ptr` and `transit.lvl`.
- The exact original files. Their SHA-256 must match the values in the examples (`lvl` `a21aa769…`, `ptr`
  `be90b58a…`, `transit` `51c0fbf1…`). Any other version is refused.
- For development-only content (graph B, routes): `R3HD_DEV_STRUCTURAL_TX=intro_20` in the shell that runs the tool.
  Without it, such a patch is refused and nothing is written. Production-policy patches (D-286) need nothing.
- To run the result in the game:
  - production-policy content runs on a production build that contains the G6-P30 overlay;
  - development-only content needs a development runtime build. Building and running it are separate,
    protocol-governed steps (AGENT_WORKFLOWS / the G6 reports).

## 3. Examples

They are in `tools/experiments/modding_feasibility/level_patch_examples/`:

| File | Terrain | Graph | Runtime status of its exact guest images |
|---|---|---|---|
| `g6p22_west_dip_fairy.json` | authored `west-dip` (0: −0.10, 2: −0.25, 4: −0.20) | A | observed (G6-P23 run m1, settled z −25.1415) |
| `g6p22_reference_patch.json` | `start-two-step-v1` written as a patch | A | observed (G6-P20 run m1) |
| `g6p20_reference.json` | preset `start-two-step-v1` | A | observed (G6-P20 run m1) |
| `graph_b.json` | preset `start-two-step-v1` | B | untested (offline only) |
| `g6p25_west_basin_fairy.json` | `west-basin`, region `start-floor-v2` (6: −0.20, 2 / 4: −0.15) | A | observed (G6-P27 run m1, settled z −25.3972 on the west floor) |
| `g6p28_fairy_route.json` | `west-basin` + route: graph C nodes 0 / 3 / 5 moved 5.4 / 5.8 / 5.0 units | A | untested (offline only) |

Copy one of them. Never edit the checked-in examples in place:

```powershell
Copy-Item tools\experiments\modding_feasibility\level_patch_examples\g6p22_west_dip_fairy.json private\work\my_patch.json
```

In the copy, change `id` (lower case, `a-z 0-9 . _ -`). It becomes the mod id. Keep the three `*_sha256` values,
`format` and `level` unchanged. Set `region` to `start-floor-v2` only if you need vertex 6.

## 4. Changing the terrain

Under `components[].patch.groups`:

- Each group has a unique `name`, a `vertices` list and one `delta_z`.
- Use 2 or 3 groups. Each of vertices 0, 2 and 4 may appear in at most one group. A vertex left out stays where it is.
- `delta_z` must be from −0.30 to −0.05. Positive values (raising) are refused.
- Vertex 6 (region `start-floor-v2` only) is the west corner of the pit floor. It shapes the ramp from the floor up
  to the west rim (collision triangle 1/2, which `start-floor-v1` cannot edit) and the floor triangles 1/3 and 1/4.
  It is limited to −0.05..−0.20: below about −0.24, a neighbouring edge reaches a scalar case whose game rule is
  unknown. It does not change Rayman's start height. The west floor has a second measured witness (G6-P26: Rayman
  walked there and stood at z −25.2122 on the unmodified level, exactly on the predicted plane). The preview's
  `west floor` line predicts the height there for your values. That prediction is not a measurement of your edit.
- Vertex 0 is the corner under Rayman's start. Vertices 2 and 4 are the floor west of it. Rayman's recorded standing
  point is on a collision triangle (1/11) whose region vertex is vertex 0. So only `delta_z` of vertex 0 changes
  his predicted standing height (about 0.63 × its `delta_z`). Vertices 2 and 4 reshape the floor around him. The
  preview shows the predicted height and which of your moved vertices sets it.

## 5. Choosing the FairyLight graph

Set `"follow_graph_of": 0` (graph A) or `1` (graph B) in the `fairylight` component. Graph A with terrain has run in
the guest. Graph B with terrain is offline-verified only.

## 5a. Reshaping graph C (optional `route`)

```json
{"type": "route", "waypoints": [{"node": 0, "offset": [-4.0, -3.0, -2.0]},
                                 {"node": 3, "offset": [0.0, -5.0, 3.0]}]}
```

- Graph C is the six-waypoint loop (0 → 1 → … → 5 → 0, about 23 s) that the **original** FairyLight instance 2 flies
  near the start. The FairyLight you add follows graph A or B and is not affected.
- Each `offset` is in level units from the original waypoint; its length must be above 0 and at most 6. Each node
  appears at most once. The tool writes the new x / y / z (float32) in the waypoint; radius and flags stay.
- The preview lists every moved waypoint's new position. Its flight through them is a prediction: the fairy was
  measured within 0.20–0.27 of every original waypoint and within 0.22 of a waypoint inserted 6 units off its route
  (E-480), but no moved route has run in the guest yet.
- The tool does not check waypoints against walls, the floor, visibility or the camera.

## 6. Validate without writing anything

```powershell
$env:R3HD_DEV_STRUCTURAL_TX = "intro_20"
python -I tools\r3hd_mods.py level-patch private\work\my_patch.json --check
```

`--check` runs the same parser, geometry validators, composition checks and transaction builder as a normal compile.
It writes nothing. Add `--json` for the structured report (the `preview` object). It takes about a second.

Exit codes: 0 = valid, 2 = refused (with a reason code and a specific message), 1 = internal error.

## 7. Reading the preview

```text
level-patch g6p22_west_dip_fairy.json: VALID (nothing written)
  declaration  g6p22.custom-terrain-fairy  identity bc7c4f5cdd364b6e
  target       intro_20: intro_20.lvl a21aa769, intro_20.ptr be90b58a, transit.lvl 51c0fbf1 (exact originals)
  terrain      west-dip (region start-floor-v1): vertex 0 -0.10, vertex 2 -0.25, vertex 4 -0.20
               allowed: vertices 0 2 4, lowering 0.05..0.30, 2-3 groups
               geometry checks passed: 10 collision triangles, 3 visual vertices / 10 visual triangles, ...
  standing     Rayman settles at z -25.1408 (predicted; unmodified -25.0779: -0.0629; start-two-step-v1 -25.2668: +0.1260)
               he stands on collision triangle 1/11 (vertices 0 9 10): moved vertex 0 sets his height
  west floor   z -25.3184 (predicted; measured original -25.2122, G6-P26 (E-515) run w2, triangle 1/4): moved vertex 2 4 changes it
  fairylight   follows graph A (follow_graph_of 0)
  transaction  level-tx v2 3e74d122bdb042e3: 63 ranges (50 terrain + 13 FairyLight)
  ...
  runtime      OBSERVED for these exact guest images: G6-P23 (E-512) run m1 (...)
```

The report gives each line a different level of evidence:

- **target**: verified against your files. The files are the exact supported originals.
- **terrain / transaction**: verified by the compiler, offline.
- **standing**: a prediction, not a measurement. It is Rayman's measured standing height on the unmodified level
  (probe l1, E-508), offset by the change of the collision plane under that point. The method was checked within
  0.0012 (G6-P20) and 0.0007 (G6-P23) of the guest. If the probe's surface model does not apply, the line says
  `prediction unavailable` and gives the reason. The tool never prints a guessed number.
- **runtime**: `OBSERVED` only when the compiled guest images (lvl / ptr / transit result hashes) are identical to a
  run on record. Otherwise it says `UNTESTED`. A valid preview is not a runtime verification.

## 8. Compile, import and plan

```powershell
python -I tools\r3hd_mods.py level-patch private\work\my_patch.json --out private\work\my_patch_mod
python -I tools\r3hd_mods.py import private\work\my_patch_mod --enable --mods-root private\work\mods --cache private\work\cache
python -I tools\r3hd_mods.py plan --mods-root private\work\mods --cache private\work\cache
```

- `--out` must be a new or empty folder. It receives only `mod.json`, and only after the whole patch compiled.
- Use private `--mods-root` / `--cache` folders for experiments. Without them, `import` and `plan` use
  `private/play/mods`.
- `plan` lists the mod as active with one `level-tx` line, and writes the plan file.

## 9. Common errors

| Message (abridged) | What to do |
|---|---|
| `level-patch is a development-only composition ... needs R3HD_DEV_STRUCTURAL_TX=intro_20` | Set the variable in this shell. Nothing was written. |
| `vertex 7 is not in region start-floor-v1 (allowed: 0, 2, 4)` | Use only vertices 0, 2 and 4. |
| `delta_z 0.1 is outside -0.30..-0.05: ... raising is not supported` | Use a negative value from −0.30 to −0.05. |
| `vertex 0 is assigned twice (already in group 'spawn-corner' ...)` | Put each vertex in one group. |
| `'ptr_sha256' is not the verified original intro_20.ptr ...` | Copy the three source hashes from an example. |
| `missing component(s) ['terrain']` | Include exactly one `terrain` and one `fairylight` component. |
| `follow_graph_of 2 (supported: 0 = graph A, 1 = graph B)` | Choose 0 or 1. |
| `node 1 moves 7.071 units; graph C allows at most 6 units` | Shorten the offset. |
| `node 6 (graph C has nodes 0-5)` / `node 3 is moved twice` / `the offset is zero` | Use nodes 0–5, once each, with a non-zero offset. |
| `... unknown: ['colour'], missing: []` | Remove keys that the format does not define. |
| `the level file is not the one this patch was made for` / `TARGET_CHANGED` | Your game files differ from the supported originals. |
| `element E triangle T would become too steep or flip`, `vertex V would leave the octree root`, ... | A geometry invariant failed. The message names it. With the current region and bounds, no grid combination does this (G6-P22 sweep, 432 / 432). |

## 10. Limitations: why this is not a map editor

- One level, a floor region of 3 vertices (4 with `start-floor-v2`), lowering only, and one FairyLight on one of two
  existing graphs. The rest of the vertices around the pit are wall bottoms, have no unique visual twin, or are at
  the slope limit (G6-P25 study).
- The tool can only produce changes that it can check against data verified from the target (vertex twins, bounds,
  octree, derived normals). Growing the region needs new `intro_20` target evidence first.
- The drawn `intro_20` terrain change has no framebuffer attribution yet.
- Graph B combined with terrain has not run in the guest.
- A route only moves the six existing waypoints of graph C, by at most 6 units each. It does not add nodes or graphs,
  and it does not change the added FairyLight's flight. No moved route has run in the guest.
- Development builds only. Nothing here is for public distribution.
