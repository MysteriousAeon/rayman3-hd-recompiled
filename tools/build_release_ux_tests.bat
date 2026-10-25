@echo off
setlocal
cd /d "%~dp0.."
set "UXTEST=private\work\final_ux_101\native"
if not exist "%UXTEST%\home\app" mkdir "%UXTEST%\home\app"
python -c "from pathlib import Path; Path(r'%UXTEST%\home\app\r3hd_launcher.exe').write_bytes(b'non-executable test fixture')" || exit /b 1
python tools\make_r3hd_icon.py --out "%UXTEST%\home\data\play_icon.ico" || exit /b 1
python tools\make_r3hd_icon.py --out "%UXTEST%\fallback\fallback.ico" || exit /b 1
call tools\devenv.bat clang-cl /nologo /std:c++17 /EHsc /W4 /MT tools\release_presentation_icon_test.cpp /Fo"%UXTEST%\icon_test.obj" /Fe"%UXTEST%\icon_test.exe" /link user32.lib gdi32.lib || exit /b 1
"%UXTEST%\icon_test.exe" "%CD%\%UXTEST%\home\data\play_icon.ico" || exit /b 1
"%UXTEST%\icon_test.exe" "%CD%\%UXTEST%\fallback\fallback.ico" || exit /b 1
python tools\release_ux_defaults_test.py "%UXTEST%\policy_%RANDOM%_%RANDOM%" || exit /b 1
python tools\release_ux_icon_audit.py private\work\launcher\r3hd_launcher.exe "%UXTEST%\settings_resources.json" --kind settings || exit /b 1
echo RELEASE_UX_TESTS_OK
