@echo off
REM Builds a stand-alone POS.exe in the dist folder (no Python needed on the till PC).
cd /d "%~dp0"
python -m pip install --upgrade pyinstaller
python -m PyInstaller --noconfirm --windowed --onefile --name POS --icon assets\pos.ico --add-data "assets\pos.ico;assets" main.py
echo.
echo Done. Copy dist\POS.exe to the shop computer. Data is stored in a "data" folder next to it.
pause
