Rayman 3 HD Recompiled - Linux portable edition
=============================================

This is the native Linux port of Rayman 3 HD Recompiled 1.1.0, initially offered
as a pre-release. No game files are included. Use your own legally obtained Xbox
360 Rayman 3 HD package (title ID 5841123F), without a title update.

Requirements
------------
- An x86-64-v2 capable CPU and a 64-bit Linux desktop, Wayland or X11.
- glibc 2.38 or newer; libstdc++ providing GLIBCXX_3.4.32 or newer.
- Vulkan 1.2+ drivers with the required device features, and desktop client
  libraries libX11.so.6, libX11-xcb.so.1, libxcb.so.1, libwayland-client.so.0.
  Use your distribution's graphics driver and Vulkan loader.
- Python 3.10 or newer. Tkinter is needed for graphical setup and Settings;
  --console uses the same setup/settings engine in a terminal.
- A working desktop audio service (PulseAudio or PipeWire's PulseAudio service).
- Approximately 2.3 GB for installation, plus space for caches and your mods.

Built against Ubuntu 24.04; tested on CachyOS, KDE Wayland and NVIDIA graphics.

First launch
------------
Extract the whole archive into a new writable folder. Open a terminal there:

  ./Settings.sh

Choose your supported Xbox 360 package (or verified extracted game-data folder),
then Vanilla, HD+ (Recommended) or Custom. The original package is only read.
Setup checks/extracts the data and offers application-menu entries. It finishes
without launching anything automatically. Choose Play or Open Settings yourself.
Starting with ./Play.sh performs the same first-run setup if needed.

Later starts:

  ./Play.sh       Start with saved settings and enabled mods.
  ./Settings.sh   Configure the game and manage mods.

No administrator access or development toolchain is needed. These commands use
system Python and desktop libraries; the package downloads nothing. In a file
manager, choose to execute the shell script rather than edit it.

Settings and controls
---------------------
Settings, presets and Mods use the same engine as the Windows release. Changing
profile keeps independent display, control and language preferences. The Mods
tab installs local ZIPs/folders, enables/disables them and changes their order.
Imports start disabled. Restart the game after changing mod selections.
Gameplay subtitles are under Settings > Display. HD+ starts with them enabled.
The game's cinematic Subtitles option is separate (Options > Audio).
F4 opens PC Settings in game. Normal Play suppresses SDK development overlays.
Stored keyboard/controller mappings are preserved; the Linux Settings window
does not yet include the Windows binding editor. DualSense options are under
Advanced; controller-speaker effects require USB and start off. Discord presence
and the Windows save-history keeper are not part of this port.

Your files
----------
Everything portable stays beside Play.sh:
  settings.json             Preferences, presets and stored mappings
  profiles/<name>/user/     Saves and achievements
  mods/                    Installed data mods
  data/content/            Verified game data
  cache/, sessions/        Runtime caches and bounded diagnostic logs
  installer.json, r3hd_home.json   Local setup state
  app/, bin/               Program files

Back up user files before updating. Extract a new release into a fresh folder
and complete setup; keep the previous copy until you have moved your chosen
profile/settings/mods deliberately. Do not merge old app/ or bin/ files into it.
There is no system installer/uninstaller. Application-menu entries can be added
or removed in Settings. Keep backups before removing an old portable folder.

Known issue and troubleshooting
------------------------------
Animations may slow down while navigating the in-game pause menu.
Full-game compatibility testing is ongoing.
If setup rejects the package, check the original Xbox Live Arcade release/title
ID and absence of a title update. Do not bypass the integrity check.
If the GUI is unavailable, check Python/Tkinter or use ./Settings.sh --console.
If desktop audio fails to initialize, the tested PulseAudio-compatible route is:

  SDL_AUDIO_DRIVER=pulseaudio ./Play.sh

An unavailable audio device can cause startup to fail. Logs are in sessions/;
review them for private information before sharing.

LGPL libraries and notices
-------------------------
bin/libffmpeg.so and bin/libmspack.so are replaceable LGPL libraries. The matching
source download is r3hd-lgpl-source-1.1.0-linux-x86_64.zip, distributed beside this
package. Build/replacement instructions are in app/licenses/LGPL-SOURCE.txt.
Keep that notice and the license texts. Other program files are integrity checked;
do not edit manifests to bypass verification.
See app/THIRD_PARTY_NOTICES.txt and the accompanying BUILDINFO.json for dependency
notices and exact binary/source/toolchain provenance.
