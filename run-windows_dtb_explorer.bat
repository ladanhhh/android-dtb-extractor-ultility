@echo off
title DTB Explorer Launcher

:: Ensure script operates from its local directory
cd /d "%~dp0"

:: 1. Check if Python is installed
python --version >nul 2>&1
if %ERRORLEVEL% EQU 0 goto RUN_SCRIPT

echo [!] Python is not installed or not found in system PATH.
echo.
set /p "INSTALL_CHOICE=Would you like to install Python now? (Y/N): "

if /i "%INSTALL_CHOICE%"=="Y" goto INSTALL_PYTHON
echo.
echo Cannot proceed without Python runtime. Exiting...
pause
exit /b 1

:INSTALL_PYTHON
echo.
echo Launching Python installer via Windows Package Manager (winget)...
winget install -e --id Python.Python.3.11 --accept-source-agreements --accept-package-agreements
if %ERRORLEVEL% NEQ 0 goto INSTALL_FAILED

echo.
echo [!] Python has been installed successfully.
echo     Please RESTART this batch file so Windows updates your PATH environment variables.
pause
exit /b 0

:INSTALL_FAILED
echo.
echo [!] Automatic installation failed or winget is unavailable.
echo     Please download and install Python manually from https://www.python.org/
pause
exit /b 1

:RUN_SCRIPT
:: 2. Launch the Python file directly
python "sources\dtb_explorer\dtb_explorer.py" %*

pause