@echo off
setlocal
set "SYSTEM_DIR=%~dp0"
if defined VNSTOCKDESK_RUNTIME_DIR (
  set "RUNTIME_DIR=%VNSTOCKDESK_RUNTIME_DIR%"
) else (
  set "RUNTIME_DIR=%LOCALAPPDATA%\VnStockDesk\runtime"
)
set "PYTHON=%RUNTIME_DIR%\.venv\Scripts\python.exe"
if exist "%PYTHON%" "%PYTHON%" "%SYSTEM_DIR%desktop_launcher.py" --stop
endlocal
