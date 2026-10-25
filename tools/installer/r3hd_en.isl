; M48-P (D-087): English texts of tools\installer\r3hd_setup.iss (with Inno Setup's Default.isl). The English-only
; setup uses these alone; the bilingual setup also has r3hd_tr.isl (M49: consumer wording). Keep the two files key for key.

[Messages]
WelcomeLabel2=This installs Rayman 3 HD Recompiled, a native Windows version of the Xbox 360 game, made from your own copy of the game.%n%nYou need:%n  - your own Rayman 3 HD package for Xbox 360 (the original Xbox Live Arcade release, without title update), copied from your console;%n  - Windows 10 or 11 (64-bit) with the Microsoft Visual C++ Redistributable 2015-2022 (x64);%n  - about 2.3 GB of free space.%n%nYour package is only read, never changed, and every game file is checked. No administrator rights are needed.
FinishedLabel=Rayman 3 HD Recompiled is installed.%n%nYou can start the game from the desktop or the Start menu.

[CustomMessages]
TaskGroup=Shortcuts:
TaskDesktop=Create a &desktop shortcut (Play)
TaskSettings=Create a desktop shortcut for &Settings (display, graphics, keyboard)
PlayComment=Play with your saved settings
SettingsComment=Display, graphics, keyboard and game profile
RunPlay=Launch Rayman 3 HD Recompiled
RunSettings=Open Settings

EngineFailed=The installer engine failed (exit code %1).
EtaEstimating=estimating the time left...
EtaUnderMinute=less than a minute left
EtaMinute=about a minute left
EtaMinutes=about %1 minutes left
Step_payload=Copying the application
Step_extract=Extracting the game files from your package
Step_check=Checking your game files
Step_copy=Copying your game files
Step_verify=Checking every extracted game file
Step_commit=Finishing the installation
Preparing=Preparing
Cancelling=Cancelling... the files prepared so far are removed; nothing is changed.
CancelConfirm=Cancel the installation?%n%nNothing is changed in the installation folder; the files prepared so far are removed.
DetailFiles=%1 of %2 files
DetailMB=%1 of %2 MB
VcMissing=The Microsoft Visual C++ Redistributable 2015-2022 (x64) is missing.%nInstall it from Microsoft (aka.ms/vs/17/release/vc_redist.x64.exe), then run this installer again.
PayloadFailed=The installer's own files could not be unpacked.

PackageTitle=Your game package
PackageDesc=Select your own Rayman 3 HD package for Xbox 360.
PackageText=Click Browse and select the single Xbox 360 Xbox Live Arcade package file copied from your console: Content\0000000000000000\5841123F\000D0000\... The file usually has a long hexadecimal name and no extension. Select the file itself, not its folder, an ISO, a ZIP or a PC copy of the game. Setup checks that it is the supported Rayman 3 HD package and extracts the game files; your original is never changed. For an update or repair, leave this empty if the installed game files are intact.
PackageLabel=Package file:
PackageFilter=All files|*.*
VerifyBox=Check every installed game file (repair; about a minute)
PackageNeeded=Select your Rayman 3 HD package: the game files are extracted from it.
PackageUnusable=This package cannot be used.

PresetTitle=Game profile
PresetDesc=How should the game look? You can change this at any time in Rayman 3 HD Settings.
PresetText=Display and graphics options, such as fullscreen and the rendering resolution, are set in Rayman 3 HD Settings after installation; nothing about them needs to be decided now.
PresetVanilla=Vanilla - the Xbox 360 release, with the fixes it needs on PC
PresetHdplus=HD+ (Recommended) - Vanilla plus fixes for visual mistakes of the Xbox 360 release
PresetCustom=Custom - pick each correction yourself afterwards, in Rayman 3 HD Settings
PresetKeep=Keep my current settings (existing installation)

ProgressTitle=Installing
ProgressDesc=Rayman 3 HD Recompiled is being installed. The game files are extracted from your package and every file is checked.
CancelInstallButton=&Cancel installation
InstallCancelled=The installation was cancelled. Nothing was changed in the installation folder.
CancelTooLate=The installation had already reached its last step when you cancelled, so it was completed.
NothingChanged=Nothing was changed in the installation folder.
FinishedBase=Rayman 3 HD Recompiled is installed.%n%nYou can start the game from the desktop or the Start menu.

MemoFolder=Installation folder:
MemoExisting=(existing installation: update / repair; saves and settings are kept)
MemoGameFiles=Game files:
MemoChecked=(checked; every file is checked again during installation)
MemoKeepFiles=keep the installed game files
MemoProfile=Game profile:
MemoDisplay=Display and graphics:
MemoDisplayLater=change them at any time in Rayman 3 HD Settings
MemoSpace=Space needed: about 2.3 GB (game files 2.1 GB, application 70 MB).

UninstallRefused=Rayman 3 HD Recompiled cannot be uninstalled right now. Nothing was removed.
UninstallUserData=Also delete your saves, settings, mods and session logs?%n%nChoose No to keep them (recommended): a later installation into the same folder uses them again.
UninstallPartial=Some files were not removed: %1

; --- the bilingual setup (BundledMod) only ---
LangPageTitle=Setup language
LangPageDesc=Choose the language of this setup.
LangSwitchFailed=The setup could not be started in the other language (%1). You can continue in this language.

TurkishNoteFreshTr=The Turkish translation will be installed and turned on.
TurkishNoteFreshEn=The game will be installed in English.
TurkishNoteUpgrade=Installed now: version %1 (%2). It is updated to this setup's version and stays %2, in the same place in your mod list.
TurkishNoteSame=This version of the Turkish translation is already installed (%1); it stays as it is.
TurkishNoteNewer=A newer Turkish version (%1) is installed; it is kept and not replaced.
TurkishNoteDifferent=Another copy of this Turkish version is installed; it is kept and not replaced.
TurkishNoteAbsent=This installation has no Turkish translation, and it is not added now. You can add it in "Rayman 3 HD Recompiled - Settings" > Mods > Install .zip (the file is in the extras folder of the installation).
TurkishNoteUnknown=The installed mods of this folder could not be read; the Turkish translation is left as it is.
TurkishNotInstalled=The Turkish translation was not installed. The game shows its original English text.
StateOn=on
StateOff=off
MemoTurkish=Turkish translation:
StepTurkish=Adding the Turkish translation...
StepSubs=Saving the subtitle setting...
TurkishFailed=The game is installed, but the Turkish translation could not be added: %1
TurkishDoneOn=Turkish translation %1 is installed and turned on. To play in English, turn it off in "Rayman 3 HD Recompiled - Settings" > Mods.
TurkishDoneOff=Turkish translation %1 is installed and stays off, as you had it. Turn it on in "Rayman 3 HD Recompiled - Settings" > Mods.
SubsFailed=The subtitle setting could not be saved: %1
SubsDoneOn=Gameplay subtitles are on. Before your first play, open the game's options (Audio) and switch Subtitles on: a new game profile starts with them off.
SubsDoneOff=Gameplay subtitles are off (cutscene subtitles follow the game's own Subtitles option).
