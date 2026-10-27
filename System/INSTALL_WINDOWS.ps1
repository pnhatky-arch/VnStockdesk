$ErrorActionPreference = "Stop"
$SystemDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$DeskDir = Split-Path -Parent $SystemDir
$DataDir = Join-Path $DeskDir "Data"
$RuntimeRoot = if ($env:VNSTOCKDESK_RUNTIME_DIR) { $env:VNSTOCKDESK_RUNTIME_DIR } else { Join-Path $env:LOCALAPPDATA "VnStockDesk\runtime" }
$VenvDir = Join-Path $RuntimeRoot ".venv"

@("market\raw", "market\processed", "market\news", "private\state") | ForEach-Object {
    New-Item -ItemType Directory -Force -Path (Join-Path $DataDir $_) | Out-Null
}
New-Item -ItemType Directory -Force -Path $RuntimeRoot | Out-Null

$Python = Get-Command py -ErrorAction SilentlyContinue
if ($Python) { & py -3 -m venv $VenvDir } else {
    $Python = Get-Command python -ErrorAction Stop
    & python -m venv $VenvDir
}
$VenvPython = Join-Path $VenvDir "Scripts\python.exe"
& $VenvPython -m pip install --upgrade pip
& $VenvPython -m pip install -r (Join-Path $SystemDir "requirements.txt")
& $VenvPython -m compileall -q $SystemDir
Write-Host "VnStockDesk da san sang tren Windows." -ForegroundColor Green
Write-Host "Runtime cuc bo: $RuntimeRoot"
Write-Host "Nhan dup START_VnStockDesk.cmd de mo dashboard." 
