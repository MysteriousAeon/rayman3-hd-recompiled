@echo off
setlocal
cd /d "%~dp0.."
rem D-220: host test of the display V-Sync header, the DXGI API probe on a never-shown window (skipped without a
rem hardware Direct3D 12 device), the cadence model self-test, then the static / settings regression.
rem Inside the full replay clang++ is already on PATH: reuse it (another devenv call can end the whole chain).
if not exist private\work\display_vsync mkdir private\work\display_vsync
set "VSYNC_TEST=private\work\display_vsync\r3hd_display_vsync_test.exe"
set "VSYNC_PROBE=private\work\display_vsync\r3hd_display_vsync_dxgi_probe.exe"
set "VSYNC_CXX=clang++ -std=c++20 -O2 -Wall -Werror -D_CRT_SECURE_NO_WARNINGS tools/r3hd_display_vsync_test.cpp -o %VSYNC_TEST%"
set "VSYNC_PROBE_CXX=clang++ -std=c++20 -O2 -Wall -Werror -D_CRT_SECURE_NO_WARNINGS tools/r3hd_display_vsync_dxgi_probe.cpp -o %VSYNC_PROBE% -ld3d12 -ldxgi -luser32"
where clang++ >nul 2>nul
if errorlevel 1 (
  call tools\devenv.bat %VSYNC_CXX% || exit /b 1
  call tools\devenv.bat %VSYNC_PROBE_CXX% || exit /b 1
) else (
  %VSYNC_CXX% || exit /b 1
  %VSYNC_PROBE_CXX% || exit /b 1
)
%VSYNC_TEST% || exit /b 1
%VSYNC_PROBE%
if errorlevel 78 exit /b 1
if errorlevel 77 (echo R3HD_DISPLAY_VSYNC_DXGI_PROBE skipped) else (if errorlevel 1 exit /b 1)
python tools\r3hd_display_vsync_cadence.py selftest || exit /b 1
python tools\r3hd_display_vsync_regression.py
exit /b %errorlevel%
