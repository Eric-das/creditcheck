@echo off
rem CreditCheck desktop app. Double-click to launch the window.
setlocal
cd /d "%~dp0"
set "PYTHONPATH=%~dp0src"
python -m creditcheck.desktop
if errorlevel 1 pause
