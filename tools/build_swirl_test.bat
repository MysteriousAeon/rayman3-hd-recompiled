@echo off
setlocal
cd /d "%~dp0.."
call tools\devenv.bat clang++ -std=c++20 tools/r3hd_swirl_test.cpp -o private/work/rex/out/build/win-amd64-release/r3hd_swirl_test.exe
if errorlevel 1 exit /b 1
private\work\rex\out\build\win-amd64-release\r3hd_swirl_test.exe
if errorlevel 1 exit /b 1
python tools\r3hd_swirl_regression.py
exit /b %errorlevel%
