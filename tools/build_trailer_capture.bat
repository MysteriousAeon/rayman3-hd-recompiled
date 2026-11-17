@echo off
setlocal
cd /d "%~dp0.."
python tools\trailer_capture_prepare.py refresh
if errorlevel 1 exit /b 1
call tools\devenv.bat cmake -S private/work/trailer_capture -B private/work/trailer_capture/build -G Ninja -DCMAKE_BUILD_TYPE=Release -DCMAKE_CXX_COMPILER=clang++ -DCMAKE_PREFIX_PATH="%CD%/external/rexglue-sdk/out/install/win-amd64"
if errorlevel 1 exit /b 1
call tools\devenv.bat cmake --build private/work/trailer_capture/build --target r3hd capture_input_test -j 6
if errorlevel 1 exit /b 1
copy /y private\trailer_20261101\runtime\bin\*.dll private\work\trailer_capture\build\ >nul
if errorlevel 1 exit /b 1
private\work\trailer_capture\build\capture_input_test.exe
if errorlevel 1 exit /b 1
python tools\trailer_capture_prepare.py seal
if errorlevel 1 exit /b 1
echo CAPTURE_BUILD_OK
