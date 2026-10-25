# Making mods for Rayman 3 HD Recompiled

A mod changes what the game reads, never the game files on disk: when the game starts, the enabled mods are checked
and laid over the game's data in memory. Turning a mod off (Settings > Mods) gives the original game back at the next
start. A mod is **data only**: a `mod.json` file plus PNG pictures. Nothing in a mod is ever run.

The commands below use the Python that comes with the game. Open a command prompt in the installation folder
(the folder with `app\`, `bin\`, `data\`) and type them as shown. `--home .` means "this installation".

## What a mod can change

| Kind (`type`) | What it changes | How it is matched |
|---|---|---|
| `texture` | one picture of the game (a bundle entry such as `menu\mnu_jard.dds`) | entry name; your PNG must have the entry's exact size |
| `text` | one string of the game's text (menus, dialogue, item names) | its place in `GAMEDATAbin/fix.lvl` (offset) and a hash of the original string |
| `glyph` | adds one of the Turkish letters ğ Ğ ş Ş ı İ, or the ellipsis … (1.0.1 and later), to the game's font | the character; drawn from the font's own glyphs plus small accents |
| `subtitle` | the text of one cutscene subtitle | `vs.<language>.<movie>.<cue>` and a hash of the original cue |

Not supported, and not to be expected from this port today: **models, animations, sounds and music, levels, scripts,
game logic, new files**, executable code of any kind, and automatic conversion of arbitrary PC mods. Subtitle timing,
order and the number of cues are the game's own and cannot change.

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
