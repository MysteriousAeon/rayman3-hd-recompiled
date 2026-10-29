@echo off
setlocal
cd /d "%~dp0.."
if not exist private\work\portable mkdir private\work\portable
call tools\devenv.bat clang-cl /nologo /EHsc /std:c++20 /MT tools\r3hd_utf8_path_test.cpp /Foprivate\work\portable\utf8_path.obj /Feprivate\work\portable\utf8_path_control.exe /link /Brepro || exit /b 1
call tools\devenv.bat clang-cl /nologo /EHsc /std:c++20 /MT tools\r3hd_utf8_path_test.cpp /Foprivate\work\portable\utf8_path.obj /Feprivate\work\portable\utf8_path.exe /link /Brepro /MANIFEST:EMBED /MANIFESTINPUT:tools\m2_host\r3hd.manifest || exit /b 1
