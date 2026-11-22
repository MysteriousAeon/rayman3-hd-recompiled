@echo off
rem G6-P75 (D-324): controller motors stopped at close. Mock-pad policy test, the SDL helper against the pinned SDL with
rem an in-process virtual pad (every physical SDL backend off; refuses if any other joystick is visible), then the
rem source / wiring regression. No game, no window, no physical controller.
setlocal
cd /d "%~dp0.."
set "PM_OUT=private\work\padmotors"
if not exist %PM_OUT%\inc\rex mkdir %PM_OUT%\inc\rex
copy /y tools\m23_haptics.h %PM_OUT%\inc\rex\ >nul || exit /b 1
copy /y tools\r3hd_pad_motors.h %PM_OUT%\inc\rex\ >nul || exit /b 1
copy /y tools\r3hd_pad_motors_sdl.h %PM_OUT%\inc\rex\ >nul || exit /b 1
set "PM_SDK=external\rexglue-sdk\out\install\win-amd64"
set "PM_CXX1=clang++ -std=c++20 -O1 -Wall -Wextra -Werror -D_CRT_SECURE_NO_WARNINGS tools/r3hd_pad_motors_test.cpp -o %PM_OUT%\r3hd_pad_motors_test.exe"
set "PM_CXX2=clang++ -std=c++20 -O1 -Wall -Wextra -Werror -D_CRT_SECURE_NO_WARNINGS -I%PM_OUT%\inc -I%PM_SDK%\include tools/r3hd_pad_motors_sdl_test.cpp %PM_SDK%\lib\SDL3-static.lib -luser32 -lgdi32 -lwinmm -limm32 -lole32 -loleaut32 -lversion -luuid -ladvapi32 -lsetupapi -lshell32 -lcfgmgr32 -o %PM_OUT%\r3hd_pad_motors_sdl_test.exe"
rem Inside the full replay clang++ is already on PATH: reuse it (another devenv call can end the whole chain).
where clang++ >nul 2>nul
if errorlevel 1 (call tools\devenv.bat %PM_CXX1%) else (%PM_CXX1%)
if errorlevel 1 exit /b 1
where clang++ >nul 2>nul
if errorlevel 1 (call tools\devenv.bat %PM_CXX2%) else (%PM_CXX2%)
if errorlevel 1 exit /b 1
%PM_OUT%\r3hd_pad_motors_test.exe || exit /b 1
set "R3HD_NONINTRUSIVE="
%PM_OUT%\r3hd_pad_motors_sdl_test.exe || exit /b 1
set "R3HD_NONINTRUSIVE=1"
%PM_OUT%\r3hd_pad_motors_sdl_test.exe hidden || exit /b 1
set "R3HD_NONINTRUSIVE="
python tools\g6p75_pad_motors_regression.py
exit /b %errorlevel%
