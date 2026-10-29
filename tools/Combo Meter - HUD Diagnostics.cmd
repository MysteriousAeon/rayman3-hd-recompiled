@echo off
setlocal
cd /d "%~dp0.."
echo Private score HUD comparison. Existing Playtest launcher is unchanged.
echo 1 = Vanilla control, 2 = Delayed Countdown
choice /c 12 /n /m "Choose mode: "
if errorlevel 2 goto delayed
"external\venv\Scripts\python.exe" "tools\combo_close_playtest.py" --manual --hud-diagnostic off
goto done
:delayed
"external\venv\Scripts\python.exe" "tools\combo_close_playtest.py" --manual --hud-diagnostic delayed
:done
echo.
pause
endlocal
