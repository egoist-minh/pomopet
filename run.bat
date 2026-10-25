@echo off
setlocal
cd /d "%~dp0"

echo Starting PomoPet...

:: Electron must run in desktop mode, not as a Node.js process.
set "ELECTRON_RUN_AS_NODE="

:: Development and packaged builds must share one persistent data store.
:: Electron's packaged userData directory resolves to this same location.
set "POMOPET_DATA_DIR=%APPDATA%\ai-studio-applet"
set "POMOPET_USER_DATA_DIR=%APPDATA%\ai-studio-applet"
if not exist "%POMOPET_DATA_DIR%" mkdir "%POMOPET_DATA_DIR%"

:: Run FastAPI, Next.js, and Electron in this terminal.
call npm run dev

if errorlevel 1 (
  echo PomoPet stopped because one of its processes failed.
  pause
  exit /b 1
)
