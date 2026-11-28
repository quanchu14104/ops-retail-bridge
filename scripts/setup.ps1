<#
.SYNOPSIS
  Dung moi truong demo Ops Chest -> Retail-AI tren mot may moi.

.DESCRIPTION
  Toan bo du an nam trong MOT repo (github.com/quanchu14104/ops-retail-bridge):
      bridge\ops_chest     Ops Chest (Store Manager)
      bridge\Retail-AI-    Retail-AI (kiosk nguoi mua)
      bridge\src           code cau noi
  Script chay lai nhieu lan van an toan: buoc nao da xong thi bo qua.
  Khong bao gio ghi khoa API vao dau ca; file .env tao tu .env.example de trong khoa.

.PARAMETER ResetDemo
  Seed lai DB demo cua Ops Chest (xoa du lieu demo cu: de xuat, lan duyet, ngay da tua).
.PARAMETER SkipInstall
  Bo qua uv sync / npm install.
.PARAMETER SkipDocker
  Bo qua Postgres cua Retail-AI va Mailpit (khi chua cai hoac chua bat Docker Desktop).

.EXAMPLE
  .\scripts\setup.ps1   (chay trong thu muc bridge)
#>
param([switch]$ResetDemo, [switch]$SkipInstall, [switch]$SkipDocker)

$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot '_common.ps1')
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$env:PYTHONIOENCODING = 'utf-8'

Write-Host "BRIDGE: $Bridge"

# ---- 1. Hai thu muc con trong repo ----
Write-Step 'Kiem tra ops_chest va Retail-AI- trong repo'
$missing = @()
foreach ($marker in @((Join-Path $OpsChest 'backend\pyproject.toml'), (Join-Path $RetailAI 'pyproject.toml'))) {
    if (Test-Path $marker) { Write-Ok $marker } else { $missing += $marker }
}
if ($missing.Count -gt 0) {
    Write-Warn "Thieu: $($missing -join ', '). Clone lai: git clone https://github.com/quanchu14104/ops-retail-bridge.git bridge"
    exit 1
}

# ---- 2. Cong cu ----
Write-Step 'Kiem tra cong cu'
$need = @{ git = 'https://git-scm.com/download/win'; uv = 'https://docs.astral.sh/uv/ (powershell -c "irm https://astral.sh/uv/install.ps1 | iex")'; node = 'https://nodejs.org (ban LTS)'; npm = 'di kem Node.js' }
$lacking = $false
foreach ($tool in $need.Keys) {
    if (Test-Command $tool) { Write-Ok $tool } else { Write-Warn "Chua co $tool : $($need[$tool])"; $lacking = $true }
}
if ($lacking) { Write-Warn 'Cai cac cong cu tren, mo cua so PowerShell moi roi chay lai.'; exit 1 }
$hasDocker = $false
if (-not $SkipDocker) {
    $hasDocker = Test-Docker
    if ($hasDocker) { Write-Ok 'docker (dang chay)' } else { Write-Warn 'Docker chua cai hoac chua bat: buoc Postgres/Mailpit se bo qua (xem cuoi script).' }
}

# ---- 3. Thu vien ----
if (-not $SkipInstall) {
    Write-Step 'Cai thu vien Python (uv sync)'
    Invoke-In $Bridge 'uv' @('sync')
    Invoke-In (Join-Path $OpsChest 'backend') 'uv' @('sync')
    Invoke-In $RetailAI 'uv' @('sync')
    Write-Step 'Cai thu vien giao dien (npm)'
    foreach ($dir in @((Join-Path $OpsChest 'frontend'), $Kiosk)) {
        if (Test-Path (Join-Path $dir 'package-lock.json')) { Invoke-In $dir 'npm' @('ci') } else { Invoke-In $dir 'npm' @('install') }
    }
}

# ---- 4. File .env (khong chua khoa) ----
Write-Step 'Tao file .env tu .env.example (neu chua co)'
foreach ($dir in @($Bridge, $OpsChest, $RetailAI, $Kiosk)) {
    $target = Join-Path $dir '.env'
    $example = Join-Path $dir '.env.example'
    if (Test-Path $target) { Write-Ok "$target da co, giu nguyen" }
    elseif (Test-Path $example) { Copy-Item $example $target; Write-Ok "tao $target" }
    else { Write-Warn "Khong co $example : bo qua (dich vu dung gia tri mac dinh)" }
}
# bridge\.env tao tu ban cu (3 repo nam canh nhau) con tro ra ../Retail-AI- va ../ops_chest: doi sang thu muc trong repo
$bridgeEnv = Join-Path $Bridge '.env'
$envText = [System.IO.File]::ReadAllText($bridgeEnv, [System.Text.Encoding]::UTF8)
$fixed = $envText -replace '(?m)^(\s*(THANH_LAM_CATALOG_PATH|FRN_DATA_PATH)\s*=\s*)\.\./(Retail-AI-|ops_chest)/', '$1$3/'
if ($fixed -ne $envText) {
    [System.IO.File]::WriteAllText($bridgeEnv, $fixed, (New-Object System.Text.UTF8Encoding $false))
    Write-Ok "sua $bridgeEnv : THANH_LAM_CATALOG_PATH / FRN_DATA_PATH tro vao thu muc trong repo"
}
function Read-EnvIfAny([string]$Path) { if (Test-Path $Path) { return Read-EnvFile $Path } else { return @{} } }
$opsEnv = Read-EnvIfAny (Join-Path $OpsChest '.env')
$retailEnv = Read-EnvIfAny (Join-Path $RetailAI '.env')
$needKeys = @()
if (-not $opsEnv['LLM_API_KEY'] -or $opsEnv['LLM_API_KEY'].StartsWith('replace')) { $needKeys += 'ops_chest\.env : LLM_BASE_URL, LLM_API_KEY, LLM_MODEL (tro ly chat cua Ops Chest)' }
if (-not $retailEnv['GROQ_API_KEY'] -or $retailEnv['GROQ_API_KEY'].StartsWith('replace')) { $needKeys += 'Retail-AI-\.env : GROQ_API_KEY (tro chuyen tu do tren kiosk)' }

