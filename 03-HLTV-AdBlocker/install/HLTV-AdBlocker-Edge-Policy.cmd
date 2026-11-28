@echo off
setlocal EnableExtensions

rem ============================================================
rem  HLTV-AdBlocker - Edge extension policy helper  (v2)
rem
rem  Writes the extension ID to the machine-wide allowlist:
rem    HKLM\SOFTWARE\Policies\Microsoft\Edge\ExtensionInstallAllowlist
rem  (also mirrored into the 32-bit registry view, because a 32-bit
rem   cmd.exe would otherwise land in Wow6432Node only)
rem
rem  Usage:
rem    HLTV-AdBlocker-Edge-Policy-v2.cmd             install (elevates)
rem    HLTV-AdBlocker-Edge-Policy-v2.cmd /remove     remove the entry
rem    HLTV-AdBlocker-Edge-Policy-v2.cmd /status     show current state
rem ============================================================

set "EXT_ID=neglnknmnfbhpodhjpaopomffhehojge"
set "ROOT=HKLM\SOFTWARE\Policies\Microsoft\Edge"
set "ALLOW_KEY=%ROOT%\ExtensionInstallAllowlist"
set "BLOCK_KEY=%ROOT%\ExtensionInstallBlocklist"
set "MODE=install"

:parse_args
if /i "%~1"=="/remove" (
    set "MODE=remove"
    shift
    goto parse_args
)
if /i "%~1"=="/status" (
    set "MODE=status"
    shift
    goto parse_args
)
if /i "%~1"=="/?" goto usage
if /i "%~1"=="/help" goto usage
if not "%~1"=="" (
    echo Unknown option: %~1
    goto usage
)

rem ---- administrator check -----------------------------------
net session >nul 2>&1
if errorlevel 1 (
    if /i "%MODE%"=="status" goto do_status
    echo Requesting administrator permission...
    powershell -NoProfile -ExecutionPolicy Bypass -Command "Start-Process -FilePath '%~f0' -ArgumentList '%*' -Verb RunAs"
    exit /b
)

if /i "%MODE%"=="status" goto do_status
if /i "%MODE%"=="remove" goto do_remove

rem =============================== install ====================
set "PRESENT="
for /f "tokens=1,2,*" %%A in ('reg query "%ALLOW_KEY%" 2^>nul') do (
    if /i "%%~B"=="REG_SZ" if /i "%%~C"=="%EXT_ID%" set "PRESENT=%%~A"
)
if not defined PRESENT (
    for /f "tokens=1,2,*" %%A in ('reg query "%ALLOW_KEY%" /reg:32 2^>nul') do (
        if /i "%%~B"=="REG_SZ" if /i "%%~C"=="%EXT_ID%" set "PRESENT=%%~A"
    )
)

if defined PRESENT (
    echo [OK] Extension ID is already allowed ^(value "%PRESENT%"^).
    goto report_policy
)

rem find the first unused value name (1, 2, 3, ...) in either view
set "INDEX="
for /L %%N in (1,1,50) do (
    if not defined INDEX (
        reg query "%ALLOW_KEY%" /v %%N >nul 2>&1
        if errorlevel 1 (
            reg query "%ALLOW_KEY%" /v %%N /reg:32 >nul 2>&1
            if errorlevel 1 set "INDEX=%%N"
        )
    )
)
if not defined INDEX set "INDEX=50"

set "WRITTEN=0"
reg add "%ALLOW_KEY%" /v %INDEX% /t REG_SZ /d "%EXT_ID%" /f /reg:64 >nul 2>&1
if not errorlevel 1 set "WRITTEN=1"
reg add "%ALLOW_KEY%" /v %INDEX% /t REG_SZ /d "%EXT_ID%" /f /reg:32 >nul 2>&1

if "%WRITTEN%"=="0" (
    echo [FAIL] Could not write the policy. Run this file as administrator.
    pause
    exit /b 1
)

