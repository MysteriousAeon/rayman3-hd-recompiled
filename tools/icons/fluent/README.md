# Fluent utility icons

VERIFIED: Microsoft Fluent UI System Icons, MIT, copyright (c) 2020 Microsoft Corporation.
Repository: https://github.com/microsoft/fluentui-system-icons
Pinned commit: `a347af95478f989038cccbf085978865264c048a` (retrieved 2026-10-18).

Sources are unchanged upstream SVG files from `assets/Settings/SVG/` and `assets/App Generic/SVG/` at that commit.
License: [Fluent-System-Icons-LICENSE.txt](../../installer/Fluent-System-Icons-LICENSE.txt), included in the staged application.

`make_r3hd_icon.py` renders the paths as white on a project-authored slate (Settings) or blue (application) tile.
Settings uses upstream 16/24/32/48 designs; application uses 24/32/48 (24 reduced for 16). Larger outputs scale the 48 design.
No game, font or bitmap input. The application glyph is the setup/executable fallback; the local package-derived Play icon remains separate.

SHA-256 below normalizes CRLF to LF for fresh Windows clones. These are source inputs, never game-derived data.

| Source | SHA-256 (LF) |
| --- | --- |
| `ic_fluent_app_generic_24_filled.svg` | `c77fc87a4a0efd4b0873ad858b49fde9d0d39ae18b42e0f2fdae67ef0e7b9b49` |
| `ic_fluent_app_generic_32_filled.svg` | `c3d8959541e9fc045768b7680f086b35783abfbba7c61d13c878fb7703d78a43` |
| `ic_fluent_app_generic_48_filled.svg` | `baffa69a7571df943fbe29c708f158ed2c42f9cf36814d74d53fcea98768aa3f` |
| `ic_fluent_settings_16_filled.svg` | `5e55fdd5a861f56d9af1a6553f9d7e7229e31946a7d69baaa859da4979dbed59` |
| `ic_fluent_settings_24_filled.svg` | `c19ff922990add433c3d5ddc2fb9843b3e4d31c1074ef05295d46c4ec8f23c83` |
| `ic_fluent_settings_32_filled.svg` | `e4378e3e827430ddce300c519499dd67b3c63a37e468b0129748abd043ca2cb7` |
| `ic_fluent_settings_48_filled.svg` | `15338faf8588ed156dd5e126e1ea459e251e82dfcc7664a9f452438cd09e222b` |
