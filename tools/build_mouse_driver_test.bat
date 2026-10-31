@echo off
setlocal
rem D-138: the real driver's mouse contract (tools\r3hd_mouse_driver_test.cpp) against the installed SDK and the
rem built runtime. Run through tools\devenv.bat; no game, window, device or OS input.
for %%I in ("%~dp0..") do set "R3HD_MOUSE_ROOT=%%~fI"
set "R3HD_MOUSE_SDK=%R3HD_MOUSE_ROOT%\external\rexglue-sdk\out\install\win-amd64"
set "R3HD_MOUSE_OUT=%R3HD_MOUSE_ROOT%\private\work\mouse"
if not exist "%R3HD_MOUSE_OUT%" mkdir "%R3HD_MOUSE_OUT%"
clang++ -DNOMINMAX -DREX_HAS_D3D12=1 -DSPDLOG_COMPILED_LIB -DSPDLOG_FMT_EXTERNAL -DWIN32_LEAN_AND_MEAN -isystem "%R3HD_MOUSE_SDK%\include" -O2 -DNDEBUG -std=gnu++23 -D_DLL -D_MT -Xclang --dependent-lib=msvcrt -msse4.1 -c "%~dp0r3hd_mouse_driver_test.cpp" -o "%R3HD_MOUSE_OUT%\mouse_driver_test.obj" || exit /b 1
clang++ -nostartfiles -nostdlib -O2 -D_DLL -D_MT -Xclang --dependent-lib=msvcrt -Xlinker /subsystem:console -fuse-ld=lld-link "%R3HD_MOUSE_OUT%\mouse_driver_test.obj" -o "%R3HD_MOUSE_OUT%\mouse_driver_test.exe" "%R3HD_MOUSE_SDK%\lib\rexruntime.lib" "%R3HD_MOUSE_SDK%\lib\spdlog.lib" "%R3HD_MOUSE_SDK%\lib\fmt.lib" "%R3HD_MOUSE_SDK%\lib\SDL3-static.lib" -lkernel32 -luser32 -lgdi32 -lwinmm -limm32 -lole32 -loleaut32 -lversion -luuid -ladvapi32 -lsetupapi -lshell32 -lhid -ldinput8 -ldxgi -ldxguid -lwinspool -lcomdlg32 -loldnames || exit /b 1
rem Load the built runtime; never copy or replace it.
set "PATH=%R3HD_MOUSE_ROOT%\private\work\rex\out\build\win-amd64-release;%PATH%"
"%R3HD_MOUSE_OUT%\mouse_driver_test.exe"
exit /b %ERRORLEVEL%
