@echo off
rem D-101 / D-102 host tests: DualSense policy with a mock pad, achievement display text; D-115: the controller
rem button map (no SDK, no device, no game).
setlocal
cd /d "%~dp0.."
if not exist private\work\ds mkdir private\work\ds
call tools\devenv.bat clang++ -std=c++20 -O1 -Wall -Wextra -Werror -D_CRT_SECURE_NO_WARNINGS tools\r3hd_dualsense_test.cpp -o private\work\ds\r3hd_dualsense_test.exe || exit /b 1
private\work\ds\r3hd_dualsense_test.exe || exit /b 1
call tools\devenv.bat clang++ -std=c++20 -O1 -Wall -Wextra -Werror -D_CRT_SECURE_NO_WARNINGS tools\r3hd_achtext_test.cpp -o private\work\ds\r3hd_achtext_test.exe || exit /b 1
private\work\ds\r3hd_achtext_test.exe || exit /b 1
call tools\devenv.bat clang++ -std=c++20 -O1 -Wall -Wextra -Werror -D_CRT_SECURE_NO_WARNINGS tools\r3hd_padmap_test.cpp -o private\work\ds\r3hd_padmap_test.exe || exit /b 1
private\work\ds\r3hd_padmap_test.exe || exit /b 1
python tools\r3hd_achievements.py selftest || exit /b 1
echo R3HD_RELEASE_TESTS_OK
