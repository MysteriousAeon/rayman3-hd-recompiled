# Rayman 3 HD Recompiled v1.2.0

This update restores more of the original PC visual effects in HD+, adds PlayStation button prompts and V-Sync, improves controller navigation in Settings, and introduces experimental level remix tools, including an Experimental 3D Level Viewer. It also adds an optional experimental save converter for transferring progress from the original Rayman 3 PC release (2003).

## HD+ Improvements

HD+ now includes four additional visual corrections:

- **Power-up spiral:** Restored the original PC swirl around Rayman when a power-up starts.
- **Power-up canisters:** Restored the purple beam and the colored rings above and below power-up canisters.
- **Distant lock-on:** Restored the blue color of the lock-on indicator for targets that are out of range.
- **Ugly creatures:** Fixed the incorrectly oriented body texture of the Ugly creatures in the Bog of Murk.

These corrections are enabled by default in HD+. Vanilla retains the original Xbox 360 HD appearance, while Custom allows individual corrections to be enabled or disabled under Settings → Corrections.

## Controllers & Settings

- Added PlayStation button prompts. In Settings, look below **Game profile** for **Controller button prompts** and choose **Auto** (default), **Xbox**, or **PlayStation**. Auto picks the icons for the primary controller when the game starts.
- The in-game PC Settings panel (F4) can now be fully navigated with a controller, and help tooltips stay on screen.
- Added an optional **V-Sync** setting under Settings → Display. It is disabled by default and takes effect the next time the game starts.
- Updated the English and Turkish Settings interfaces.

## Modding

- Mods that change gameplay are now marked in Settings → Mods, with an explanation in their details.
- While a gameplay-changing mod is enabled, **new achievements are not earned**. Enabling gameplay-changing mods does not automatically convert or delete your saves. As with other experimental mods, backing up important saves before use is recommended. Disable the mod to earn achievements again.
- Level remixes can be exported as mods and installed through Settings → Mods like any other mod.

## Experimental 3D Level Viewer

Added an **Experimental 3D Level Viewer** for Windows, allowing you to explore selected Rayman 3 HD levels using their original 3D geometry and textures.

- **3D exploration:** Navigate recognizable game environments with a free camera.
- **Limited level editing:** Move supported objects, adjust movement paths, and modify terrain in designated areas.
- **Mod integration:** Export your edits as mods and manage them through **Settings → Mods**.
- **Classic editor:** The existing top-down editor remains available as **Classic / Advanced Editor**.

Open the viewer under **Settings → Mods → Experimental 3D Level Viewer**. The Classic editor is also accessible from the Start menu's Level Editor shortcut or the portable edition's `Level Editor.cmd`.

**Current limitations:**

- This is not a complete custom-map creator. Creating new levels, adding geometry, and freely placing objects are not supported.
- Editing is limited to three early-game level segments (`intro_10`, `intro_15`, and `intro_20`), with different capabilities available in each.
- Many objects cannot be moved, including those positioned by the game's scripts.
- Some experimental edits, including waypoint changes, have not been verified in gameplay.
- Terrain editing is restricted to a small area of one level.
- The editing interface is still experimental and may require some familiarity with level editing tools.

## Experimental PC Save Converter

An optional standalone converter is now available for transferring saves from the original Rayman 3 PC release (2003) to Rayman 3 HD Recompiled on Windows.

Download `Rayman3HDRecompiled-1.2.0-pc-save-converter.zip` separately from the release assets. The converter preserves supported progress information, including levels, cages, scores, current and maximum health, and story progression.

**How to use:** Create a new save slot in Rayman 3 HD Recompiled, close the game, then run `R3SaveConverter.exe` to import your original PC `.sav` file. Existing destination slots are backed up before replacement. Detailed instructions are included in the ZIP and the project README.

**Current limitations:**

- Conversion is experimental and has been tested with a limited number of PC saves. Compatibility with every save or PC release is not guaranteed.
- PC key bindings and option settings are not transferred, and progress towards some achievements starts again.
- Maximum life was observed to return to 40 after playing the first levels with a converted all-cages save.
- Cage-gated bonus content has not yet been verified using converted saves.

## Updating from v1.1.0

Close the game, Settings, and any level editor before updating.

**Installer:** Run the new setup and select your existing installation folder. Existing saves, mods, settings, and preferences are preserved.

**Portable ZIP:** Extract the new package to a new writable folder. Follow the included `PORTABLE.txt` instructions when migrating data from an earlier portable copy.

HD+ automatically enables the new visual corrections. Existing Custom preferences are preserved, and corrections without a saved preference follow the Custom profile's base.

Backing up your settings and profiles before updating is strongly recommended.

The installer and portable edition require your own supported Xbox 360 Rayman 3 HD package (title ID `5841123F`, without a title update). No game files are included.

## Additional Notes

- The game continues to run at 60 FPS. V-Sync results depend on your graphics driver and display.
- Button prompts are chosen when the game starts; restart the game after changing controllers.
- The optional Turkish translation package remains v1.0.1, with unchanged contents.
- Some visual issues inherited from the Xbox 360 HD release remain. A rare audio-initialization crash has also been observed during testing.
- This is a Windows-only update. The experimental Linux pre-release remains at v1.1.0 and does not include the new features or fixes in this release. Steam Deck compatibility has not been officially verified.
