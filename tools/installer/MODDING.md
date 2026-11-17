# Making mods for Rayman 3 HD Recompiled 1.2.0 (Windows)

A mod changes what the game reads, never the game files on disk: when the game starts, the enabled mods are checked
and laid over the game's data in memory. Turning a mod off (Settings > Mods) gives the original game back at the next
start. A mod is **data only**: a `mod.json` file plus PNG pictures. Nothing in a mod is ever run.

The commands below use the Python that comes with the game. Open a command prompt in the installation folder
(the folder with `app\`, `bin\`, `data\`) and type them as shown. `--home .` means "this installation".

## Game language and translation mods

The Settings app has a **Game language** choice, separate from **Settings language**.
It selects shipped game text, subtitles and voices for the next game launch.
**The current Turkish and PINHATT PT-BR translation mods need Game language = English:** they replace the
English text and subtitle entries. Choosing another native language does not translate that language's entries
with those mods. For native languages, disable conflicting translation mods yourself on the Mods page.
Nothing automatically disables, removes or changes a mod. Settings language affects only the PC Settings app.

## What a mod can change

| Kind (`type`) | What it changes | How it is matched |
|---|---|---|
| `texture` | one picture of the game (a bundle entry such as `menu\mnu_jard.dds`) | entry name; your PNG must have the entry's exact size |
| `text` | one string of the game's text (menus, dialogue, item names) | its place in `GAMEDATAbin/fix.lvl` (offset) and a hash of the original string |
| `glyph` | adds Turkish letters ğ Ğ ş Ş ı İ, ellipsis …, or Œ œ | the character; composed from glyphs, small accents or PNG layers |
| `subtitle` | the text of one cutscene subtitle | `vs.<language>.<movie>.<cue>` and a hash of the original cue |

Experimental gameplay-changing overrides: `script-constant`,
`macro-constant`, `designer-default`, `actor-position` and `waypoint-position`: one number inside an existing behaviour script, macro or
actor's starting values, or an existing actor's starting position, in a level (see "Script constants" below).

Not supported, and not to be expected from this port today: **models, animations, sounds and music, level geometry,
new, removed or rotated actors, new or longer scripts, any other script change, new files**, executable code of any kind, and
automatic conversion of arbitrary PC mods. Subtitle timing, order and the number of cues are the game's own and
cannot change.

## Your first mod in four steps

1. **Make a working example** (a striped test pattern with an arrow pointing up on one menu texture):

       app\python\python.exe app\tools\r3hd_modkit.py --home . template my_mod

   Add `--find "Resume Game" --text "Play On"` to also change one menu text.
2. **Edit `my_mod\mod.json`**: give it your own `id` (lower case: `a-z 0-9 . _ -`, for example
   `yourname.blue-menu`), `name`, `version`, `description`, `authors` and `license`. Replace
   `my_mod\textures\test_pattern.png` with your picture: **same width and height**, PNG, any colour type.
3. **Check and pack it**:

       app\python\python.exe app\tools\r3hd_modkit.py --home . pack my_mod my_mod.zip

   `pack` validates everything against your game files first and writes nothing if a check fails; the message says
   what to fix. `r3hd_modkit.py --home . check my_mod.zip` checks a .zip someone gave you.
4. **Install it**: Settings > Mods > Install .zip, choose `my_mod.zip`, and start the game.

## mod.json

```json
{
  "format": 1,
  "id": "yourname.blue-menu",
  "name": "Blue menu",
  "version": "1.0.0",
  "description": "What the mod does, in a sentence or two.",
  "authors": ["Your name"],
  "license": "CC0-1.0",
  "target": {"title_id": "5841123F", "releases": ["x360-xbla-5841123F-v1"], "min_port_version": "0.36.0"},
  "requires": [],
  "conflicts": [],
  "overrides": [
    {"type": "texture", "entry": "menu\\mnu_jard.dds", "bundles": ["GAMEDATAbin/fix"], "image": "textures/menu.png"},
    {"type": "text", "file": "GAMEDATAbin/fix.lvl", "offset": 123456, "slot_sha256": "<64 hex digits>", "text": "Play On"}
  ]
}
```

- `format` is 1. `id` is the mod's identity: a later version with the same `id` replaces the installed one in place
  (its on / off state and its place in the list stay). Keep it stable across your releases.
- `version` looks like `1.0.0` (an optional suffix such as `-beta` is allowed; versions compare by their numbers).
- `target` must name Rayman 3 HD for Xbox 360 as shown; `min_port_version` is the oldest version of this port your
  mod needs (0.36.0 is fine for everything described here).
- `requires` / `conflicts` list other mods' `id`s. A Turkish letter (or …) in a `text` needs a `glyph` for it in the
  same mod or in a mod it `requires`.
- Allowed files: `.json`, `.png`, `.txt`, `.md`. Limits: 2,048 files, 64 MB per file, 256 MB in all, 4,096
  overrides, pictures up to 4096 x 4096.

### Finding what to change

    app\python\python.exe app\tools\r3hd_mods.py --home . texture-info "menu\mnu_jard.dds"
    app\python\python.exe app\tools\r3hd_mods.py --home . texture-export "menu\mnu_jard.dds" original.png
    app\python\python.exe app\tools\r3hd_mods.py --home . text-find "Resume Game"

`texture-info` gives the bundles that hold an entry with its size and format; `texture-export` writes the entry
upright as a PNG to paint over (it comes from your own game files: do not publish it). `text-find` gives the
`offset` and `slot_sha256` of a string. Entry names follow the original PC game's texture paths (`charact\rayman.dds`
for `charact/rayman.gf`).

### Textures

Your PNG must be the entry's exact size. It is encoded into the entry's own format (DXT1 or DXT5) with all its mip
levels. Transparency: DXT5 entries keep your alpha; DXT1 entries have only on/off transparency. `bundles` is
`"all"` (every level that holds the entry) or a list such as `["GAMEDATAbin/fix"]`.

### Texts

The `text` replaces the string at `offset` if the string there still has the hash `slot_sha256` (so a mod made for a
different game file is refused, not misapplied). A text may be longer than the original if the mod's other text
overrides free enough room; when it does not fit, validation says by how many bytes to shorten. The game's font has
no `; < > { }`; it has no `…` either unless a `glyph` adds it (see above).

### Script constants (experimental)

The game's actors run behaviour scripts stored in each level file. A `script-constant` changes **one number** in
such a script: an `int` (whole number, -2147483648 to 2147483647) or a `real` (32-bit decimal). Nothing else in a
script can change: not its structure, conditions, function calls, references to actors or other data, and nothing
can be added. List a level's behaviours, then one behaviour's scripts and numbers:

    app\python\python.exe app\tools\r3hd_mods.py --home . script-info intro_10
    app\python\python.exe app\tools\r3hd_mods.py --home . script-info intro_10 --behavior FlyMvt

```json
{"type": "script-constant", "level": "intro_10",
 "behavior": "<the full behaviour name from script-info>", "script": 0, "node": 16,
 "script_sha256": "<64 hex digits from script-info>", "kind": "real", "value": 0.25}
```

- `level` is a level folder name (`intro_10`) or `fix` (data shared by every level). `script` and `node` are the
  indexes script-info prints; `kind` must be the node's own kind; `script_sha256` ties the edit to exactly that
  script, so a mod for different game data is refused, not misapplied.
- The number is written in place: the level file keeps its size. A mod's script constants apply together; if a
  higher mod changes one of the same numbers, the lower mod is left out as a whole (no half-applied logic).
- **This changes game logic.** The tool checks the form, not what the number means: a wrong value can make a level
  impossible, crash the game or break progression. The meaning of a number comes from your own testing. A change in
  a level is not progression in a save; test such mods on a copy of your profile.
- A mod with a `script-constant` is marked **[changes game logic]** in Settings > Mods, with a warning in its
  details. While such a mod is applied, **the game awards no new achievements** (the ones you already have are kept;
  an achievement the game tries to award meanwhile is not recorded and may need to be earned again with the mod off).
  Saving is not changed: progress saved while such a mod is on is ordinary save data and may depend on the mod. Back
  up your saves before you use one. A port older than this feature refuses a plan with such a mod as a whole.
- **Constants in macros** (development prototype, D-226): many numbers sit in a model's *macros*, small unnamed
  scripts its behaviours call. `script-info LEVEL --model TEXT` lists the macros of the models whose first behaviour
  contains TEXT, with each macro's index, `script_sha256` and numbers, or why it cannot be changed. Override:
  `{"type": "macro-constant", "level": "intro_10", "model": "<the model's full first-behaviour name>", "macro": 3,
  "node": 34, "script_sha256": "...", "kind": "int", "value": 60}`. Refused: macros of `fix`, empty macros, and
  macros used by anything but their own model. The same warnings, achievement rule and priority apply.
- **Designer-variable starting values** (development prototype, D-227): each actor placed in a level keeps its
  own starting values for its model's numbered *designer variables*. The same `script-info LEVEL --model TEXT`
  lists, per instance of the model in that level file (counted from 0 in file order), its `initial_sha256` and the
  variables that can change: `bool` (0 or 1), `byte` (0 to 127), `int`, `real`. Override:
  `{"type": "designer-default", "level": "intro_10", "model": "<the model's full first-behaviour name>",
  "instance": 0, "variable": 5, "initial_sha256": "...", "kind": "byte", "value": 6}`. Refused: `fix`, vectors,
  references to actors, waypoints, texts and every other type, and instances whose values are shared with or
  referenced from other data. A starting value only matters if the actor's scripts read it before they set it
  themselves; many scripts set their variables when the actor starts. The same warnings, achievement rule and
  priority apply.
- **Actor starting positions** (development prototype, D-228): `script-info LEVEL --model TEXT` also lists, per
  actor of the model placed in that level file (counted from 0 in file order), its `matrix_sha256`, matrix type and
  position. Override: `{"type": "actor-position", "level": "intro_10", "model": "<the model's full first-behaviour
  name>", "instance": 0, "matrix_sha256": "...", "position": [19.1, -13.56, -34.58]}`. Only the position moves;
  rotation and scale stay. Refused: `fix`, actors without a usable matrix, matrices shared with or referenced
  from other data, and (D-229) actors whose model's scripts set their position themselves: a moved bridge, for
  example, went straight back to its anchor (E-462). Other actors may still be moved by their own scripts later
  (along paths, onto waypoints): a new starting position matters only for actors that stay where they are placed.
  Whether a moved actor's collision moves with it has not been shown. Moving an actor into a wall, out of reach or
  out of its area can break the level. The same warnings, achievement rule and priority apply.
- **Waypoint positions** (development prototype, D-231): moving actors such as the `intro_10` flight follow a graph
  of waypoints that one of their designer variables names. `script-info LEVEL --model TEXT` lists, per graph
  variable of each actor, every node's `waypoint_sha256`, position and radius, or why it cannot move. Override:
  `{"type": "waypoint-position", "level": "intro_10", "model": "<the model's full first-behaviour name>",
  "instance": 0, "variable": 0, "node": 13, "waypoint_sha256": "...", "position": [25.08, -34.13, -40.1]}`. Only the
  position moves (radius and flags stay); nodes and connections cannot be added, removed or rewired. Refused: `fix`,
  graphs another actor or other data also uses, and waypoints shared between nodes or referenced from elsewhere. A
  moved waypoint can send an actor through walls or out of reach; nothing checks the level geometry. The same
  warnings, achievement rule and priority apply.
- Tested so far: one edit read back from the running game (E-455), the flight's starting speed in `intro_10`
  (E-456), its loop-arc speed in a macro (E-459), its starting lum count (E-460), the position of one lum
  (E-461) and one waypoint of its route (E-464) changed in hidden test runs.
  Treat every script mod as something to try in the game before you share it. `script-info` output comes from
  your game files: do not publish it.

### Achievement names (optional)

A mod may also carry `achievements/achievements.json` beside `mod.json`: the names and descriptions the Achievements
window and the unlock notice show. It is display text only: achievement ids, unlock rules, scores and your progress
never change, and the game itself keeps reading the original English.

```json
{"format": 1, "kind": "r3hd-achievement-text", "title_id": "5841123F", "language": "tr",
 "strings": [{"id": 9, "field": "label", "source_sha256": "<SHA-256 of the English text>", "text": "..."}]}
```

`field` is `label`, `description` or `unachieved` (the text shown while locked; leave it out when it is the same as
the description). An entry is shown only while `source_sha256` matches the game's English; an empty `text`, a
changed English or a mod that is turned off shows the English. A file with a mistake is ignored as a whole and the
rest of the mod still applies. Up to 64 characters for a name, 160 for a description; Turkish letters are drawn.

## Order and priority

Settings > Mods lists the installed mods; the **higher a mod is, the higher its priority**: when two mods change the
same thing, the upper one wins. Use the arrows to reorder, the check box to turn a mod on or off, Remove to delete it.
Changes apply the next time the game starts. A mod applies whole or not at all: if an enabled mod no longer fits (a
game file differs, a required mod is missing), it is left out, the list says why, and the other mods still apply.

## Level Remix Editor (`intro_10`, `intro_15`, `intro_20`)

Start **Rayman 3 HD Recompiled - Level Editor** (Start menu), **Classic / Advanced Editor...** on Settings > Mods, or
`Level Editor.cmd` in the portable folder. **Experimental 3D Level Viewer...** on Settings > Mods shows the same levels
with their original geometry and textures and offers limited editing of supported objects, paths and terrain. The Level Remix Editor changes three **existing** levels from your own
game data and saves the result as a mod. It does not create new levels or maps and is not a free-form level editor.
Choose the mode and level at the top right:

- **intro_20 terrain + FairyLight patch:** lower the green start-floor vertices within their verified range and add
  a FairyLight that follows graph A. Graph B and moved graph C waypoints are shown as DEVELOPMENT-ONLY: the released
  game refuses a mod that contains them.
- **Actor and waypoint remix (intro_10, intro_15, intro_20):** move existing actors (up to 25 units) and the
  waypoints of actor-owned routes (up to 6 units). The read-only collision is drawn behind them. Every item shows
  its evidence class:
  - **VERIFIED:** tested in the game at a new position.
  - **EXPERIMENTAL:** checked byte for byte, but its behaviour at a new position has not been measured; test it
    yourself.
  - **LOCKED / SCRIPT-OVERRIDDEN:** cannot be moved.

  Rotation, new actors, new waypoints and new links are not supported. Each project and each mod covers one level.
  The ground readout and **Snap to ground** are a geometric prediction from the static collision, not a behaviour
  guarantee. Warnings after Validate are advisory; the compiler decides. The **Presets** menu holds tested edits, for
  example two intro_10 red lums moved onto the flight path, the intro_20 FairyLight loop and three moved intro_20
  actors. Each is labelled with exactly the evidence of its tested items (VERIFIED, PLACEMENT VERIFIED or ROUTE
  SUPPORTED). The route panel lists each graph and can revert single nodes.

Edit, press **Validate**, then **File > Export mod folder** and **File > Import + enable exported mod**. The mod
appears in Settings > Mods like any other, marked `[changes game logic]`, and applies the next time the game starts.
While it is enabled the game awards no new achievements. Your game files and saves are never changed by the editor,
but progress saved while such a mod is on may depend on it: back up your saves first (each play session also keeps a
copy of the saves from before it in the installation's `save_history` folder). Projects (`*.r3hdmap.json`) and exports are saved where you
choose. **Help > What can this editor change?** repeats these limits. Close the editor before you uninstall, repair
or update the game: the installer refuses while it is open.

## Original PC (2003) texture mods

Texture mods for the original PC game made as Rayman Control Panel packages (`metadata.jsonc` plus `.gf` textures
under `...<archive>.cnt\<folder>\<name>.gf`) can often be converted:

    app\python\python.exe app\tools\r3hd_pcmod.py --game-dir data\content inspect pc_mod.zip
    app\python\python.exe app\tools\r3hd_pcmod.py --game-dir data\content convert pc_mod.zip converted_mod
    app\python\python.exe app\tools\r3hd_modkit.py --home . pack converted_mod converted_mod.zip

- Supported `.gf` pixel formats: 8888, 888, 565, 1555, 4444, 88 and paletted (one channel); 1 to 4 channels.
- Each `.gf` goes to the HD entry of the same name in every bundle that holds it and is resized to that entry's size
  (the HD textures are often larger). Without alpha in the source, the HD texture's own transparency is kept.
- A texture with no HD entry of that name is skipped and `inspect` says so. Models, sounds and anything that is not a
  `.gf` texture are not converted.
- One real PC texture mod has been converted and checked in the game so far; treat every conversion as something to
  look at in the game before you share it.
- The rights stay with the original mod's authors (and with Ubisoft for anything derived from the game's art):
  convert only what you may use, and do not share a converted mod unless its authors allow it.

## Sharing a mod

Share the `.zip` that `pack` wrote. Never put files exported from the game (`texture-export` pictures, game text,
sounds, anything from `data\`) into a mod you share, unless you made them yourself: a mod that changes a texture
should carry your own picture, a text mod only your own words.
