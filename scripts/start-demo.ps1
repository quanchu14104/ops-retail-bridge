<#
.SYNOPSIS
  Bat ca demo Ops Chest -> Retail-AI: moi dich vu mot cua so PowerShell rieng.

.DESCRIPTION
  Mo 5 cua so: Ops Chest API (8000), Ops Chest UI (5173), Retail-AI API (8020), kiosk (5190) va bridge sync
  (moi 120 giay). Bat Postgres cua Retail-AI va Mailpit neu Docker dang chay. Dong cua so nao thi dich vu do dung.
  Chay setup.ps1 mot lan truoc.

.PARAMETER NoSync
  Khong bat bridge sync (feed giu nguyen ban cu).
#>
param([switch]$NoSync)

$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot '_common.ps1')

function ConvertTo-PSLiteral([string]$Text) { return "'" + $Text.Replace("'", "''") + "'" }

function Start-ServiceWindow([string]$Title, [string]$Dir, [hashtable]$Environment, [string]$Command) {
    $lines = @(
        "`$host.UI.RawUI.WindowTitle = $(ConvertTo-PSLiteral $Title)",
        '[Console]::OutputEncoding = [System.Text.Encoding]::UTF8',
        "Set-Location -LiteralPath $(ConvertTo-PSLiteral $Dir)"
    )
    foreach ($k in $Environment.Keys) { $lines += "`$env:$k = $(ConvertTo-PSLiteral ([string]$Environment[$k]))" }
    $lines += "Write-Host $(ConvertTo-PSLiteral "== $Title ==") -ForegroundColor Cyan"
    $lines += $Command
    # -EncodedCommand: giu nguyen chu tieng Viet trong bien moi truong, khong lo dau nhay
    $encoded = [Convert]::ToBase64String([System.Text.Encoding]::Unicode.GetBytes(($lines -join "`n")))
    $proc = Start-Process powershell -ArgumentList @('-NoExit', '-NoProfile', '-EncodedCommand', $encoded) -PassThru
    $script:Started += @{ title = $Title; pid = $proc.Id }
    Write-Ok "$Title (PID $($proc.Id))"
}

function ConvertTo-Hashtable($Ordered) { $h = @{}; foreach ($k in $Ordered.Keys) { $h[$k] = $Ordered[$k] }; return $h }

if (-not (Test-Path (Join-Path $OpsChest 'backend\ops_chest.db'))) {
    Write-Warn 'Chua co DB demo cua Ops Chest. Chay .\bridge\scripts\setup.ps1 truoc.'
    exit 1
}

Write-Step 'Docker'
if (Test-Docker) {
    Invoke-In $RetailAI 'docker' @('compose', 'up', '-d', 'postgres')
    Invoke-In $OpsChest 'docker' @('compose', 'up', '-d', 'mailpit')
} else {
    Write-Warn 'Docker chua chay: kiosk se khong tra loi duoc khuyen mai/hang moi ve, duyet don dat hang se bao loi email.'
}

Write-Step 'Mo cac cua so dich vu'
$script:Started = @()
$opsEnv = ConvertTo-Hashtable (Read-EnvFile (Join-Path $Bridge 'demo\ops-chest.env'))
$retailEnv = ConvertTo-Hashtable (Read-EnvFile (Join-Path $Bridge 'demo\retail-ai.env'))
$retailEnv['PYTHONIOENCODING'] = 'utf-8'
Start-ServiceWindow 'Ops Chest API :8000' (Join-Path $OpsChest 'backend') $opsEnv `
    'uv run uvicorn app.api.main:app --host 127.0.0.1 --port 8000'
Start-ServiceWindow 'Ops Chest UI :5173' (Join-Path $OpsChest 'frontend') @{ API_TARGET = 'http://localhost:8000' } `
    'npm run dev -- --port 5173 --strictPort'
Start-ServiceWindow 'Retail-AI API :8020' $RetailAI $retailEnv `
    'uv run uvicorn backend.api.main:app --host 127.0.0.1 --port 8020'
Start-ServiceWindow 'Kiosk :5190' $Kiosk @{ VITE_API_BASE_URL = $retailEnv['VITE_API_BASE_URL'] } `
    'npm run dev -- --host 127.0.0.1 --port 5190 --strictPort'
if (-not $NoSync) {
    # Lan sync dau co the bao "khong ket noi duoc Ops Chest" khi API chua len kip; vong lap tu thu lai sau 120 giay
    Start-ServiceWindow 'Bridge sync (120s)' $Bridge @{ PYTHONIOENCODING = 'utf-8' } `
        'Start-Sleep -Seconds 15; uv run bridge sync --every 120'
}

# Ghi PID de stop-demo.ps1 dong dung cac cua so nay
New-Item -ItemType Directory -Force (Join-Path $Bridge 'out') | Out-Null
$script:Started | ConvertTo-Json | Set-Content -Encoding UTF8 (Join-Path $Bridge 'out\demo-windows.json')

Write-Host ''
Write-Host 'Ops Chest (Store Manager): http://localhost:5173   tai khoan quanly / quanly123'
Write-Host 'Kiosk (nguoi mua):         http://127.0.0.1:5190'
Write-Host 'Mailpit (email dat hang):  http://localhost:8025'
Write-Host 'Dung demo: .\bridge\scripts\stop-demo.ps1 (hoac dong cac cua so vua mo).'
