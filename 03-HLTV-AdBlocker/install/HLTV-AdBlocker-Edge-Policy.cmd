@echo off
setlocal
set "EXT_ID=neglnknmnfbhpodhjpaopomffhehojge"
set "POLICY_KEY=HKLM\SOFTWARE\Policies\Microsoft\Edge\ExtensionInstallAllowlist"

net session >nul 2>&1
if errorlevel 1 (
    echo Requesting administrator permission...
    powershell -NoProfile -ExecutionPolicy Bypass -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
    exit /b
)

reg add "%POLICY_KEY%" /v 1 /t REG_SZ /d "%EXT_ID%" /f >nul
if errorlevel 1 (
    echo Failed to write the Edge policy. Run this file as administrator.
    pause
    exit /b 1
)

echo.
echo HLTV-AdBlocker Edge policy installed.
echo.
echo 1. Fully quit Edge: close every window, then right-click the Edge icon in the taskbar and choose Quit.
echo 2. Open Edge and go to edge://extensions
echo 3. Turn on the HLTV-AdBlocker switch.
echo.
echo The policy only adds this extension ID to ExtensionInstallAllowlist.
echo To remove it later, run this command as administrator:
echo   reg delete "%POLICY_KEY%" /v 1 /f
echo.
pause
