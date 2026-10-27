# Rayman 3 HD Recompiled

A native Windows port of **Rayman 3 HD** for Xbox 360. The game's code has been statically recompiled to run directly on a PC, without an emulator.

The installer uses your own Xbox 360 game package to set up the game on Windows.

**No game files are included.** You need your own, legally obtained copy of Rayman 3 HD for Xbox 360.

This is an independent fan project and is not affiliated with or endorsed by Ubisoft or Microsoft. Rayman 3 HD and related trademarks belong to their respective owners.

## Why this project exists

Rayman 3 was one of my favorite games growing up, and I wanted my wife to experience it too. I wanted her to be able to play it in Turkish, so I started working on a way to make that possible. What began as a personal project eventually grew into a native PC port of the Xbox 360 HD version.

## Features

- **Native Windows port:** Play the Xbox 360 HD version without running an emulator.
- **HD+ enhancements:** Optional visual corrections, alongside Vanilla and Custom profiles.
- **Turkish translation:** An optional localization covering game text, menus, subtitles, and achievement descriptions.
- **Keyboard and controller support:** Two keyboard layouts with customizable key bindings, plus Xbox-compatible controllers.
- **DualSense enhancements:** Dynamic lightbar colors based on the game world and power-ups, with adjustable R2 adaptive trigger resistance.
- **Achievements:** In-game achievement tracking and notifications, with Turkish text when the translation mod is enabled.
- **Discord Rich Presence:** Optional Discord activity integration.
- **Mod support:** Install and manage compatible texture, text, font, and subtitle mods through Settings.
- **Integrated setup and settings:** Import your game package, configure the port, and preserve your preferences across updates.

## Requirements

