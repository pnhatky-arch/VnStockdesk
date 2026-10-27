@echo off
setlocal
set "SYSTEM_DIR=%~dp0"
if defined VNSTOCKDESK_RUNTIME_DIR (
  set "RUNTIME_DIR=%VNSTOCKDESK_RUNTIME_DIR%"
) else (
  set "RUNTIME_DIR=%LOCALAPPDATA%\VnStockDesk\runtime"
)
set "PYTHON=%RUNTIME_DIR%\.venv\Scripts\python.exe"
if not exist "%PYTHON%" (
  echo Chua cai moi truong. Hay chay INSTALL_WINDOWS.ps1 truoc.
  pause
  exit /b 1
)
cd /d "%SYSTEM_DIR%"
"%PYTHON%" "%SYSTEM_DIR%desktop_launcher.py"
if errorlevel 1 (
  echo.
  echo VnStockDesk khong khoi dong duoc.
  echo Log: %RUNTIME_DIR%\dashboard.log
  if exist "%RUNTIME_DIR%\dashboard.log" (
    echo.
    powershell -NoProfile -Command "Get-Content -LiteralPath '%RUNTIME_DIR%\dashboard.log' -Tail 60"
  )
  echo.
  pause
  exit /b 1
)
endlocal
