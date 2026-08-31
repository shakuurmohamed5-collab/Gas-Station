@echo off
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo Project Python was not found at .venv\Scripts\python.exe
    echo Recreate the virtual environment before starting the system.
    pause
    exit /b 1
)

echo Preparing GasFlow...
".venv\Scripts\python.exe" manage.py migrate --noinput
if errorlevel 1 (
    echo Database preparation failed.
    pause
    exit /b 1
)

echo.
echo GasFlow is starting at http://127.0.0.1:8000/
echo Keep this window open. Press Ctrl+C to stop the system.
echo.
".venv\Scripts\python.exe" manage.py runserver 127.0.0.1:8000

