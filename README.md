# Rayman 3 HD Recompiled

A native Windows and Linux port of **Rayman 3 HD** for Xbox 360. The game's code has been statically recompiled to run directly on a PC, without an emulator.

Setup uses your own Xbox 360 game package. Windows v1.3.0 offers an installer and a portable ZIP; Linux uses a portable archive, currently available as an experimental pre-release (v1.1.0). Downloads are on the project's [Releases page](https://github.com/MysteriousAeon/rayman3-hd-recompiled/releases).

**No game files are included.** You need your own, legally obtained copy of Rayman 3 HD for Xbox 360.

This is an independent fan project and is not affiliated with or endorsed by Ubisoft or Microsoft. Rayman 3 HD and related trademarks belong to their respective owners.

## Official Trailer

[Rayman 3 HD Recompiled - Official Trailer](https://youtu.be/OxQLvGyhB7s)

## Why this project exists

Rayman 3 was one of my favorite games growing up, and I wanted my wife to experience it too. I wanted her to be able to play it in Turkish, so I started working on a way to make that possible. What began as a personal project eventually grew into a native PC port of the Xbox 360 HD version.

## Features

- **Native Windows and Linux support:** Play the Xbox 360 HD version without running an emulator.
- **HD+ enhancements:** Optional fixes for lighting, sky colors, charge effects, power-up effects, lock-on colors, texture rendering, and Combo Meter animation, alongside Vanilla and Custom profiles.
- **Mouse and keyboard support:** Optional mouse camera and button controls, mouse-controlled Look Mode, two keyboard layouts, and customizable bindings.
- **In-game PC Settings:** Press F4 to adjust common settings without leaving the game.
- **Controller support:** Customizable controller button mapping, including support for Xbox-compatible controllers and native DualSense controllers, with Xbox or PlayStation button prompts.
- **DualSense enhancements:** Dynamic lightbar colors, adjustable adaptive trigger resistance, and optional controller-speaker effects.
- **Built-in game languages:** English, French, Spanish, Italian, and German, using the original Xbox 360 HD game data.
- **Turkish translation:** An optional localization covering game text, menus, subtitles, and achievement descriptions.
- **Achievements:** In-game achievement tracking and notifications, with Turkish text when the translation mod is enabled.
- **Discord Rich Presence (Windows):** Optional Discord activity integration.
- **Mod support:** Install and manage compatible texture, text, font, and subtitle mods through Settings.
- **Level remix tools (Windows, experimental):** Explore selected levels in the Experimental 3D Level Viewer and make limited changes to supported objects, paths, and terrain, or use the Classic 2D editor.
- **Portable editions and Windows installer:** Set up the game using your own Xbox 360 package, with persistent settings and saves.

## Requirements

| Requirement | Windows | Linux |
|---|---|---|
| System | Windows 10 or 11, 64-bit | 64-bit Linux, x86-64-v2 CPU; glibc 2.38+ and libstdc++ with GLIBCXX_3.4.32+ |
| Graphics | Direct3D 12 | Vulkan 1.2+ driver with the required device features; Wayland or X11 desktop |
| Dependencies | [Visual C++ Redistributable 2015–2022 (x64)](https://aka.ms/vs/17/release/vc_redist.x64.exe) for the installer; included in the portable ZIP | Python 3.10+, Tkinter for the GUI, desktop X11/XCB and Wayland client libraries, and PulseAudio-compatible desktop audio |

The Linux package is built against Ubuntu 24.04 and has been tested on CachyOS with KDE Wayland and NVIDIA graphics. Python/Tkinter and graphics/audio libraries come from your distribution; compiler tools are not needed to play.

Both platforms need:

- Approximately 2.3 GB of free disk space
- Your own Xbox 360 Rayman 3 HD package: the original Xbox Live Arcade release (title ID `5841123F`), **without a title update**, copied from your console's storage

## Installation

Copy the game package from your Xbox 360 to your PC. It is the file located under `Content\0000000000000000\5841123F\000D0000\` on your console's storage.

### Windows installer

1. Download `Rayman3HDRecompiled-<version>-setup.exe` from the project's Releases page and run it. Administrator privileges are not required.
2. Select English or Türkçe, choose an installation folder, and provide your Xbox 360 game package. The installer validates the package against the supported release. Your original package is only read, never modified.
3. On the final page, select **Launch Rayman 3 HD Recompiled** to start the game, or **Open Settings** to configure it.

The game and Settings can also be launched from the Start menu or optional desktop shortcuts.

### Portable editions

A portable edition is available for both platforms. Extract the complete archive into a new writable folder:

| Platform | Download | Play | Settings |
|---|---|---|---|
| Windows | `Rayman3HDRecompiled-<version>-portable.zip` | `Play.cmd` | `Settings.cmd` |
| Linux | `Rayman3HDRecompiled-<version>-linux-x86_64-portable.tar.gz` | `./Play.sh` | `./Settings.sh` |

On Linux, run these commands in a terminal inside the extracted folder. On first launch, provide your supported Xbox 360 game package or verified extracted data and choose Vanilla, HD+ or Custom. Setup ends without starting the game automatically. Settings also provides optional Linux application-menu entries.

The portable edition keeps settings, profiles, saves, and mods inside its own folder. It does not automatically use another installation's profile.

The complete folder can be moved to another writable location. Back up your user data before updating; follow the included Windows `PORTABLE.txt` or Linux `app/README-LINUX.txt`. Keep an old copy until you have deliberately moved your chosen settings, saves and mods.

The Windows portable ZIP includes its required Visual C++ runtime libraries. A clean non-admin Windows installation has not yet been tested. On Linux, graphical setup and Settings need Tkinter; `./Settings.sh --console` offers terminal configuration if the GUI is unavailable.

### Windows installer updates, repairs, and uninstalling

**Update or repair:** Run the setup again and select the same installation folder. Your saves, settings, and mods are preserved. If the installed game files are intact, you do not need to select the original package again.

**Uninstall:** Use Windows Settings → Apps or the uninstaller in the installation folder. Saves, settings, and mods are kept unless you explicitly choose to delete them.

### Settings language

Settings is available in English and Turkish. Use **Interface language / Arayüz dili** in the upper-right corner to change it.

A fresh installation follows the language selected during setup. Updates preserve your existing preference.

This setting changes only the Settings interface. The game's language is controlled separately through the Turkish translation mod.

**Türkçe kurulum rehberi:** [docs/KURULUM.md](docs/KURULUM.md)

### Game language

Under **Settings → Advanced → Game Language**, choose from the five languages included in the original Xbox 360 HD release:

- English
- French
- Spanish
- Italian
- German

The selected language applies to the game's text, subtitles, and available voice audio. It is saved independently of the Settings interface language and game profile, and takes effect the next time the game starts.

The Turkish and Brazilian Portuguese translation mods currently replace English-language content. Select **English** as the game language when using either mod, and avoid enabling multiple language mods simultaneously.

French text, subtitles, and representative cinematic audio have been verified. Voice coverage throughout the full campaign has not yet been checked.

## Controls

Xbox-compatible controllers use the Xbox 360 button layout. The two keyboard layouts are listed below. On Windows, choose a layout and customize bindings under Settings → Controls; controller mappings are on the Controller tab. Linux preserves stored mappings but does not yet include this binding editor in its Settings window.

| Action | Modern (default) | Original PC (2003) |
|---|---|---|
| Move | W A S D | Arrow keys |
| Walk (hold while moving) | Ctrl | Shift |
| Camera | Arrow keys | Numeric keypad; A / S / D also turn or lower the camera |
| Jump / helicopter | Space | C |
| Attack (hold to charge) | E | Space |
| Lock on / strafe | Shift | Ctrl |
| Pause | Enter or P | Esc |
| Roll / Back | Esc or Backspace | W or Backspace |
| Look Mode (hold) | R | X |
| Show Health Bar | 1 | V |
| Grimace | 3 | V |

**Walk** is an additional keyboard action in this port. The Xbox 360 version allows slower movement by gently tilting the analog stick. Holding Walk provides a similar option on the keyboard.

You can rebind Walk or leave it unassigned.

On Windows, in Settings → Controls → Controller, capture a button to reassign it. Digital buttons swap with digital buttons, triggers with triggers, and sticks with sticks. One map applies to physical controllers; keyboard bindings remain independent. Xbox-compatible controllers and native DualSense are supported, with physical DualSense Bluetooth acceptance recorded; other device configurations have limited testing. Guide / PS and the touchpad cannot be assigned. Existing saved keyboard choices take precedence over updated defaults.

### Button prompts

On Windows, **Controller button prompts**, below **Game profile** in Settings, chooses the button icons shown in the game:

- **Auto** (default): Identifies the primary or only controller when the game starts. Unknown or ambiguous controllers use Xbox icons.
- **Xbox** or **PlayStation:** Always uses that set.

Restart the game after changing controllers or this setting.

The in-game PC Settings panel (F4) can also be navigated with a controller.

### Mouse controls

Mouse controls are optional and disabled by default.

Under **Settings → Mouse**, you can configure:

- **Mouse Camera:** Move the camera with the mouse and adjust its sensitivity.
- **Mouse Buttons:** Use mouse buttons for supported gameplay actions, including attacking.

When Mouse Camera is enabled, the mouse also controls the camera in Look Mode.

Mouse input is limited to gameplay and does not interfere with menus, cinematics, or pause screens. Keyboard and controller controls remain available.

## In-game PC Settings

Press **F4** during gameplay to open the PC Settings panel.

The panel provides quick access to commonly used options without requiring you to close the game. Some changes take effect immediately, while others require restarting the game.

For the complete set of options, use the separate Settings application.

### Hiding the score (F5)

For cleaner screenshots and recordings, enable **Settings → Corrections → Score HUD toggle (F5)**. Press **F5** during gameplay to hide or show the score and Combo Meter without affecting the rest of the HUD. This option is disabled by default.

## Game profiles: Vanilla, HD+, and Custom

Choose a profile under Settings → Game profile:

- **Vanilla:** Preserves the Xbox 360 release's original presentation, with compatibility fixes necessary for native PC execution.
- **HD+:** Enables additional visual corrections for issues inherited from the Xbox 360 HD release.
- **Custom:** Allows individual corrections to be enabled or disabled.

HD+ includes the following corrections:

| Correction | What it does |
|---|---|
| Combo Meter Animation | Adds a smooth closing animation instead of the original abrupt disappearance. |
| Separate texture coordinates for two-layer effects | Corrects texture coordinate handling for supported layered effects. |
| Correct HD Lighting Colors | Removes the unnatural pink tint in Hoodlum Headquarters and the Tower of the Leptys. |
| Correct Texture Orientation | Fixes upside-down textures on four Robo-Pirate statues in Hoodlum Headquarters and the incorrectly oriented body texture of the Ugly creatures in the Bog of Murk. |
| Correct Sky Colors | Restores the intended sky colors in Clearleaf Forest and the Bog of Murk. |
| Correct Charge Trail Colors | Restores the changing colors of Rayman's fist charge trail. |
| Restore Power-Up Spiral | Restores the original PC swirl around Rayman when a power-up starts. |
| Restore Power-Up Canister Colors | Restores the purple beam and the colored rings of power-up canisters. |
| Restore Out-of-Range Lock-On Color | Restores the blue color of the lock-on indicator for distant targets. |

Individual corrections can be configured under **Settings → Corrections** when using Custom.

Existing Custom choices are preserved during updates. New corrections without a saved preference follow the base profile selected for Custom.

Changing the game profile does not reset display, control, or advanced settings. Changes take effect the next time the game starts.

### Rendering resolution

Under **Settings → Display → Rendering resolution**, choose **Auto** (default), **720p (1x, original)**, **1440p (2x)**, or **2160p (3x)**.

Auto selects the smallest supported resolution that covers the game's visible 16:9 picture, excluding black bars on other aspect ratios. For example, in fullscreen on a 1080p display, Auto selects 1440p. You can manually select 720p if performance is poor.

### V-Sync

On Windows, **Settings → Display → V-Sync** synchronizes frame presentation with your display. It is off by default and takes effect the next time the game starts. Results depend on your graphics driver and display; the game continues to run at 60 FPS.

### Subtitles

For cinematic subtitles, enable the original game's **Subtitles** setting under Options → Audio. This option starts disabled on a new game profile.

The separate **Gameplay subtitles** option under Settings → Display enables subtitles for voiced dialogue during gameplay.

Fresh HD+ installations start with Gameplay subtitles enabled; fresh Vanilla installations start with it disabled. Your subsequent preference is preserved independently of profile changes.

## Turkish translation / Türkçe yama

The game can be played in Turkish using the optional translation mod.

The Windows installer includes the translation:

- **Turkish setup:** Installs and enables the translation.
- **English setup:** Does not install the translation automatically, but includes its ZIP in the installation's `extras\` folder.
- **Adding the translation later:** Open Settings → Mods → Install .zip and choose `extras\rayman3hd-turkish-1.0.1.zip`.
- **Switching back to English:** Disable the translation under Settings → Mods.
- **Updating:** Your existing translation preference is preserved. A mod you disabled remains disabled, and one you removed is not automatically reinstalled.

On Linux, download `rayman3hd-turkish-1.0.1.zip` from the project's Releases page, install it through **Settings → Mods → Install .zip**, and enable it before starting the game.

The translation covers the game's menus, dialogue, subtitles, and achievement text. It has received additional human localization review and corrections.

For complete Turkish instructions, see the [Türkçe Yama guide](docs/turkce-yama.md).

## Community Translations

- **Brazilian Portuguese — [PINHATT](https://github.com/crispinhatt/Rayman3HD-Traducao-PTBR):** An independently maintained community translation for Rayman 3 HD Recompiled. Follow the author's installation instructions.

The Brazilian Portuguese mod has passed target-data validation and limited runtime compatibility testing. Full-game translation review remains pending.

Only one language translation mod should be enabled at a time. Restart the game after changing language mods.

## DualSense enhancements

Native DualSense controllers can use additional features when supported by the connection and controller configuration:

- **Dynamic lightbar colors:** The lightbar changes according to the current game world and active power-up.
- **Adaptive R2 trigger:** Adds resistance to the R2 trigger during eligible gameplay.
- **Adjustable trigger strength:** Use Settings → Advanced → Adaptive Trigger Strength to choose a value from 0% to 100%.
- **Controller-speaker effects:** Plays selected power-up sounds through the DualSense's built-in speaker, with a separate volume control under Settings → Advanced.

The default adaptive trigger strength is 30%. Selecting 0% disables trigger resistance.

Controller-speaker effects require a USB connection and are disabled by default. Lightbar and adaptive trigger effects can be disabled independently.

These features require access to a supported physical DualSense. Steam Input or virtual controller configurations may prevent them from being available.

## Achievements and Discord

The port includes an in-game achievement interface. Achievement titles and descriptions can appear in Turkish when the translation mod is enabled.

On Windows, **Discord Rich Presence** can display your game activity in Discord. It is enabled by default for new installations and can be disabled in Settings.

Neither feature requires Xbox Live connectivity.

## Mods

Settings → Mods lets you install compatible mods, enable or disable them, and change their priority.

Supported data modifications include:

- Textures
- Text and font glyphs
- Subtitles
- Level remixes made with the included level tools (Windows), which make limited changes to selected levels

Mods cannot currently replace game models, add new levels, or replace audio, scripts, or executable code.

Mods are checked against the supported game files to reduce the risk of applying incompatible data.

Mods that change gameplay, such as level remixes, are marked and explained in Settings → Mods. While one is enabled, **new achievements are not earned**. Enabling gameplay-changing mods does not automatically convert or delete your saves. As with other experimental mods, backing up important saves before use is recommended. Disable the mod to earn achievements again.

To create a compatible mod, see [MODDING.md](tools/installer/MODDING.md), also included in the installed application's `app\` folder.

## Experimental 3D Level Viewer and Level Remix Editor

The Windows release includes experimental tools for exploring and remixing a few existing levels. Open them from **Settings → Mods**:

- **Experimental 3D Level Viewer:** Explore selected Rayman 3 HD levels using their original visual geometry and textures. Limited remix editing tools are available for supported objects, paths, and terrain.
- **Classic / Advanced Editor:** The top-down 2D Level Remix Editor. The Start menu's **Level Editor** shortcut and the portable edition's `Level Editor.cmd` open this editor.

Both tools read the game data of your own installation. A finished remix is exported as a mod; install and enable it in Settings → Mods, then play.

Please keep in mind:

- This is **not** a complete custom-map creator. You cannot build new levels, add new geometry, or place objects freely.
- Editing is currently limited to three early-game level segments (`intro_10`, `intro_15`, and `intro_20`), with different capabilities available in each.
- Many objects cannot be moved, for example those positioned by the game's scripts. The editor marks them as locked.
- Edits labeled **experimental** have not been tested in the game. Their in-game behavior, including some route (waypoint) changes, may differ from what you expect.
- Terrain editing is limited to a small area of one level.
- The 3D viewer's editing interface is still rough. The Classic editor remains available for the same levels.
- Gameplay-changing mods prevent new achievements while enabled.

## Original PC saves (experimental converter)

Save files from the original Rayman 3: Hoodlum Havoc PC release (2003) cannot be copied into Rayman 3 HD Recompiled directly; the two games store their saves differently. The optional `Rayman3HDRecompiled-1.2.0-pc-save-converter.zip` on the release page converts a PC save (`.sav`) into an existing save slot of this port on Windows.

The converter is experimental and has only been validated with a limited number of PC saves.

1. Back up your `profiles` folder (installed edition: `%LOCALAPPDATA%\Rayman3HDRecomp\profiles`; portable edition: `profiles` in the extracted folder).
2. Start the game, choose **New Game**, confirm a player name, then quit. The converter requires an existing save slot created by the game.
3. Extract the converter ZIP. If using the portable edition, place `R3SaveConverter.exe` in the extracted portable folder (the one containing `profiles`).
4. With the game closed, launch `R3SaveConverter.exe`, select your original PC `.sav` file, review the detected progress, and confirm the destination slot. The selected HD save slot will be replaced, but the converter creates a backup in `save_converter_backups` first. The original PC save is not modified.
5. Start the game, choose **Load**, and select the converted slot.

PC key bindings and option settings are not transferred, and progress towards some achievements starts again.

See the `README.md` included in the converter ZIP for command-line usage (Python 3.8 or newer), additional details, and known limitations.

## Troubleshooting

**The game package is rejected.** Only the supported original Xbox Live Arcade release, without a title update, is accepted. Other versions cannot be used interchangeably.

**Settings reports missing components.** Follow the message shown in Settings. On Windows, check the Visual C++ Redistributable or repair installation. On Linux, check Python/Tkinter and the desktop libraries listed above.

**Cutscene subtitles are missing.** Enable Subtitles in the original game's Options → Audio menu.

**Keyboard controls are different from expected.** Check Settings → Controls. Existing key bindings are preserved during upgrades.

**The game closes unexpectedly.** Diagnostic files are stored under `sessions\<date-time>\` in the installation folder. On Windows, each play session also writes `support_report.txt` there; attach it to your bug report. Check it before sharing: automatic redaction may not remove all personal information.

**Achievements are not unlocking.** A mod that changes gameplay, such as a level remix, is enabled. Disable it in Settings → Mods.

**The 3D Level Viewer does not open.** Check the message shown in Settings. The viewer uses OpenGL through your graphics driver. The Classic / Advanced Editor remains available.

**Reporting bugs:** Open an issue on the project's [Issues page](https://github.com/MysteriousAeon/rayman3-hd-recompiled/issues). Include the release version, Windows or Linux, installer or portable edition, graphics card, controller, and the steps that lead to the problem.

## Known limitations

- The game was completed from beginning to end during Windows human playtesting of v1.0.1. Automated regression and installation testing is also performed for subsequent releases, but a separate full playthrough of every release has not been completed.
- Hardware compatibility testing is limited. The port has been exercised on the developer's Windows 11 and CachyOS systems and in limited external testing; this does not establish compatibility with every GPU, driver, controller, or display configuration.
- Some visual differences and issues inherited from the Xbox 360 HD release remain. HD+ addresses several of these, including the Clearleaf sky, Bog of Murk clouds, and lighting colors in Hoodlum Headquarters and the Tower of the Leptys.
- A rare audio-initialization crash has been observed during testing. Its cause has not been established.
- Holding Walk while swimming may prevent forward movement. Release Walk to continue swimming.
- On Linux, animations may slow down while navigating the in-game pause menu.
- Changing Windows display scaling while Settings is open can leave a minor visual artifact. Reopening Settings resolves it.
- Button prompts are chosen when the game starts and do not switch while it is running.
- The level remix tools are experimental, Windows-only, and limited to three levels; see the section above.
- The PC save converter is experimental and optional. It has been tested with a small number of PC saves; compatibility with every PC save is not established.
- The Linux pre-release remains at v1.1.0 and does not include the changes introduced in later Windows releases.

The HD+ Robo-Pirate statue texture correction has been checked in gameplay.

## Building from source

The repository contains the port's source code, tools, and configuration. Building locally requires your own supported Xbox 360 game package and the project's pinned toolchain.

The game-derived machine code is generated locally. Generated game translations and proprietary game assets are not included in the source repository.

See [docs/BUILDING.md](docs/BUILDING.md) and `tools/build_milestone8.bat` for the Windows build procedure. The Linux download includes `BUILDINFO.json` with its source, toolchain and binary provenance; its LGPL source archive includes separate library rebuild instructions.

External technical references used during development are described in [docs/PROVENANCE.md](docs/PROVENANCE.md).

## Acknowledgments and licences

Rayman 3 HD Recompiled builds upon the work of several open-source projects:

- [ReXGlue SDK](https://github.com/rexglue/rexglue-sdk) (BSD-3-Clause), including code derived from [Xenia](https://xenia.jp).
- [XenonRecomp](https://github.com/hedge-dev/XenonRecomp) and [Unleashed Recompiled](https://github.com/hedge-dev/UnleashedRecomp), which served as references during development.
- FFmpeg (LGPL-2.1-or-later) and libmspack (LGPL-2.1), distributed as replaceable libraries with corresponding source archives.
- SDL 3, Dear ImGui, {fmt}, spdlog, xxHash, toml++, disruptorplus, DirectXShaderCompiler, CPython, and other dependencies.

Special thanks to the developers and contributors of these projects for making their work available to the community.

For complete third-party acknowledgments and licensing information, see the [Windows notices](tools/installer/THIRD_PARTY_NOTICES.txt) or [Linux notices](tools/linux/THIRD_PARTY_NOTICES.txt) and the licence files included with the application.

The project's original source code is licensed under the [MIT licence](LICENSE). Third-party components retain their respective licences. The MIT licence does not cover the game, code translated from it or translations of its text; the Scope section of [LICENSE](LICENSE) lists these exclusions.

Rayman 3 HD and its associated intellectual property belong to their respective rights holders.

## Star History

<a href="https://www.star-history.com/?repos=mysteriousaeon%2Frayman3-hd-recompiled&type=date&legend=top-left">
 <picture>
   <source media="(prefers-color-scheme: dark)" srcset="https://api.star-history.com/chart?repos=mysteriousaeon/rayman3-hd-recompiled&type=date&theme=dark&legend=top-left" />
   <source media="(prefers-color-scheme: light)" srcset="https://api.star-history.com/chart?repos=mysteriousaeon/rayman3-hd-recompiled&type=date&legend=top-left" />
   <img alt="Star History Chart" src="https://api.star-history.com/chart?repos=mysteriousaeon/rayman3-hd-recompiled&type=date&legend=top-left" />
 </picture>
</a>
