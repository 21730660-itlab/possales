@echo off
REM Double-click to start Shop POS (Arabic interface) from the Python source.
cd /d "%~dp0"
set POS_EDITION=shop_ar
where pyw >NUL 2>NUL && (start "" pyw -3 main.py & goto :eof)
where pythonw >NUL 2>NUL && (start "" pythonw main.py & goto :eof)
where py >NUL 2>NUL && (py -3 main.py & goto :eof)
python main.py
if errorlevel 1 (
  echo.
  echo Python was not found. Install it from https://www.python.org/downloads/
  echo and tick "Add python.exe to PATH" during setup.
  pause
)
