@echo off
rem Start the dashboard. The side panel opens from the buttons in the DATA sheet.
rem NOTE: .bat files must stay ASCII + CRLF.
cd /d "%~dp0"
title Order-Cost-Manager - keep this window open (minimize it)
if not exist node_modules\ (
  call "%~dp0setup.bat"
  if errorlevel 1 exit /b 1
)
if not exist dist\index.html call npm run build
echo.
echo ============================================================
echo   The dashboard is running.
echo   Keep this window open while you use it (minimize is OK).
echo   Closing this window closes the dashboard.
echo ============================================================
set ELECTRON_RUN_AS_NODE=
call node node_modules\electron\cli.js .
