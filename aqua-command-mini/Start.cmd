@echo off
setlocal
cd /d "%~dp0"
if exist "%~dp0AQUA_COMMAND_Mini.exe" (
  start "" "%~dp0AQUA_COMMAND_Mini.exe"
  exit /b 0
)
py -3.13 -c "import tkinter" >nul 2>&1
if errorlevel 1 (
  echo Python 3.13 with Tkinter is required for the source edition.
  echo Use the portable Windows package or read README.md.
  pause
  exit /b 2
)
py -3.13 -m aqua_command gui
if errorlevel 1 pause
