@echo off
setlocal
cd /d "%~dp0"

echo Preparing build (venv + dependencies)...
if not exist "venv\Scripts\activate.bat" (
  echo ERROR: venv not found. Create it with: python -m venv venv
  pause
  exit /b 1
)
call venv\Scripts\activate.bat
python -m pip install -r requirements.txt

echo.
echo ===================================================
echo Building SmashArenaIDScanner (PyInstaller, onefile)
echo ===================================================
echo.

REM Single-line PyInstaller avoids broken line-continuation (^) with UTF-8 / stray spaces.
python -m PyInstaller --noconfirm --onefile --windowed --name "SmashArenaIDScanner" --add-data "arenahere.png;." --add-data "arenahere_720p.png;." --hidden-import "winsdk.windows.media.ocr" --hidden-import "winsdk.windows.graphics.imaging" --hidden-import "winsdk.windows.storage.streams" --hidden-import "winsdk.windows.applicationmodel.datatransfer" --hidden-import "pystray._win32" --collect-all "pystray" --collect-all "customtkinter" main.py

echo.
echo ===================================================
echo Done. See dist\SmashArenaIDScanner.exe
echo (Images are bundled; copy the single exe to use it.)
echo ===================================================
pause
