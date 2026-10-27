param([Parameter(Mandatory=$true)][string]$TunnelToken)
$ErrorActionPreference = "Stop"
if (-not (Get-Command cloudflared -ErrorAction SilentlyContinue)) {
    if (-not (Get-Command winget -ErrorAction SilentlyContinue)) {
        throw "Khong tim thay winget. Hay cai cloudflared tu trang Cloudflare truoc."
    }
    winget install --id Cloudflare.cloudflared --exact --accept-source-agreements --accept-package-agreements
}
cloudflared service install $TunnelToken
Write-Host "Cloudflare Tunnel da duoc cai nhu Windows Service." -ForegroundColor Green
Write-Host "Token chi duoc gui truc tiep cho cloudflared va khong luu trong System."
