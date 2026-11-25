# Rayman 3 HD Recompiled v1.4.0

This Windows update adds **native 1080p rendering** and an optional HD+ correction for Grand Minimus's crown. The new rendering resolution is available alongside the existing 720p, 1440p, and 2160p options, without changing how Auto selects a resolution.

## Rendering Resolution

- **Native 1080p (1.5x):** Added a manual **1920x1080 (1.5x)** option under **Settings → Display → Rendering resolution**. Unlike scaling a 720p image to a 1080p window, this renders the game at 1080p using Direct3D 12 on Windows.
- **Auto remains unchanged:** Auto continues to choose between 720p, 1440p, and 2160p based on the visible game area. On a 1080p display, Auto still selects 1440p; select 1080p manually if you prefer it.
- **Compatibility:** Native 1080p rendering works with Vanilla, HD+, and Custom profiles on Windows.

## HD+ Improvements

- Added **Correct Grand Minimus's Crown** under **Settings → Corrections**. This fixes the crown's overlapping surfaces so the back no longer shows through the front.
- The correction is enabled by default in **HD+**, disabled in **Vanilla**, and can be configured individually in **Custom**.
- Updated the English and Turkish Settings interfaces for the new options.

## Updating from v1.3.1

Close the game and Settings before updating.

**Installer:** Run `Rayman3HDRecompiled-1.4.0-setup.exe` and select your existing installation folder. Existing saves, mods, settings, and preferences are preserved.

**Portable ZIP:** Extract `Rayman3HDRecompiled-1.4.0-portable.zip` to a new writable folder. Follow the included `PORTABLE.txt` instructions to move your settings, saves, and mods from the previous portable copy.

Backing up your settings and profiles before updating is recommended.

The installer and portable edition require your own supported Xbox 360 Rayman 3 HD package (title ID `5841123F`, without a title update). **No game files are included.**

## Downloads

| File | Description |
|---|---|
| `Rayman3HDRecompiled-1.4.0-setup.exe` | Windows installer (English / Türkçe) |
| `Rayman3HDRecompiled-1.4.0-portable.zip` | Windows portable edition |
| `rayman3hd-turkish-1.0.1.zip` | Optional standalone Turkish translation |
| `Rayman3HDRecompiled-1.2.0-pc-save-converter.zip` | Experimental converter for original PC saves |
| `r3hd-lgpl-source-1.4.0.zip` | Corresponding LGPL library source code |
| `SHA256SUMS.txt` | SHA-256 checksums for the release files |

## Additional Notes

- The game continues to run at 60 FPS. No new levels or gameplay mechanics are introduced.
- The optional Turkish translation remains at v1.0.1, and the experimental PC save converter remains at v1.2.0; their contents are unchanged.
- Native 1080p rendering was tested in representative levels throughout the campaign, but a separate full-game playthrough at 1.5x and compatibility across all graphics hardware have not been verified. Unsupported fractional-rendering operations may cause the game to close rather than display incorrectly.
- This is a Windows release. The experimental Linux pre-release remains at v1.1.0 and does not include these changes.

For installation instructions, additional known limitations, and source build information, see the [project README](https://github.com/MysteriousAeon/rayman3-hd-recompiled#readme).
