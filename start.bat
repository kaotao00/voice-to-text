@echo off
REM Keep this file ASCII-only and CRLF-terminated.
REM No goto/labels: an unreachable label makes cmd terminate
REM the script silently, which looks like a crash.
setlocal
chcp 65001 > nul
set PYTHONIOENCODING=utf-8
cd /d "%~dp0"

if not exist "voice_to_text.py" (
    echo ERROR: voice_to_text.py not found.
    echo This .bat must sit in the same folder
    echo as voice_to_text.py
    echo Current folder: %CD%
    echo.
    pause
    exit /b 1
)

echo Starting voice input tool...
echo Keep this window open while using it.
echo Close this window to quit.
echo.

set "VOICE_PYTHON=%USERPROFILE%\miniconda3\envs\voice\python.exe"
if exist "%VOICE_PYTHON%" (
    "%VOICE_PYTHON%" voice_to_text.py
) else (
    python voice_to_text.py
)

echo.
echo ---- program exited (code %ERRORLEVEL%) ----
echo.
echo If you saw ModuleNotFoundError, run install.bat first.
echo If the hotkey did nothing, right-click this file
echo and pick "Run as administrator".
echo.
pause
