@echo off
REM Launcher for the dedicated Python 3.12 environment.
REM It calls the environment interpreter directly, so
REM conda init is not required for cmd.exe.
REM Keep this file ASCII-only and CRLF-terminated.
setlocal
chcp 65001 > nul
set PYTHONIOENCODING=utf-8
cd /d "%~dp0"

set "PYTHON_EXE=%USERPROFILE%\miniconda3\envs\voice\python.exe"

if not exist "%PYTHON_EXE%" (
    echo.
    echo ERROR: voice environment Python was not found:
    echo   %PYTHON_EXE%
    echo.
    echo Create it first:
    echo   conda create -n voice python=3.12
    echo   conda run -n voice python -m pip install -r requirements.txt
    echo.
    echo If Miniconda is installed somewhere else, edit
    echo PYTHON_EXE in this file to match that location.
    echo.
    pause
    exit /b 1
)

"%PYTHON_EXE%" --version
echo.
echo Starting voice input tool...
echo Keep this window open while using it.
echo.

"%PYTHON_EXE%" voice_to_text.py

echo.
echo ---- program exited (code %ERRORLEVEL%) ----
echo.
pause
