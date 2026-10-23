@echo off
rem Start the dashboard. The side panel opens from the purple/white buttons in the DATA sheet.
rem NOTE: .bat files must stay ASCII + CRLF.
cd /d "%~dp0"
if not exist node_modules\ (
  call "%~dp0setup.bat"
  if errorlevel 1 exit /b 1
)
if not exist dist\index.html call npm run build
set ELECTRON_RUN_AS_NODE=
call node node_modules\electron\cli.js .
