@echo off
rem Builds R3SaveConverter.exe (single file, windowed) from convert_gui.py. Needs: python -m pip install pyinstaller
rem Output: private\work\save_converter_exe\dist\R3SaveConverter.exe (not committed); set R3SC_OUT to override.
rem _decimal is excluded: unused, and it would bundle libmpdec without a license notice (decimal falls back to _pydecimal).
setlocal
set HERE=%~dp0
set OUT=%HERE%..\..\private\work\save_converter_exe
if defined R3SC_OUT set OUT=%R3SC_OUT%
python -m PyInstaller --noconfirm --clean --onefile --windowed --name R3SaveConverter --exclude-module _decimal --paths "%HERE%." ^
  --distpath "%OUT%\dist" --workpath "%OUT%\build" --specpath "%OUT%" "%HERE%convert_gui.py" || exit /b 1
echo BUILD_OK %OUT%\dist\R3SaveConverter.exe
