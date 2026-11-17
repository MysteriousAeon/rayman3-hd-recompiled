@echo off
setlocal
cd /d "%~dp0.."
rem Inside the full replay clang++ is already on PATH: reuse it (another devenv call can end the whole chain).
set "LOCKON_TEST=private\work\rex\out\build\win-amd64-release\r3hd_lockon_color_test.exe"
set "LOCKON_CXX=clang++ -std=c++20 -O2 -D_CRT_SECURE_NO_WARNINGS tools/r3hd_lockon_color_test.cpp -o %LOCKON_TEST%"
where clang++ >nul 2>nul
if errorlevel 1 (call tools\devenv.bat %LOCKON_CXX%) else (%LOCKON_CXX%)
if errorlevel 1 exit /b 1
if not defined R3HD_GAME_DIR set "R3HD_GAME_DIR=%CD%\private\extracted\5841123F"
%LOCKON_TEST% || exit /b 1
if exist "%R3HD_GAME_DIR%\GAMEDATAbin\fix.btf" %LOCKON_TEST% "%R3HD_GAME_DIR%\GAMEDATAbin\fix.btf" || exit /b 1
python tools\r3hd_lockon_color.py selftest || exit /b 1
python tools\r3hd_lockon_color.py check || exit /b 1
python tools\r3hd_lockon_regression.py
exit /b %errorlevel%
