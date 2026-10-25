# Building Rayman 3 HD Recompiled from source

This guide builds the game executable and its runtime on your own Windows PC from your own copy of the game.
Nothing of the game is in this repository: the game's code is translated locally, from your `Default.xex`, during
the build. The translated code, the extracted game files and every build output stay on your PC (under the
ignored `private/` and `external/` folders) and must not be shared.

Most players do not need this: the setup on the Releases page does the same work for you.

## What you need

- Windows 10 or 11, 64-bit.
- Your own Rayman 3 HD package for Xbox 360: the original Xbox Live Arcade release (title ID `5841123F`),
  without a title update, copied from your console's storage.
- The toolchain the project is built with. These are the versions it has been built with; other versions may work,
  but are not tested (`config/build/toolchain.json` records them):
  - [LLVM](https://github.com/llvm/llvm-project/releases) 23.1.3 (clang++), default path `C:\Program Files\LLVM\bin`
  - Visual Studio Build Tools 18 with the C++ build tools (MSVC 14.50) and the Windows SDK 10.0.26100; this also
    provides Ninja
  - CMake (4.3.2 observed)
  - Python 3.11 or later
  - Git
- About 4 GB of free disk space (SDK checkout and build, extracted game files, generated code) and a network
  connection for the SDK download.

If LLVM or the Build Tools are installed somewhere else, set `R3HD_LLVM_BIN` (the folder with `clang++.exe`) or
`R3HD_VCVARS` (the full path of `vcvars64.bat`) before building.

## 1. Fetch the pinned ReXGlue SDK

```bash
python tools/r3hd_bootstrap.py all
```

This clones [ReXGlue SDK](https://github.com/rexglue/rexglue-sdk) into `external/rexglue-sdk` at the commit
pinned in `config/build/toolchain.json`, checks out its submodules at their recorded commits, replaces the
libmspack symlinks with copies (Windows checks them out as text files) and configures it. It never resets or
deletes an existing checkout; a directory at another commit is refused with a reason. No key, firmware or game data
is downloaded. `python tools/r3hd_bootstrap.py plan` shows what it would do without changing anything.

## 2. Extract your game package

```bash
python tools/r3hd_intake.py extract PATH\TO\YOUR\PACKAGE C:\R3HD\data
```

The intake identifies the package, checks all 915 files against the supported release and writes them to
`C:\R3HD\data\content`. Your package is only read. Any other version is refused.

## 3. Build

```bat
set R3HD_GAME_DIR=C:\R3HD\data\content
set R3HD_BUILD_MODE=user
cmd /c tools\build_milestone8.bat
```

The build patches the SDK, builds it, translates `Default.xex` into C++ under `private/work/rex/generated`, compiles
`r3hd.exe` and runs the project's tests. It ends with `M8_BUILD_OK`. In user mode the generated code must match the
digest pinned in `config/build/toolchain.json`; a different result stops the build with `CODEGEN_DIFFERENT`
before anything is compiled. `R3HD_JOBS` sets the number of parallel compile jobs.

`python tools/r3hd_build_doctor.py` checks the toolchain, the SDK and the game data before or after a build, and
says what is missing.

The `reports/` folder holds only data the build and the tools read: the supported release's file manifest, the
title's import and exception tables and the pinned target audit. They contain names, addresses, sizes and hashes,
no game code or data.

Tests that need the game data at the developer location (`private/extracted/5841123F`) print `SKIP` lines when it
is elsewhere; that is expected.

## 4. Play the local build

```bash
python tools/r3hd_paths.py init-home %LOCALAPPDATA%\Rayman3HDRecomp --preset hdplus
python tools/r3hd_paths.py install --home %LOCALAPPDATA%\Rayman3HDRecomp
powershell -ExecutionPolicy Bypass -File tools\play.ps1 -UserHome %LOCALAPPDATA%\Rayman3HDRecomp -GameDir C:\R3HD\data\content
```

`init-home` creates a home for settings, saves and logs (`--preset vanilla` for the Xbox 360 presentation),
`install` copies the built executable and libraries into it, and `play.ps1` starts the game. The comment at the top
of `tools/play.ps1` lists its options.

## The Windows setup

The setup on the Releases page is built by `tools/m50_build.py` from a finished build. That step also needs
Inno Setup and the separately distributed Turkish translation mod, and is not needed to play a local build.

## Licences

The project's own files are MIT-licensed; the Scope section of [LICENSE](../LICENSE) lists what the licence does not
cover. The ReXGlue SDK and its submodules keep their own
licences. The LGPL components (FFmpeg, libmspack) are built as separate, replaceable DLLs;
`tools/installer/LGPL-SOURCE.txt` says how to rebuild them.
