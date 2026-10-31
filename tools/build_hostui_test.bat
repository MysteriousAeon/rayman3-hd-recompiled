@echo off
setlocal
rem D-139: the in-game PC Settings input gate and panel model (tools\r3hd_hostui_gate_test.cpp) against the installed
rem SDK and the built runtime's real keyboard / mouse driver. Run through tools\devenv.bat; no game, window, device or
rem OS input.
for %%I in ("%~dp0..") do set "R3HD_HOSTUI_ROOT=%%~fI"
set "R3HD_HOSTUI_SDK=%R3HD_HOSTUI_ROOT%\external\rexglue-sdk\out\install\win-amd64"
set "R3HD_HOSTUI_OUT=%R3HD_HOSTUI_ROOT%\private\work\pcset"
if not exist "%R3HD_HOSTUI_OUT%" mkdir "%R3HD_HOSTUI_OUT%"
clang++ -DNOMINMAX -DREX_HAS_D3D12=1 -DSPDLOG_COMPILED_LIB -DSPDLOG_FMT_EXTERNAL -DWIN32_LEAN_AND_MEAN -isystem "%R3HD_HOSTUI_SDK%\include" -I "%~dp0." -O2 -DNDEBUG -std=gnu++23 -D_DLL -D_MT -Xclang --dependent-lib=msvcrt -msse4.1 -c "%~dp0r3hd_hostui_gate_test.cpp" -o "%R3HD_HOSTUI_OUT%\hostui_test.obj" || exit /b 1
clang++ -nostartfiles -nostdlib -O2 -D_DLL -D_MT -Xclang --dependent-lib=msvcrt -Xlinker /subsystem:console -fuse-ld=lld-link "%R3HD_HOSTUI_OUT%\hostui_test.obj" -o "%R3HD_HOSTUI_OUT%\hostui_test.exe" "%R3HD_HOSTUI_SDK%\lib\rexruntime.lib" "%R3HD_HOSTUI_SDK%\lib\spdlog.lib" "%R3HD_HOSTUI_SDK%\lib\fmt.lib" "%R3HD_HOSTUI_SDK%\lib\SDL3-static.lib" -lkernel32 -luser32 -lgdi32 -lwinmm -limm32 -lole32 -loleaut32 -lversion -luuid -ladvapi32 -lsetupapi -lshell32 -lhid -ldinput8 -ldxgi -ldxguid -lwinspool -lcomdlg32 -loldnames || exit /b 1
rem Load the built runtime; never copy or replace it.
set "PATH=%R3HD_HOSTUI_ROOT%\private\work\rex\out\build\win-amd64-release;%PATH%"
"%R3HD_HOSTUI_OUT%\hostui_test.exe"
exit /b %ERRORLEVEL%