reg query "%ALLOW_KEY%" /v %INDEX% 2>nul | findstr /i /c:"%EXT_ID%" >nul
if errorlevel 1 (
    echo [FAIL] Policy value was written but could not be read back.
    pause
    exit /b 1
)
echo [OK] Wrote value %INDEX% = %EXT_ID%
echo      under %ALLOW_KEY%  ^(64-bit and 32-bit views^)

goto report_policy

rem =============================== remove =====================
:do_remove
set "REMOVED=0"
for /f "tokens=1,2,*" %%A in ('reg query "%ALLOW_KEY%" 2^>nul') do (
    if /i "%%~B"=="REG_SZ" if /i "%%~C"=="%EXT_ID%" (
        reg delete "%ALLOW_KEY%" /v "%%~A" /f /reg:64 >nul 2>&1
        reg delete "%ALLOW_KEY%" /v "%%~A" /f /reg:32 >nul 2>&1
        set /a REMOVED+=1
    )
)
if "%REMOVED%"=="0" (
    echo [--] No allowlist entry for this extension under %ALLOW_KEY%.
) else (
    echo [OK] Removed %REMOVED% allowlist entry/entries.
)
pause
exit /b 0

rem =============================== status =====================
:do_status
echo Extension ID : %EXT_ID%
echo.
echo Allowlist key  : %ALLOW_KEY%
reg query "%ALLOW_KEY%" 2>nul | findstr /i /c:"%EXT_ID%" >nul
if errorlevel 1 (
    reg query "%ALLOW_KEY%" /reg:32 2>nul | findstr /i /c:"%EXT_ID%" >nul
    if errorlevel 1 (
        echo   [not present in 64-bit or 32-bit view]
    ) else (
        echo   [present in 32-bit view only]
    )
) else (
    echo   [present]
    reg query "%ALLOW_KEY%" 2>nul | findstr /i /c:"%EXT_ID%"
)
echo.
echo Blocklist key  : %BLOCK_KEY%
reg query "%BLOCK_KEY%" 2>nul | findstr /i /c:"*" >nul
if errorlevel 1 (
    echo   [not set]  -^> ExtensionInstallAllowlist has no effect by itself.
) else (
    echo   [present]  -^> allowlist is meaningful
)
echo.
echo Policy UI: open edge://policy in Edge and press "Reload policies".
pause
exit /b 0

rem =============================== report =====================
:report_policy
echo.
reg query "%BLOCK_KEY%" 2>nul | findstr /i /c:"*" >nul
if errorlevel 1 (
    echo [hint] No ExtensionInstallBlocklist policy is set.
    echo        Microsoft docs: ExtensionInstallAllowlist only exempts an extension
    echo        from ExtensionInstallBlocklist. On its own it does NOT enable
    echo        installing an extension from a local .crx file.
    echo        The extension is installed from edge://extensions instead:
    echo        drag the .crx onto that page, or use "Load unpacked" on the
    echo        extracted folder ^(its manifest keeps the "key" field, so the ID
    echo        stays neglnknmnfbhpodhjpaopomffhehojge^).
) else (
    echo [info] ExtensionInstallBlocklist is present; the allowlist entry is meaningful.
)
echo.
echo Next steps:
echo   1. Fully quit Edge: close every window, then right-click the Edge icon
echo      in the taskbar and choose "Quit" ^(a restart is required for policies^).
echo   2. Open edge://policy and press "Reload policies" to verify it loaded.
echo   3. Open edge://extensions and turn the extension switch on if needed.
echo.
echo To undo: run this file with /remove
echo.
pause
exit /b 0

rem =============================== usage ======================
:usage
echo.
echo HLTV-AdBlocker - Edge extension policy helper (v2)
echo.
echo   /status    show current policy state (no admin needed)
echo   /remove    remove the allowlist entry (admin needed)
echo.
pause
exit /b 0
