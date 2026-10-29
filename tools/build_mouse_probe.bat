@echo off
setlocal
rem Run through tools\devenv.bat. Research only; no runtime rebuild or game launch.
for %%I in ("%~dp0..") do set "R3HD_PROBE_ROOT=%%~fI"
set "R3HD_PROBE_SDK=%R3HD_PROBE_ROOT%\external\rexglue-sdk\out\install\win-amd64"
set "R3HD_PROBE_OUT=%R3HD_PROBE_ROOT%\private\work\mouse_probe"
if not exist "%R3HD_PROBE_OUT%" mkdir "%R3HD_PROBE_OUT%"
clang++ -DNOMINMAX -DREX_HAS_D3D12=1 -DSPDLOG_COMPILED_LIB -DSPDLOG_FMT_EXTERNAL -DWIN32_LEAN_AND_MEAN -isystem "%R3HD_PROBE_SDK%\include" -O2 -DNDEBUG -std=gnu++23 -D_DLL -D_MT -Xclang --dependent-lib=msvcrt -msse4.1 -c "%~dp0r3hd_mouse_probe.cpp" -o "%R3HD_PROBE_OUT%\mouse_probe.obj" || exit /b 1
clang++ -nostartfiles -nostdlib -O2 -D_DLL -D_MT -Xclang --dependent-lib=msvcrt -Xlinker /subsystem:console -fuse-ld=lld-link "%R3HD_PROBE_OUT%\mouse_probe.obj" -o "%R3HD_PROBE_OUT%\mouse_probe.exe" "%R3HD_PROBE_SDK%\lib\rexruntime.lib" "%R3HD_PROBE_SDK%\lib\spdlog.lib" "%R3HD_PROBE_SDK%\lib\fmt.lib" "%R3HD_PROBE_SDK%\lib\SDL3-static.lib" -lkernel32 -luser32 -lgdi32 -lwinmm -limm32 -lole32 -loleaut32 -lversion -luuid -ladvapi32 -lsetupapi -lshell32 -lhid -ldinput8 -ldxgi -ldxguid -lwinspool -lcomdlg32 -loldnames || exit /b 1
rem Load the existing runtime; never copy or replace it.
set "PATH=%R3HD_PROBE_ROOT%\private\work\rex\out\build\win-amd64-release;%PATH%"
"%R3HD_PROBE_OUT%\mouse_probe.exe"
exit /b %ERRORLEVEL%
