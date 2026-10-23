@echo off
rem HRD-net cost claim workshop
rem   run.bat              open the dashboard (this PC only): http://127.0.0.1:8820
rem   run.bat organize     any CLI command: python -m hrdnet ...
rem NOTE: .bat files must stay ASCII + CRLF.
cd /d "%~dp0"
if not exist .venv\setup_ok (
  call "%~dp0setup.bat" nopause
  if errorlevel 1 exit /b 1
)
chcp 65001 >nul
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8
if "%~1"=="" title HRD claim workshop - keep this window open while the dashboard is in use
.venv\Scripts\python.exe -m hrdnet %*
exit /b %errorlevel%
