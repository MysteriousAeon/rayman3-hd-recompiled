# Rayman 3 HD Recompiled v1.3.1

This Windows maintenance update improves audio reliability when changing playback devices and during audio-client shutdown. It also adds more information to local support reports when the requested rendering resolution cannot be used.

## Audio Reliability

- **Playback-device switching:** Fixed an issue that could cause a crash when changing the default Windows audio output while multiple audio clients were active.
- **Audio-client shutdown:** Fixed race conditions that could cause crashes or other unexpected behavior when an audio client closes while audio is still being processed.

## Reliability & Diagnostics

- **Rendering resolution fallback:** When the requested rendering resolution cannot be used and the game falls back to a lower scale, the Windows launcher now shows a notice after the session ends.
- Local `support_report.txt` files now include rendering-scale and fallback details, helping diagnose display-related issues. Existing automatic redaction is preserved; please review reports before sharing them.

## Updating from v1.3.0

Close the game, Settings, and any level editor before updating.

**Installer:** Run the new setup and select your existing installation folder. Your saves, settings, mods, and preferences are preserved.

**Portable ZIP:** Extract the new package to a fresh writable folder. Follow the included `PORTABLE.txt` instructions to move your settings, profiles, saves, and mods from your previous portable copy.

Backing up your settings and profiles before updating is recommended.

The installer and portable edition require your own supported Xbox 360 Rayman 3 HD package (title ID `5841123F`, without a title update). **No game files are included.**

## Release Assets

- `Rayman3HDRecompiled-1.3.1-setup.exe` — Windows installer
- `Rayman3HDRecompiled-1.3.1-portable.zip` — Windows portable archive (includes required Visual C++ runtime libraries)
- `r3hd-lgpl-source-1.3.1.zip` — Corresponding LGPL library source code
- `rayman3hd-turkish-1.0.1.zip` — Optional Turkish translation package (unchanged)
- `Rayman3HDRecompiled-1.2.0-pc-save-converter.zip` — Optional experimental PC save converter (unchanged)
- `SHA256SUMS.txt` — SHA-256 checksums for the release files

## Additional Notes

- The game continues to run at 60 FPS. Rendering resolution options remain Auto, 720p, 1440p, and 2160p. No new rendering modes or gameplay changes are introduced.
- The audio fixes have passed targeted regression tests and Windows playtesting. This does not establish that every rare historical crash has been eliminated; an unrelated audio-initialization crash remains under investigation.
- The optional Turkish translation package remains v1.0.1, with unchanged contents. The PC save converter remains experimental and has been validated with a limited number of saves.
- Some issues inherited from the Xbox 360 HD release remain.
- This is a Windows-only update. The experimental Linux pre-release remains at v1.1.0 and does not include these changes. Steam Deck compatibility has not been officially verified.
