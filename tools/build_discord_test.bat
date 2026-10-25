@echo off
setlocal
cd /d "%~dp0.."
if not exist private\work\release_discord mkdir private\work\release_discord
call tools\devenv.bat clang-cl /nologo /std:c++17 /EHsc /W4 /MT /D_CRT_SECURE_NO_WARNINGS /Iexternal\rexglue-sdk\thirdparty\inja\third_party\include tools\release_discord_test.cpp /Foprivate\work\release_discord\test.obj /Feprivate\work\release_discord\test.exe || exit /b 1
python tools\release_discord_test.py private\work\release_discord\test.exe || exit /b 1
echo DISCORD_TEST_OK
