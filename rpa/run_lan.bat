@echo off
rem HRD claim dashboard - open READ-ONLY to other PCs on the same network (LAN).
rem Does not change local.json; next time run.bat starts it for this PC only again.
cd /d "%~dp0"
if not exist .venv\setup_ok (
  call "%~dp0setup.bat" nopause
  if errorlevel 1 goto :fail
)
set PYTHONIOENCODING=utf-8
set HRD_PUBLIC=1

rem 1) viewer password (needed for read-only access from other PCs)
.venv\Scripts\python.exe -m hrdnet has-viewer-password
if not errorlevel 1 goto :firewall
echo.
echo No viewer password yet. Choose one for read-only access (4+ characters).
:askpw
set "HUBPW="
set /p "HUBPW=Viewer password: "
if "%HUBPW%"=="" goto :askpw
.venv\Scripts\python.exe -m hrdnet viewer-password "%HUBPW%"
if errorlevel 1 goto :askpw
set "HUBPW="

:firewall
rem 2) Windows Firewall rule for TCP 8820 (Private networks only). Needs admin once.
netsh advfirewall firewall show rule name="HRD-Claim-8820" >nul 2>&1
if not errorlevel 1 goto :start
echo.
echo Adding firewall rule HRD-Claim-8820 (TCP 8820, Private networks only). An admin prompt will appear.
powershell -NoProfile -Command "Start-Process netsh -Verb RunAs -Wait -ArgumentList 'advfirewall firewall add rule name=HRD-Claim-8820 dir=in action=allow protocol=TCP localport=8820 profile=private'"
netsh advfirewall firewall show rule name="HRD-Claim-8820" >nul 2>&1
if errorlevel 1 echo [warn] Firewall rule was not added. Other PCs may not be able to connect.

:start
echo.
echo Closing this window stops the dashboard.
.venv\Scripts\python.exe -m hrdnet ui
exit /b %errorlevel%

:fail
pause
exit /b 1
