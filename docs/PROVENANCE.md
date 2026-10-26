# Source provenance

This page records external technical references used during development. Third-party software included with the
release is listed separately in [THIRD_PARTY_NOTICES.txt](../tools/installer/THIRD_PARTY_NOTICES.txt).

## Raymap

During development, the public [Raymap](https://github.com/byvar/raymap) repository was consulted as a technical
research reference. It informed the project's early understanding of some Rayman 3 data structures and file
formats, including texture, font, collision, mesh and script layouts, and the texture format of the original PC
release. The Xbox 360 layouts the project relies on were then checked against the game's files, its executable or
the running game, and the PC texture format against a real PC mod package.

The game runtime, the installer and the build do not require Raymap. Earlier, a development-only research tool read
name tables from a separate local Raymap checkout; that dependency has been removed. Some tool comments still refer
to Raymap where it was used, so that the history stays accurate.

Rayman 3 HD Recompiled is an independent project and is not affiliated with or endorsed by Raymap or its
contributors.

## Limits

This page reflects the project's own review of where Raymap was used. That review was targeted rather than an
exhaustive comparison of every file, and it found no Raymap source files or name tables in the repository or the
release. It is not a legal opinion and does not claim a clean-room development process.
