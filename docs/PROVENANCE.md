# Source provenance

This page records external technical references used during development. Third-party software included with the
release is listed separately in THIRD_PARTY_NOTICES.txt beside the installed application materials
([source copy](https://github.com/MysteriousAeon/rayman3-hd-recompiled/blob/main/tools/installer/THIRD_PARTY_NOTICES.txt)).

## Raymap

During development, the public [Raymap](https://github.com/byvar/raymap) repository was consulted as a technical
research reference. It informed the project's early understanding of some Rayman 3 data structures and file
formats, including texture, font, collision, mesh and script layouts, and the texture format of the original PC
release. The Xbox 360 layouts the project relies on were then checked against the game's files, its executable or
the running game, and the PC texture format against a real PC mod package.

This research also informed the shipped bundle-texture, font/glyph and PC texture-conversion tools; removing
the development dependency described below does not remove that research influence.

The game runtime, the installer and the build do not require Raymap. Earlier, a development-only research tool read
name tables from a separate local Raymap checkout; that dependency has been removed. Some tool comments still refer
to Raymap where it was used, so that the history stays accurate.

Rayman 3 HD Recompiled is an independent project and is not affiliated with or endorsed by Raymap or its
contributors.

## Rayman Control Panel

RayCarrot's [Rayman Control Panel](https://github.com/RayCarrot/RaymanControlPanel) informed the design of this
project's mod tools, particularly GF texture handling, mod metadata, priority ordering, and archive-entry
addressing. The PC texture converter also supports RCP-format mod packages. This acknowledgment reflects
research and design influence, not collaboration or endorsement.

## Community research leads

ICUP321's research on texture orientation in the PS3 HD release provided a diagnostic lead. The Xbox 360
texture corrections were established separately against this version's own data; no PS3 patch assets are included.
Community issue reports have also helped identify problems for investigation. These references do not imply
affiliation with or endorsement by their authors or the Rayman modding community.

## Limits

This page reflects the project's own review of where Raymap was used. That review was targeted rather than an
exhaustive comparison of every file, and it found no Raymap source files or name tables in the repository or the
release. It is not a legal opinion and does not claim a clean-room development process.

The RCP review established research and design influence, without establishing copied RCP source code.
Exact GF implementation lineage remains unresolved. This page is not an exhaustive account of every source
consulted during AI-assisted development, and does not establish implementation independence from those sources.
