@echo off
setlocal
set "SYSTEM_DIR=%~dp0"
echo ============================================================
echo VnStockDesk - KIEM TRA BAN DANG CHAY
echo ============================================================
powershell.exe -NoProfile -Command "$p='%SYSTEM_DIR%app.py'; Write-Host ('Source: ' + $p); Write-Host ('Cap nhat: ' + (Get-Item $p).LastWriteTime); Write-Host ('SHA256: ' + (Get-FileHash $p -Algorithm SHA256).Hash); if (Select-String -LiteralPath $p -Pattern 'VNINDEX-20260903-1123' -Quiet) { Write-Host 'BUILD: VNINDEX-20260903-1123 - DA DONG BO' -ForegroundColor Green } else { Write-Host 'BUILD CU - GOOGLE DRIVE CHUA DONG BO' -ForegroundColor Red; exit 2 }"
if errorlevel 1 goto :not_synced

echo Dang dung dashboard cu...
call "%SYSTEM_DIR%STOP_VnStockDesk.cmd"
timeout /t 2 /nobreak >nul
echo Dang mo dashboard moi...
call "%SYSTEM_DIR%START_VnStockDesk.cmd"
exit /b 0

:not_synced
echo.
echo File app.py tren Windows chua co ban VN-Index.
echo Mo Google Drive, chon VnStockDesk va doi den khi trang thai la Up to date.
echo Sau do chay lai file nay.
pause
exit /b 2
