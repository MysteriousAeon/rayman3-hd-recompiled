@echo off
rem D-101 / D-102 host tests: DualSense policy with a mock pad, achievement display text; D-115: the controller
rem button map; D-138: the mouse state and camera mapping (no SDK, no device, no game).
setlocal
cd /d "%~dp0.."
if not exist private\work\ds mkdir private\work\ds
call tools\devenv.bat clang++ -std=c++20 -O1 -Wall -Wextra -Werror -D_CRT_SECURE_NO_WARNINGS tools\r3hd_dualsense_test.cpp -o private\work\ds\r3hd_dualsense_test.exe || exit /b 1
private\work\ds\r3hd_dualsense_test.exe || exit /b 1
call tools\devenv.bat clang++ -std=c++20 -O1 -Wall -Wextra -Werror -D_CRT_SECURE_NO_WARNINGS tools\r3hd_achtext_test.cpp -o private\work\ds\r3hd_achtext_test.exe || exit /b 1
private\work\ds\r3hd_achtext_test.exe || exit /b 1
call tools\devenv.bat clang++ -std=c++20 -O1 -Wall -Wextra -Werror -D_CRT_SECURE_NO_WARNINGS tools\r3hd_padmap_test.cpp -o private\work\ds\r3hd_padmap_test.exe || exit /b 1
private\work\ds\r3hd_padmap_test.exe || exit /b 1
rem D-138: the environment of the calls above is reused; one more devenv call inside the full build overflows cmd's
rem environment (vcvars prepends to PATH each time) and silently ends the whole build.
clang++ -std=c++20 -O1 -Wall -Wextra -Werror -D_CRT_SECURE_NO_WARNINGS tools\r3hd_mouse_test.cpp -o private\work\ds\r3hd_mouse_test.exe || exit /b 1
private\work\ds\r3hd_mouse_test.exe || exit /b 1
rem D-141: the controller-speaker rule and XMA2 splitter; with a game data root, also the person's own clip.
clang++ -std=c++20 -O1 -Wall -Wextra -Werror -D_CRT_SECURE_NO_WARNINGS tools\r3hd_ds_speaker_test.cpp -o private\work\ds\r3hd_ds_speaker_test.exe || exit /b 1
if defined R3HD_GAME_DIR (private\work\ds\r3hd_ds_speaker_test.exe "%R3HD_GAME_DIR%" || exit /b 1) else (private\work\ds\r3hd_ds_speaker_test.exe || exit /b 1)
python tools\r3hd_achievements.py selftest || exit /b 1
echo R3HD_RELEASE_TESTS_OK
