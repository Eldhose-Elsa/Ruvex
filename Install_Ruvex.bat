@echo off
setlocal enabledelayedexpansion
title Ruvex - Windows Setup Wizard

echo =====================================================================
echo                     Ruvex - Setup Wizard
echo =====================================================================
echo.
echo Installing Ruvex for the current user...
echo Target Directory: %%LOCALAPPDATA%%\Programs\Ruvex
echo.

set "INSTALL_DIR=%LOCALAPPDATA%\Programs\Ruvex"
set "EXE_SOURCE=%~dp0dist\Ruvex.exe"

if not exist "!EXE_SOURCE!" (
    set "EXE_SOURCE=%~dp0Ruvex.exe"
)

if not exist "!EXE_SOURCE!" (
    echo [ERROR] Could not find Ruvex.exe!
    echo Please make sure Ruvex.exe is in the same folder or in dist\.
    echo.
    pause
    exit /b 1
)

:: Create installation directory
if not exist "!INSTALL_DIR!" (
    mkdir "!INSTALL_DIR!" 2>nul
)
if not exist "!INSTALL_DIR!\assets" (
    mkdir "!INSTALL_DIR!\assets" 2>nul
)

:: Copy executable
echo [1/3] Copying application files...
copy /y "!EXE_SOURCE!" "!INSTALL_DIR!\Ruvex.exe" >nul
if %ERRORLEVEL% neq 0 (
    echo [ERROR] Failed to copy application files to !INSTALL_DIR!.
    pause
    exit /b 1
)

:: Copy assets if available
if exist "%~dp0assets\app.ico" (
    copy /y "%~dp0assets\app.ico" "!INSTALL_DIR!\assets\app.ico" >nul
)
if exist "%~dp0assets\Ruvex.png" (
    copy /y "%~dp0assets\Ruvex.png" "!INSTALL_DIR!\assets\Ruvex.png" >nul
)

:: Create Desktop and Start Menu Shortcuts using PowerShell
echo [2/3] Creating Desktop and Start Menu shortcuts...
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
    "$ws = New-Object -ComObject WScript.Shell; " ^
    "$desk = [Environment]::GetFolderPath('Desktop'); " ^
    "$s1 = $ws.CreateShortcut(\"$desk\Ruvex.lnk\"); " ^
    "$s1.TargetPath = '!INSTALL_DIR!\Ruvex.exe'; " ^
    "$s1.WorkingDirectory = '!INSTALL_DIR!'; " ^
    "$s1.IconLocation = '!INSTALL_DIR!\Ruvex.exe,0'; " ^
    "$s1.Description = 'Ruvex - RAW to Image Converter (PNG, WEBP, JPEG)'; " ^
    "$s1.Save(); " ^
    "$startMenu = [Environment]::GetFolderPath('Programs'); " ^
    "$s2 = $ws.CreateShortcut(\"$startMenu\Ruvex.lnk\"); " ^
    "$s2.TargetPath = '!INSTALL_DIR!\Ruvex.exe'; " ^
    "$s2.WorkingDirectory = '!INSTALL_DIR!'; " ^
    "$s2.IconLocation = '!INSTALL_DIR!\Ruvex.exe,0'; " ^
    "$s2.Description = 'Ruvex - RAW to Image Converter (PNG, WEBP, JPEG)'; " ^
    "$s2.Save();"

:: Create Uninstaller
echo [3/3] Setting up Uninstaller...
(
echo @echo off
echo title Uninstall Ruvex
echo echo Are you sure you want to uninstall Ruvex?
echo echo.
echo pause
echo taskkill /f /im Ruvex.exe 2^>nul
echo del /f /q "%%USERPROFILE%%\Desktop\Ruvex.lnk" 2^>nul
echo del /f /q "%%APPDATA%%\Microsoft\Windows\Start Menu\Programs\Ruvex.lnk" 2^>nul
echo rmdir /s /q "%%LOCALAPPDATA%%\Programs\Ruvex" 2^>nul
echo echo.
echo echo Successfully uninstalled Ruvex!
echo pause
) > "!INSTALL_DIR!\Uninstall.bat"

echo.
echo =====================================================================
echo                  Installation Completed Successfully!
echo =====================================================================
echo.
echo Shortcuts created on:
echo   - Desktop: "Ruvex"
echo   - Windows Start Menu: "Ruvex"
echo.
echo No Python installation or extra dependencies required on this PC!
echo.
set /p LAUNCH="Would you like to launch Ruvex now? (Y/N): "
if /i "!LAUNCH!"=="Y" (
    start "" "!INSTALL_DIR!\Ruvex.exe"
)

exit /b 0
