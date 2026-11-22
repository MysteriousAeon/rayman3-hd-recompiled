# Rayman 3 HD Recompiled v1.3.0

This Windows update adds an optional Score HUD toggle, improves automatic rendering resolution selection, and introduces local support reports. It also includes fixes for controllers, game startup, Settings, and level remix tools.

## Controls & Settings

- **Score HUD toggle (F5):** Enable **Score HUD toggle (F5)** under **Settings → Corrections** to hide or show the score and Combo Meter during gameplay. Other HUD elements remain visible. This option is disabled by default.
- **Auto rendering resolution:** Auto now chooses the smallest supported resolution that covers the visible 16:9 game picture, excluding black bars on displays with other aspect ratios. For example, on a 1080p display, Auto selects 1440p. The manual 720p, 1440p, and 2160p options are unchanged.
- **Controller vibration:** Vibration motors now stop when the game closes.
- **Second-controller sign-in:** Fixed an issue where declining the sign-in prompt on a second controller could leave the sign-in flow stuck. The first controller continues to own the main profile and saves.
- Updated the Mods page layout so its controls fit at 1080p with 150% display scaling.

## Reliability & Diagnostics

- **Local support reports:** On Windows, each play session now creates a `support_report.txt` file in its `sessions\<date-time>\` folder. Settings points to this report after an unexpected exit. User names, computer names, and installation paths are automatically redacted, and crash dumps are not included. Please review the report before sharing it, as automatic redaction may not catch everything.
- Fixed game startup and diagnostic collection from installation paths containing square brackets (`[` or `]`).
- If Windows cannot start the game, Settings now explains the error in English or Turkish, records diagnostic information, and cleans up only files created by that launch attempt.

## Modding & Level Tools

- The level remix tools now ask for confirmation before replacing an installed mod with the same ID.
- Fixed an issue that could prevent an exported remix from opening again in the editor.

## Updating from v1.2.0

Close the game, Settings, and any level editor before updating.

**Installer:** Run the new setup and select your existing installation folder. Your saves, settings, mods, and preferences are preserved.

**Portable ZIP:** Extract the new package to a fresh writable folder. Follow the included `PORTABLE.txt` instructions to move your settings, profiles, saves, and mods from your previous portable copy.

Backing up your settings and profiles before updating is recommended.

The installer and portable edition require your own supported Xbox 360 Rayman 3 HD package (title ID `5841123F`, without a title update). **No game files are included.**

## Additional Notes

- The game continues to run at 60 FPS. Rendering resolution options remain Auto, 720p, 1440p, and 2160p.
- Controller button prompts in Auto mode are selected when the game starts. Restart the game after changing controllers.
- The optional Turkish translation package remains v1.0.1, with unchanged contents.
- The optional PC save converter remains experimental and has been validated with a limited number of saves.
- Some issues inherited from the Xbox 360 HD release remain. A rare audio-initialization crash is also still under investigation.
- This is a Windows-only update. The experimental Linux pre-release remains at v1.1.0 and does not include these changes. Steam Deck compatibility has not been officially verified.
