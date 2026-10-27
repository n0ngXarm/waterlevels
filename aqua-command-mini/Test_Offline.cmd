@echo off
setlocal
cd /d "%~dp0"
if not exist "aqua_command" (
  echo Run source tests from the source package. See README.md.
  pause
  exit /b 2
)
set AQUA_RUN_GUI_TESTS=1
set PYTHONUTF8=1
py -3.13 -m unittest discover -v
set AQUA_TEST_EXIT=%errorlevel%
pause
exit /b %AQUA_TEST_EXIT%
