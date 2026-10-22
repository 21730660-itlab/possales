@echo off
REM Builds dist\POS_Setup_<version>.exe - a normal Windows installer for the POS.
REM Needs: Python 3.10+ and Inno Setup 6 (free: https://jrsoftware.org/isdl.php).
cd /d "%~dp0"

python -m pip install --upgrade pyinstaller pywin32 || goto :fail
python -m PyInstaller --noconfirm --windowed --name POS --icon assets\pos.ico --add-data "assets\pos.ico;assets" --hidden-import win32print --hidden-import win32api main.py || goto :fail

for /f %%v in ('python -c "import pos; print(pos.__version__)"') do set VERSION=%%v

set ISCC="%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
if not exist %ISCC% set ISCC="%ProgramFiles%\Inno Setup 6\ISCC.exe"
if not exist %ISCC% (
  echo.
  echo Inno Setup 6 was not found. Install it from https://jrsoftware.org/isdl.php and run this again.
  goto :fail
)
%ISCC% /DAppVersion=%VERSION% installer\setup.iss || goto :fail

echo.
echo Done: dist\POS_Setup_%VERSION%.exe
pause
goto :eof

:fail
echo.
echo Build failed - see the messages above.
pause
exit /b 1
