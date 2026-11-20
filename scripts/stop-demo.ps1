<#
.SYNOPSIS
  Dong cac cua so dich vu do start-demo.ps1 mo (va moi tien trinh con: uvicorn, vite, bridge sync).
  Postgres va Mailpit (Docker) van chay; tat bang Docker Desktop hoac "docker compose stop" neu muon.
#>
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot '_common.ps1')
$file = Join-Path $Bridge 'out\demo-windows.json'
if (-not (Test-Path $file)) { Write-Warn 'Khong thay out\demo-windows.json: chua chay start-demo.ps1, hoac da dung.'; exit 0 }
# PowerShell 5.1: ConvertFrom-Json tra ca mang thanh MOT doi tuong; gan vao bien roi moi duyet
$windows = Get-Content -Raw -Encoding UTF8 $file | ConvertFrom-Json
foreach ($w in $windows) {
    if (Get-Process -Id $w.pid -ErrorAction SilentlyContinue) {
        & taskkill /T /F /PID $w.pid | Out-Null
        Write-Ok "Dong $($w.title)"
    }
}
Remove-Item $file
