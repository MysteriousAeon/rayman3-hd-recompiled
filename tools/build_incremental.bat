@echo off
rem Incremental rebuild after a host-only change (SDK runtime sources, tools\m2_host): SDK targets, install,
rem relink r3hd, copy the runtime DLLs. A few minutes instead of the 10-12 of build_milestone8.bat, for A/B runs
rem only: it replays no patches, regenerates nothing and runs no regression. A checkpoint still needs
rem build_milestone8.bat to end with M8_BUILD_OK. Ends with INCREMENTAL_BUILD_OK.
setlocal
cd /d "%~dp0.."
call "C:\Program Files (x86)\Microsoft Visual Studio\18\BuildTools\VC\Auxiliary\Build\vcvars64.bat" >nul 2>&1
set "PATH=C:\Program Files\LLVM\bin;%PATH%"
cmake --build external/rexglue-sdk/out/build/win-amd64 --config Release --target rexglue rexgpu-xenos SDL3_test -j 4
if errorlevel 1 exit /b 1
cmake --install external/rexglue-sdk/out/build/win-amd64 --config Release
if errorlevel 1 exit /b 1
cmake --build private/work/rex/out/build/win-amd64-release --target r3hd -j 6
if errorlevel 1 exit /b 1
copy /y external\rexglue-sdk\out\install\win-amd64\bin\*.dll private\work\rex\out\build\win-amd64-release\ >nul
echo INCREMENTAL_BUILD_OK
exit /b 0
