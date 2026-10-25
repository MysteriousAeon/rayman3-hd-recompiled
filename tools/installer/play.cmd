@echo off
rem Rayman 3 HD Recompiled: start the game with this installation's settings.
setlocal
for %%I in ("%~dp0..") do set "R3HD_INSTALL_HOME=%%~fI"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0tools\play.ps1" -UserHome "%R3HD_INSTALL_HOME%" %*
if errorlevel 1 pause
