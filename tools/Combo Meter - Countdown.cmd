@echo off
setlocal
cd /d "%~dp0.."
"external\venv\Scripts\python.exe" "tools\combo_close_visual.py" --manual --mode countdown
echo.
pause
endlocal
