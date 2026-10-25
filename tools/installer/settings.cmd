@echo off
rem Rayman 3 HD Recompiled: review or change the preset (Vanilla / HD+ / Custom).
setlocal
for %%I in ("%~dp0..") do set "R3HD_INSTALL_HOME=%%~fI"
"%~dp0python\python.exe" -B "%~dp0tools\r3hd_installer.py" configure --home "%R3HD_INSTALL_HOME%"
pause
