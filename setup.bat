@echo off
rem One-time setup: dashboard (Node) + RPA engine (Python). Run once per PC.
rem NOTE: .bat files must stay ASCII + CRLF.
cd /d "%~dp0"
title [SETUP] install - do not close until done
where node >nul 2>&1
if errorlevel 1 (
  echo.
  echo Node.js is not installed. Install Node.js 22 LTS from https://nodejs.org and run setup.bat again.
  pause
  exit /b 1
)
echo [1/3] Installing dashboard packages...
call npm install --no-audit --no-fund
if errorlevel 1 ( echo npm install failed. & pause & exit /b 1 )
echo [2/3] Building dashboard...
call npm run build
if errorlevel 1 ( echo build failed. & pause & exit /b 1 )
echo [3/3] Installing RPA engine (Python 3.12 needed)...
call rpa\setup.bat nopause
if errorlevel 1 ( echo RPA setup failed. Install Python 3.12 with "Add python.exe to PATH" and run setup.bat again. & pause & exit /b 1 )
echo.
echo Setup done. Double-click run.bat to start.
pause
