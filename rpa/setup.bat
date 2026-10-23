@echo off
rem HRD claim workshop - one-time setup. Messages are printed by setup_env.py (Korean).
rem NOTE: .bat files must stay ASCII + CRLF.
cd /d "%~dp0"
chcp 65001 >nul
title [SETUP] RPA engine install - do not close until done
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8
where python >nul 2>&1
if errorlevel 1 (
  echo.
  echo ================================================================
  echo   Python is not installed.
  echo   1. Open https://www.python.org/downloads/ and install Python 3.12
  echo   2. On the first screen, CHECK "Add python.exe to PATH"
  echo   3. Run setup.bat again
  echo ================================================================
  pause
  exit /b 1
)
python setup_env.py fastapi uvicorn yaml openpyxl pywinauto pyautogui cv2 PIL
set RC=%errorlevel%
if /i not "%~1"=="nopause" pause
exit /b %RC%
