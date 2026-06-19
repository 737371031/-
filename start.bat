@echo off
setlocal

cd /d "%~dp0"

set "HOST=127.0.0.1"
set "PORT=8080"
set "PAGE=/"
set "MODE=%~1"

if /I "%MODE%"=="admin" set "PAGE=/admin.html"
if /I "%MODE%"=="subscriptions" set "PAGE=/subscriptions.html"

set "PYTHON_EXE="
set "PYTHON_ARGS="

where python >nul 2>nul
if not errorlevel 1 (
    python --version >nul 2>nul
    if not errorlevel 1 set "PYTHON_EXE=python"
)

if not defined PYTHON_EXE (
    py -3 --version >nul 2>nul
    if not errorlevel 1 (
        set "PYTHON_EXE=py"
        set "PYTHON_ARGS=-3"
    )
)

if not defined PYTHON_EXE (
    where python3 >nul 2>nul
    if not errorlevel 1 (
        python3 --version >nul 2>nul
        if not errorlevel 1 set "PYTHON_EXE=python3"
    )
)

if not defined PYTHON_EXE (
    set "CODEX_PY=%USERPROFILE%\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
    if exist "%CODEX_PY%" set "PYTHON_EXE=%CODEX_PY%"
)

if not defined PYTHON_EXE (
    echo [ERROR] No Python runtime was found.
    echo Install Python 3 first, then run this script again.
    pause
    exit /b 1
)

echo Starting local site...
echo.
echo Home: http://%HOST%:%PORT%/
echo Admin: http://%HOST%:%PORT%/admin.html
echo.

start "" "http://%HOST%:%PORT%%PAGE%"
call "%PYTHON_EXE%" %PYTHON_ARGS% server.py --host %HOST% --port %PORT%

endlocal
