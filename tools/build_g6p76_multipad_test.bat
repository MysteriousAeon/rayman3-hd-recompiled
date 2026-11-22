@echo off
rem G6-P76: several controllers. (1) The real InputSystem / SlotAssignment of the development rexruntime.dll with two
rem mock pads and the keyboard, plus its negative control (SharedAssignment must fail). (2) The pinned SDL with two
rem in-process virtual pads (every physical SDL backend off; refuses if any other joystick is visible), normal and
rem hidden. (3) The source pins of the policy. No game, no window, no physical controller, no global input.
setlocal
cd /d "%~dp0.."
set "MP_OUT=private\work\g6p76"
if not exist %MP_OUT%\inc\rex mkdir %MP_OUT%\inc\rex
copy /y tools\m23_haptics.h %MP_OUT%\inc\rex\ >nul || exit /b 1
copy /y tools\r3hd_pad_motors.h %MP_OUT%\inc\rex\ >nul || exit /b 1
copy /y tools\r3hd_pad_motors_sdl.h %MP_OUT%\inc\rex\ >nul || exit /b 1
set "MP_SDK=external\rexglue-sdk\out\install\win-amd64"
set "MP_CXX1=clang++ -std=c++23 -O1 -Wall -Wextra -Werror -Wno-unused-parameter -D_CRT_SECURE_NO_WARNINGS -DNOMINMAX -DWIN32_LEAN_AND_MEAN -DREX_HAS_D3D12=1 -DSPDLOG_COMPILED_LIB -DSPDLOG_FMT_EXTERNAL -I%MP_SDK%\include tools/g6p76_multipad_input_test.cpp %MP_SDK%\lib\rexruntime.lib -o %MP_OUT%\g6p76_multipad_input_test.exe"
set "MP_CXX2=clang++ -std=c++20 -O1 -Wall -Wextra -Werror -D_CRT_SECURE_NO_WARNINGS -I%MP_OUT%\inc -I%MP_SDK%\include tools/g6p76_multipad_sdl_test.cpp %MP_SDK%\lib\SDL3-static.lib -luser32 -lgdi32 -lwinmm -limm32 -lole32 -loleaut32 -lversion -luuid -ladvapi32 -lsetupapi -lshell32 -lcfgmgr32 -o %MP_OUT%\g6p76_multipad_sdl_test.exe"
where clang++ >nul 2>nul
if errorlevel 1 (call tools\devenv.bat %MP_CXX1%) else (%MP_CXX1%)
if errorlevel 1 exit /b 1
where clang++ >nul 2>nul
if errorlevel 1 (call tools\devenv.bat %MP_CXX2%) else (%MP_CXX2%)
if errorlevel 1 exit /b 1
set "PATH=%CD%\%MP_SDK%\bin;%PATH%"
set "R3HD_NONINTRUSIVE="
%MP_OUT%\g6p76_multipad_input_test.exe || exit /b 1
%MP_OUT%\g6p76_multipad_input_test.exe control-shared >nul
if not errorlevel 1 (
  echo G6P76 negative control FAIL: SharedAssignment passed the slot checks
  exit /b 1
)
echo G6P76 negative control rejected: SharedAssignment fails the slot checks
%MP_OUT%\g6p76_multipad_sdl_test.exe || exit /b 1
set "R3HD_NONINTRUSIVE=1"
%MP_OUT%\g6p76_multipad_sdl_test.exe hidden || exit /b 1
set "R3HD_NONINTRUSIVE="
python tools\g6p76_multipad_regression.py --selftest
exit /b %errorlevel%
