# Rayman 3 HD Recompiled v1.0.3

This update adds support for the Xbox 360 HD release's five built-in game languages, an optional Combo Meter closing animation, and a portable ZIP edition.

## Language Support

- Added a **Game Language** option under **Settings → Advanced**, with support for English, French, Spanish, Italian, and German.
- Game language selection uses the original Xbox 360 HD data, including localized text, subtitles, and available voice audio. No separate translation mod is required for these five languages.
- Language preferences are saved across launches and remain independent of the Settings interface language and game profile.
- Improved the modding tools to support explicit glyph overrides for characters missing from the original font mapping, including **œ/Œ**.

*Note: French menus, subtitles, and cinematic audio have been verified. Voice coverage throughout the full campaign has not been checked. The current Turkish and Brazilian Portuguese translation mods require English to be selected as the game language.*

## HD+ Improvements

- Added an optional **Combo Meter closing animation**, reusing an animation from the original game. The meter now slides upward during the final second of a combo instead of disappearing instantly.
- **Vanilla** preserves the original abrupt closing behavior.
- **HD+** enables the animation by default.
- **Custom** allows the animation to be enabled or disabled independently under **Settings → Corrections**.
- Combo Meter Animation preferences are saved across launches without resetting unrelated Custom settings.

## Portable Edition

- Added a **portable ZIP edition** alongside the Windows installer.
- Launch the portable game using `Play.cmd`, or open `Settings.cmd` to configure it.
- Portable settings, saves, profiles, and mods remain inside the extracted folder, independently of an installed copy.
- The complete portable folder can be moved to another writable location without requiring a new installation.
- Required Visual C++ runtime libraries are included in the portable package.

*Note: The portable edition requires 64-bit Windows 10 version 1903 or newer, or Windows 11. It has not been tested on a clean non-admin Windows machine.*

## Updating from v1.0.2

Close the game and Settings before updating.

**Installer:** Run the new setup and select your existing installation folder. Existing saves, mods, settings, and preferences are preserved.

**Portable ZIP:** Extract the new package to a writable folder. Follow the included `PORTABLE.txt` instructions when migrating data from an earlier portable copy.

**Backing up your settings and profiles before updating is strongly recommended.**

The installer and portable edition require your own supported Xbox 360 Rayman 3 HD package (title ID `5841123F`, without a title update). No game files are included.

## Additional Notes

- Added [PINHATT's Brazilian Portuguese translation](https://github.com/crispinhatt/Rayman3HD-Traducao-PTBR) to the README's Community Translations section. The mod is independently maintained and is not bundled with this release.
- The optional Turkish translation package remains **v1.0.1**, with unchanged contents.
- Some visual issues inherited from the Xbox 360 HD release remain. A rare audio-initialization crash has also been observed during testing.
- This is a Windows release. Linux and Steam Deck compatibility have not been officially verified. A separate full playthrough of v1.0.3 has not been performed.