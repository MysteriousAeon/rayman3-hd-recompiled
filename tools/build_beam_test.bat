@echo off
setlocal
cd /d "%~dp0.."
rem Inside the full replay clang++ is already on PATH: reuse it (another devenv call can end the whole chain).
set "BEAM_TEST=private\work\rex\out\build\win-amd64-release\r3hd_beam_color_test.exe"
set "BEAM_CXX=clang++ -std=c++20 -O2 -D_CRT_SECURE_NO_WARNINGS tools/r3hd_beam_color_test.cpp -o %BEAM_TEST%"
where clang++ >nul 2>nul
if errorlevel 1 (call tools\devenv.bat %BEAM_CXX%) else (%BEAM_CXX%)
if errorlevel 1 exit /b 1
if not defined R3HD_GAME_DIR set "R3HD_GAME_DIR=%CD%\private\extracted\5841123F"
%BEAM_TEST% || exit /b 1
if exist "%R3HD_GAME_DIR%\GAMEDATAbin\menu_20\menu_20_2.btf" %BEAM_TEST% "%R3HD_GAME_DIR%\GAMEDATAbin\menu_20\menu_20_2.btf" || exit /b 1
if exist "%R3HD_GAME_DIR%\GAMEDATAbin\fact_40\fact_40_2.btf" %BEAM_TEST% "%R3HD_GAME_DIR%\GAMEDATAbin\fact_40\fact_40_2.btf" || exit /b 1
if exist "%R3HD_GAME_DIR%\GAMEDATAbin\fix.btf" %BEAM_TEST% "%R3HD_GAME_DIR%\GAMEDATAbin\fix.btf" || exit /b 1
python tools\r3hd_beam_color.py selftest || exit /b 1
python tools\r3hd_beam_color.py check || exit /b 1
python tools\r3hd_beam_regression.py
exit /b %errorlevel%
