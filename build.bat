@echo off
REM CLEAN rebuild. Kills any already-running copy first (tray apps keep
REM running in the background even after you close their window — if an
REM old copy is still alive, you'll keep seeing IT, not your new build),
REM then wipes cached PyInstaller output, then builds fresh.

echo Closing any already-running ProcessWatchdog.exe...
taskkill /IM ProcessWatchdog.exe /F >nul 2>&1

echo Removing old build artifacts...
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist
if exist ProcessWatchdog.spec del /q ProcessWatchdog.spec
if exist __pycache__ rmdir /s /q __pycache__

python -m pip install --upgrade pip
python -m pip install -r requirements.txt

python -m PyInstaller --noconfirm --onefile --windowed ^
  --name "ProcessWatchdog" ^
  --icon "icon.ico" ^
  --add-data "icon.ico;." ^
  --add-data "icon_tray.png;." ^
  watchdog_app.py

echo.
echo Build complete. Find it at dist\ProcessWatchdog.exe
pause