- Windows 10 or 11, 64-bit
- [Microsoft Visual C++ Redistributable 2015–2022 (x64)](https://aka.ms/vs/17/release/vc_redist.x64.exe)
- A graphics card with Direct3D 12 support
- Approximately 2.3 GB of free disk space
- Your own Xbox 360 Rayman 3 HD package: the original Xbox Live Arcade release (title ID `5841123F`), **without a title update**, copied from your console's storage

## Installation

1. Copy the game package from your Xbox 360 to your PC. It is the file located under `Content\0000000000000000\5841123F\000D0000\` on your console's storage.
2. Download `Rayman3HDRecompiled-<version>-setup.exe` from the project's Releases page and run it. Administrator privileges are not required.
3. Select English or Türkçe, choose an installation folder, and provide your Xbox 360 game package. The installer validates the package against the supported release. Your original package is only read, never modified.
4. On the final page, select **Launch Rayman 3 HD Recompiled** to start the game, or **Open Settings** to configure it.

The game and Settings can also be launched from the Start menu or optional desktop shortcuts.

### Updating, repairing, and uninstalling

**Update or repair:** Run the setup again and select the same installation folder. Your saves, settings, and mods are preserved. If the installed game files are intact, you do not need to select the original package again.

**Uninstall:** Use Windows Settings → Apps or the uninstaller in the installation folder. Saves, settings, and mods are kept unless you explicitly choose to delete them.

### Settings language

Settings is available in English and Turkish. Use **Interface language / Arayüz dili** in the upper-right corner to change it.

A fresh installation follows the language selected during setup. Updates preserve your existing preference.

This setting changes only the Settings interface. The game's language is controlled separately through the Turkish translation mod.

**Türkçe kurulum rehberi:** [docs/KURULUM.md](docs/KURULUM.md)

## Controls

Xbox-compatible controllers use the Xbox 360 button layout. For keyboard controls, choose between two layouts in Settings → Controls. Individual keyboard bindings can be customized. Controller mappings are available on the Controller tab.

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

In Settings → Controls → Controller, capture a button to reassign it. Digital buttons swap with digital buttons, triggers with triggers, and sticks with sticks. One map applies to physical controllers; keyboard bindings remain independent. Xbox-compatible controllers and native DualSense are supported, with physical DualSense Bluetooth acceptance recorded; other device configurations have limited testing. Guide / PS and the touchpad cannot be assigned. Existing saved keyboard choices take precedence over updated defaults.

## Game profiles: Vanilla, HD+, and Custom

Choose a profile under Settings → Game profile:

- **Vanilla:** Preserves the Xbox 360 release's presentation, with compatibility fixes necessary for native Windows execution.
- **HD+:** Includes Vanilla functionality plus optional corrections for visual issues in the Xbox 360 HD release.
- **Custom:** Allows you to choose individual corrections.

Changing the game profile does not reset display, control, or advanced settings. Changes take effect the next time the game starts.

### Subtitles

For cinematic subtitles, enable the original game's **Subtitles** setting under Options → Audio. This option starts disabled on a new game profile.

The separate **Gameplay subtitles** option under Settings → Corrections enables subtitles for voiced dialogue during gameplay.

Fresh HD+ installations start with Gameplay subtitles enabled; fresh Vanilla installations start with it disabled. Your subsequent preference is preserved independently of profile changes.

## Turkish translation / Türkçe yama

The game can be played in Turkish using the optional translation mod.

- **Turkish setup:** Installs and enables the translation.
- **English setup:** Does not install the translation automatically, but includes its ZIP in the installation's `extras\` folder.
- **Adding the translation later:** Open Settings → Mods → Install .zip and choose `extras\rayman3hd-turkish-1.0.1.zip`.
- **Switching back to English:** Disable the translation under Settings → Mods.
- **Updating:** Your existing translation preference is preserved. A mod you disabled remains disabled, and one you removed is not automatically reinstalled.

The translation covers the game's menus, dialogue, subtitles, and achievement text. It has received additional human localization review and corrections for this release.

For complete Turkish instructions, see the [Türkçe Yama guide](docs/turkce-yama.md).

## DualSense enhancements

Native DualSense controllers can use additional features when supported by the connection and controller configuration:

- **Dynamic lightbar colors:** The lightbar changes according to the current game world and active power-up.
- **Adaptive R2 trigger:** Adds resistance to the R2 trigger during eligible gameplay.
- **Adjustable strength:** Use Settings → Advanced → Adaptive Trigger Strength to choose a value from 0% to 100%.

The default strength is **30%**. Selecting **0%** disables the trigger resistance.

Lightbar and adaptive trigger effects can be disabled independently. Both are enabled by default on fresh installations; previously saved choices are preserved.

Settings changes take effect the next time the game starts.

These features require access to a supported physical DualSense. Steam Input or virtual controller configurations may prevent them from being available.

## Achievements and Discord

The port includes an in-game achievement interface. Achievement titles and descriptions can appear in Turkish when the translation mod is enabled.

**Discord Rich Presence** can display your game activity in Discord. It is enabled by default for new installations and can be disabled in Settings.

Neither feature requires Xbox Live connectivity.

## Mods

Settings → Mods lets you install compatible mods, enable or disable them, and change their priority.

Supported data modifications include:

- Textures
- Text and font glyphs
- Subtitles

Mods cannot currently replace game models, levels, audio, scripts, or executable code.

Mods are checked against the supported game files to reduce the risk of applying incompatible data.

To create a compatible mod, see [MODDING.md](tools/installer/MODDING.md), also included in the installed application's `app\` folder.

## Troubleshooting

**The game package is rejected.** Only the supported original Xbox Live Arcade release, without a title update, is accepted. Other versions cannot be used interchangeably.

**Settings reports missing components.** Follow the message shown in Settings. You may need the Visual C++ Redistributable or a repair installation.

**Cutscene subtitles are missing.** Enable Subtitles in the original game's Options → Audio menu.

**Keyboard controls are different from expected.** Check Settings → Controls. Existing key bindings are preserved during upgrades.

**The game closes unexpectedly.** Diagnostic files are stored under `sessions\<date-time>\` in the installation folder. Include the relevant session logs when reporting a bug, after checking them for information you do not wish to share.

## Known limitations

- The game has been completed from beginning to end on version 1.0.1 during human playtesting. The final installer candidate has also passed automated runtime and installation checks, but a separate full playthrough on that exact candidate has not been performed.
- Hardware compatibility testing is limited. The port has been exercised on the developer's Windows 11 system and in limited external testing; this does not establish compatibility with every GPU, driver, controller, or display configuration.
- Some visual issues inherited from the Xbox 360 HD release remain, including examples involving the Clearleaf sky and certain Hoodlum HQ scenes.
- A rare audio-initialization crash has been observed during testing. Its cause has not been established.
- Holding Walk while swimming may prevent forward movement. Release Walk to continue swimming.
- Changing Windows display scaling while Settings is open can leave a minor visual artifact. Reopening Settings resolves it.

The HD+ Robo-Pirate statue texture correction has been checked in gameplay.

## Building from source

The repository contains the port's source code, tools, and configuration. Building locally requires your own supported Xbox 360 game package and the project's pinned toolchain.

The game-derived machine code is generated locally. Generated game translations and proprietary game assets are not included in the source repository.

See [docs/BUILDING.md](docs/BUILDING.md) and `tools/build_milestone8.bat` for the current development/build procedure.

External technical references used during development are described in [docs/PROVENANCE.md](docs/PROVENANCE.md).

## Acknowledgments and licences

Rayman 3 HD Recompiled builds upon the work of several open-source projects:

- [ReXGlue SDK](https://github.com/rexglue/rexglue-sdk) (BSD-3-Clause), including code derived from [Xenia](https://xenia.jp).
- [XenonRecomp](https://github.com/hedge-dev/XenonRecomp) and [Unleashed Recompiled](https://github.com/hedge-dev/UnleashedRecomp), which served as references during development.
- FFmpeg (LGPL-2.1-or-later) and libmspack (LGPL-2.1), distributed as replaceable libraries with corresponding source archives.
- SDL 3, Dear ImGui, {fmt}, spdlog, xxHash, toml++, disruptorplus, DirectXShaderCompiler, CPython, and other dependencies.

Special thanks to the developers and contributors of these projects for making their work available to the community.

For complete third-party acknowledgments and licensing information, see [THIRD_PARTY_NOTICES.txt](tools/installer/THIRD_PARTY_NOTICES.txt) and the licence files included with the application.

The project's original source code is licensed under the [MIT licence](LICENSE). Third-party components retain their respective licences. The MIT licence does not cover the game, code translated from it or translations of its text; the Scope section of [LICENSE](LICENSE) lists these exclusions.

Rayman 3 HD and its associated intellectual property belong to their respective rights holders.