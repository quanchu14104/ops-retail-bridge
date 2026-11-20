# Ham dung chung cho setup.ps1 va start-demo.ps1. Viet cho Windows PowerShell 5.1 (khong dung && hay ?:).

$Bridge = Split-Path -Parent $PSScriptRoot
$Workspace = Split-Path -Parent $Bridge
$OpsChest = Join-Path $Workspace 'ops_chest'
$RetailAI = Join-Path $Workspace 'Retail-AI-'
$Kiosk = Join-Path $RetailAI 'apps\kiosk-airi'

function Write-Step([string]$Message) { Write-Host "`n==> $Message" -ForegroundColor Cyan }
function Write-Ok([string]$Message) { Write-Host "  [ok] $Message" -ForegroundColor Green }
function Write-Warn([string]$Message) { Write-Host "  [!] $Message" -ForegroundColor Yellow }

function Read-EnvFile([string]$Path) {
    # KEY=VALUE, bo dong trong va chu thich, bo ngoac kep bao ngoai (giong bridge/config.py)
    $values = [ordered]@{}
    foreach ($raw in [System.IO.File]::ReadAllLines($Path, [System.Text.Encoding]::UTF8)) {
        $line = $raw.Trim()
        if ($line -eq '' -or $line.StartsWith('#') -or -not $line.Contains('=')) { continue }
        $i = $line.IndexOf('=')
        $key = $line.Substring(0, $i).Trim()
        $value = $line.Substring($i + 1).Trim()
        if ($value.Length -ge 2 -and $value[0] -eq $value[-1] -and ('"', "'") -contains [string]$value[0]) {
            $value = $value.Substring(1, $value.Length - 2)
        }
        $values[$key] = $value
    }
    return $values
}

function Invoke-In([string]$Dir, [string]$Exe, [string[]]$Arguments) {
    # Chay lenh ngoai trong thu muc Dir; loi (exit code khac 0) thi dung script
    Push-Location $Dir
    try {
        & $Exe @Arguments
        if ($LASTEXITCODE -ne 0) { throw "$Exe $($Arguments -join ' ') that bai (exit $LASTEXITCODE) trong $Dir" }
    } finally {
        Pop-Location
    }
}

function Test-Command([string]$Name) { return [bool](Get-Command $Name -ErrorAction SilentlyContinue) }

function Test-Docker {
    if (-not (Test-Command 'docker')) { return $false }
    $null = & docker info --format '{{.ServerVersion}}' 2>$null
    return ($LASTEXITCODE -eq 0)
}
