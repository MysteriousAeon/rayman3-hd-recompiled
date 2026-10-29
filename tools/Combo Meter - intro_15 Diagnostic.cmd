@echo off
setlocal
cd /d "%~dp0.."
echo Private intro_15 handless gameplay diagnostic. No automatic input.
echo Load Game / RAY, wait until Murfy drops Rayman and you can move.
echo Collect a jewel while handless, then stop scoring for at least 3 seconds.
echo 1 = Vanilla control, 2 = Delayed Countdown
choice /c 12 /n /m "Choose mode: "
if errorlevel 2 goto delayed
"external\venv\Scripts\python.exe" "tools\combo_close_playtest.py" --manual --intro15-diagnostic off
goto done
:delayed
"external\venv\Scripts\python.exe" "tools\combo_close_playtest.py" --manual --intro15-diagnostic delayed
:done
echo.
pause
endlocal
