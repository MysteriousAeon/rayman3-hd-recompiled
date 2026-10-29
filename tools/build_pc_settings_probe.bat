@echo off
setlocal
rem Evidence probe only: no runtime rebuild, game, window or physical device.
for %%I in ("%~dp0..") do set "R3HD_PC_ROOT=%%~fI"
set "R3HD_PC_SDK=%R3HD_PC_ROOT%\external\rexglue-sdk\out\install\win-amd64"
set "R3HD_PC_OUT=%R3HD_PC_ROOT%\private\work\pc_settings_probe"
if not exist "%R3HD_PC_OUT%" mkdir "%R3HD_PC_OUT%"
clang++ -DNOMINMAX -DREX_HAS_D3D12=1 -DSPDLOG_COMPILED_LIB -DSPDLOG_FMT_EXTERNAL -DWIN32_LEAN_AND_MEAN -isystem "%R3HD_PC_SDK%\include" -O2 -DNDEBUG -std=gnu++23 -D_DLL -D_MT -Xclang --dependent-lib=msvcrt -msse4.1 -c "%~dp0r3hd_pc_settings_probe.cpp" -o "%R3HD_PC_OUT%\probe.obj" || exit /b 1
clang++ -nostartfiles -nostdlib -O2 -D_DLL -D_MT -Xclang --dependent-lib=msvcrt -Xlinker /subsystem:console -fuse-ld=lld-link "%R3HD_PC_OUT%\probe.obj" -o "%R3HD_PC_OUT%\probe.exe" "%R3HD_PC_SDK%\lib\rexruntime.lib" "%R3HD_PC_SDK%\lib\spdlog.lib" "%R3HD_PC_SDK%\lib\fmt.lib" "%R3HD_PC_SDK%\lib\SDL3-static.lib" -lkernel32 -luser32 -lgdi32 -lwinmm -limm32 -lole32 -loleaut32 -lversion -luuid -ladvapi32 -lsetupapi -lshell32 -lhid -ldinput8 -ldxgi -ldxguid -lwinspool -lcomdlg32 -loldnames || exit /b 1
set "PATH=%R3HD_PC_ROOT%\private\work\rex\out\build\win-amd64-release;%PATH%"
"%R3HD_PC_OUT%\probe.exe"
exit /b %ERRORLEVEL%
