Rayman 3 HD Recompiled
======================

Play:              Start menu "Rayman 3 HD Recompiled" (or app\r3hd_launcher.exe --play). Starts the game with your
                   saved settings.
Settings:          Start menu "Rayman 3 HD Recompiled - Settings" (or app\r3hd_launcher.exe).
                     Game profile   Vanilla = the Xbox 360 release with the fixes it needs on PC;
                                    HD+     = Vanilla plus fixes for visual mistakes of the Xbox 360 release;
                                    Custom  = pick each correction yourself.
                     Display        window or fullscreen; rendering resolution (Auto, 720p, 1440p, 2160p).
                     Controls       keyboard keys (Modern or Original PC keys; any key can be changed). Hold Walk
                                    (Ctrl in Modern, Shift in Original PC) while moving to walk slowly.
                     Mods           turn installed mods on or off, change their order, install a mod .zip.
                     Advanced       Settings language, mouse cursor, save times, Discord Rich Presence,
                                    DualSense light bar and R2 resistance (Adaptive Trigger Strength 0-100 %,
                                    0 % = off), diagnostics.
                   Display, controls and advanced settings stay the same when you change the profile. Settings apply
                   the next time the game starts. Nothing here changes your game files or saves.
Turkish:           the Turkish translation is a mod. A Turkish setup installs and turns it on; to add it later, use
                   Settings > Mods > Install .zip and choose the file in the installation's extras\ folder. Turn it
                   off there to play in English.
Subtitles:         a new game profile starts with the game's own Subtitles option off: switch it on once in the
                   game's Options (Audio). Subtitles for voiced lines during gameplay: Settings > Corrections >
                   Gameplay subtitles (on for a new HD+ installation, off for Vanilla); the choice stays when you
                   change the profile.
Command line:      app\play.cmd [options], e.g. app\play.cmd -Fullscreen -RenderScale 2. An option named here wins over
                   the saved settings for that launch. app\settings.cmd is a text-mode alternative to Settings.
Repair or update:  run the installer again and choose this folder. Your saves, settings and mods are kept.
Uninstall:         Windows Settings > Apps, or the uninstaller in this folder. Saves (profiles\), settings and mods
                   are kept unless you choose to delete them.
Problems:          the Settings window says what is missing and how to fix it. Each game session writes its
                   diagnostics to sessions\<date-time>\.
Making mods:       MODDING.md in this folder.

Folder layout
  app\        Settings, installer engine, configuration, Python runtime                    (installer-owned)
  bin\        r3hd.exe and its runtime libraries                                           (installer-owned)
  data\       the game files extracted from your package, verified file by file           (installer-owned)
  cache\      shader cache                                                                 (installer-owned)
  extras\     the Turkish translation (.zip), to add it later through Settings > Mods      (installer-owned)
  settings.json, profiles\ (saves), mods\, save_history\, sessions\ (diagnostics)         (yours: kept on uninstall)

Requirements: Windows 10 or 11 x64, the Microsoft Visual C++ Redistributable 2015-2022 (x64), a Direct3D 12 GPU,
about 2.3 GB of free space, and your own copy of Rayman 3 HD for Xbox 360 (Xbox Live Arcade release 0.0.0.1, no
title update), copied from your console's storage.

Third-party components and licences: THIRD_PARTY_NOTICES.txt and licenses\.