# ---- 5. Bridge: crosswalk va overrides ----
Write-Step 'Bridge: kiem tra crosswalk va sinh overrides'
Invoke-In $Bridge 'uv' @('run', 'bridge', 'crosswalk', 'check')
Invoke-In $Bridge 'uv' @('run', 'bridge', 'overrides')

# ---- 6. Seed DB demo cua Ops Chest (ten/gia Thanh Lam Mart) ----
$db = Join-Path $OpsChest 'backend\ops_chest.db'
if ((Test-Path $db) -and -not $ResetDemo) {
    Write-Step 'DB demo Ops Chest da co, giu nguyen (them -ResetDemo de seed lai)'
} else {
    Write-Step 'Seed DB demo Ops Chest kem ten/gia Thanh Lam Mart'
    $demo = Read-EnvFile (Join-Path $Bridge 'demo\ops-chest.env')
    foreach ($k in $demo.Keys) { Set-Item "env:$k" $demo[$k] }
    try {
        Invoke-In (Join-Path $OpsChest 'backend') 'uv' @('run', 'python', '-m', 'app.sim.seed', '--reset')
    } finally {
        # Khong de DATABASE_URL cua Ops Chest lot sang buoc import cua Retail-AI
        foreach ($k in $demo.Keys) { Remove-Item "env:$k" -ErrorAction SilentlyContinue }
        $env:PYTHONIOENCODING = 'utf-8'
    }
}

# ---- 7. Docker: Postgres cua Retail-AI, catalog Thanh Lam Mart, Mailpit ----
if ($hasDocker) {
    Write-Step 'Postgres cua Retail-AI va catalog Thanh Lam Mart'
    Invoke-In $RetailAI 'docker' @('compose', 'up', '-d', 'postgres')
    $ready = $false
    for ($i = 0; $i -lt 30 -and -not $ready; $i++) {
        Push-Location $RetailAI
        $null = & docker compose exec -T postgres pg_isready 2>$null
        $ready = ($LASTEXITCODE -eq 0)
        Pop-Location
        if (-not $ready) { Start-Sleep -Seconds 2 }
    }
    if (-not $ready) { throw 'Postgres cua Retail-AI chua san sang sau 60 giay' }
    Invoke-In $RetailAI 'uv' @('run', 'python', 'scripts/import_thanh_lam.py', '--apply')
    Write-Step 'Mailpit (hop thu gia cho email dat hang)'
    # Chi bat Mailpit: Postgres trong compose cua Ops Chest gianh cong 5432 voi Retail-AI
    Invoke-In $OpsChest 'docker' @('compose', 'up', '-d', 'mailpit')
}

# Cau hinh chay cho Claude Code da commit san o bridge\.claude\launch.json: mo thu muc bridge la dung duoc.

# ---- Tong ket ----
Write-Step 'Xong'
if ($needKeys.Count -gt 0) {
    Write-Warn 'Can dien khoa API cua ban (khong dung chung khoa qua GitHub):'
    foreach ($k in $needKeys) { Write-Host "    - $k" }
    Write-Host '    Khong co khoa thi demo van chay: Ops Chest khong chat duoc, kiosk chi tra loi cac cau co dinh.'
}
if (-not $hasDocker) {
    Write-Warn 'Chua chay buoc Docker. Bat Docker Desktop roi chay lai: .\scripts\setup.ps1 -SkipInstall'
    Write-Host '    Thieu Postgres thi kiosk khong tra loi duoc khuyen mai, hang moi ve; thieu Mailpit thi duyet don dat hang bao loi gui email.'
}
Write-Host ''
Write-Host 'Chay demo:  .\scripts\start-demo.ps1'
Write-Host 'Tai khoan Ops Chest: quanly / quanly123 (Store Manager), nhanvien / nhanvien123 (nhan vien)'
