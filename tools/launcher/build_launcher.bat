@echo off
rem M30 (D-067): build the Settings launcher, tools\launcher\r3hd_launcher.exe -> OUT (default private\work\launcher).
rem The pinned LLVM (clang-cl, lld-link, llvm-rc) with the MSVC libraries of config\build\toolchain.json; the C runtime
rem is linked statically, so the launcher can report a missing Visual C++ runtime instead of failing to start. No PDB
rem and /Brepro: the binary carries no build-machine path or time stamp. tools\build_milestone8.bat calls this; alone:
rem   cmd /c tools\launcher\build_launcher.bat [OUT]
rem Ends with LAUNCHER_BUILD_OK.
setlocal
cd /d "%~dp0..\.."
set "OUT=%~1"
if "%OUT%"=="" set "OUT=private\work\launcher"
if not defined R3HD_VCVARS set "R3HD_VCVARS=C:\Program Files (x86)\Microsoft Visual Studio\18\BuildTools\VC\Auxiliary\Build\vcvars64.bat"
if not defined R3HD_LLVM_BIN set "R3HD_LLVM_BIN=C:\Program Files\LLVM\bin"
if not exist "%R3HD_LLVM_BIN%\clang-cl.exe" echo LAUNCHER_BUILD_FAIL clang-cl.exe not found; set R3HD_LLVM_BIN & exit /b 1
if not defined VCToolsInstallDir (
  if not exist "%R3HD_VCVARS%" echo LAUNCHER_BUILD_FAIL vcvars64.bat not found; set R3HD_VCVARS & exit /b 1
  call "%R3HD_VCVARS%" >nul 2>&1
)
if not exist "%OUT%" mkdir "%OUT%" || exit /b 1
rem M31 (D-068): the project icon is drawn by tools\make_r3hd_icon.py into OUT (a build output, never committed).
python tools\make_r3hd_icon.py --out "%OUT%\r3hd.ico" || exit /b 1
rem M32 (D-069): the Settings shortcut's icon (a gear), the launcher's second icon resource.
python tools\make_r3hd_icon.py --variant settings --out "%OUT%\r3hd_settings.ico" || exit /b 1
"%R3HD_LLVM_BIN%\llvm-rc.exe" /nologo /I "%OUT%" /fo "%OUT%\r3hd_launcher.res" tools\launcher\r3hd_launcher.rc || exit /b 1
"%R3HD_LLVM_BIN%\clang-cl.exe" /nologo /std:c++17 /O2 /MT /W4 -Wno-missing-field-initializers /EHsc /GS /DUNICODE /D_UNICODE /Brepro ^
  /Fo"%OUT%\r3hd_launcher.obj" /Fe"%OUT%\r3hd_launcher.exe" tools\launcher\r3hd_launcher.cpp ^
  -fuse-ld=lld /link /SUBSYSTEM:WINDOWS /DEBUG:NONE /INCREMENTAL:NO /Brepro /OPT:REF /OPT:ICF ^
  "%OUT%\r3hd_launcher.res" user32.lib gdi32.lib comctl32.lib shell32.lib comdlg32.lib ole32.lib || exit /b 1
echo LAUNCHER_BUILD_OK %OUT%\r3hd_launcher.exe
exit /b 0
