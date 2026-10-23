@echo off
REM Builds both Windows installers in the dist folder:
REM   POS_Setup_<version>.exe             - Electronics POS (English)
REM   ShopPOS_Arabic_Setup_<version>.exe  - Shop POS (Arabic)
REM Needs: Python 3.10+ and Inno Setup 6 (free: https://jrsoftware.org/isdl.php).
cd /d "%~dp0"

python -m pip install --upgrade pyinstaller pywin32 || goto :fail
python -m PyInstaller --noconfirm --windowed --name POS --icon assets\pos.ico --add-data "assets\pos.ico;assets" --add-data "installer\editions\electronics\edition.txt;." --hidden-import win32print --hidden-import win32api main.py || goto :fail
python -m PyInstaller --noconfirm --windowed --name ShopPOS --icon assets\pos.ico --add-data "assets\pos.ico;assets" --add-data "installer\editions\shop_ar\edition.txt;." --hidden-import win32print --hidden-import win32api main.py || goto :fail

for /f %%v in ('python -c "import pos; print(pos.__version__)"') do set VERSION=%%v

set ISCC="%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
if not exist %ISCC% set ISCC="%ProgramFiles%\Inno Setup 6\ISCC.exe"
if not exist %ISCC% (
  echo.
  echo Inno Setup 6 was not found. Install it from https://jrsoftware.org/isdl.php and run this again.
  goto :fail
)
%ISCC% /DAppVersion=%VERSION% /DEdition=electronics installer\setup.iss || goto :fail
%ISCC% /DAppVersion=%VERSION% /DEdition=shop_ar installer\setup.iss || goto :fail

echo.
echo Done:
echo   dist\POS_Setup_%VERSION%.exe
echo   dist\ShopPOS_Arabic_Setup_%VERSION%.exe
pause
goto :eof

:fail
echo.
echo Build failed - see the messages above.
pause
exit /b 1
