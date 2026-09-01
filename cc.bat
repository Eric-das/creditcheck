@echo off
rem CreditCheck launcher. Runs ALL THREE stages by default:
rem   Stage 1 net balance & open items + Stage 2 allocation chain
rem   + Stage 3 split-level reconciliation.
rem Usage:
rem   cc ACME01       run all three stages for an account
rem   cc --check      test the Sage connection only (short-circuits stages)
rem   double-click    prompts for an account ref, then runs all three stages
setlocal
cd /d "%~dp0"
set "PYTHONPATH=%~dp0src"

if not "%~1"=="" (
    python -m creditcheck.cli %* --chain --recon
    goto :eof
)

set "ACC="
set /p "ACC=Account ref (or --check): "
if "%ACC%"=="" goto :eof
python -m creditcheck.cli %ACC% --chain --recon
echo.
pause
