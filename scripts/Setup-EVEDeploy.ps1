param(
  [string]$Root,
  [string]$EcosystemPath
)

$ErrorActionPreference = 'Stop'

$scriptDir = $null
if ($MyInvocation.MyCommand.Path) {
  $scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
}
elseif ($PSCommandPath) {
  $scriptDir = Split-Path -Parent $PSCommandPath
}
elseif ($PSScriptRoot) {
  $scriptDir = $PSScriptRoot
}
else {
  $scriptDir = (Get-Location).Path
}

if (-not $PSBoundParameters.ContainsKey('Root')) {
  $Root = [System.IO.Path]::GetFullPath((Join-Path $scriptDir '..'))
}
else {
  $Root = [System.IO.Path]::GetFullPath($Root)
}

if (-not $EcosystemPath) {
  $EcosystemPath = Join-Path $Root 'ecosystem.config.cjs'
}

Write-Host "Root: $Root"
Write-Host "Ecosystem: $EcosystemPath"

if (-not (Test-Path $Root)) {
  throw "Project root not found: $Root"
}

$venvPy = Join-Path $Root '.venv\Scripts\python.exe'
$installScript = Join-Path $Root 'scripts\install.ps1'
$envExample = Join-Path $Root '.env.example'
$envFile = Join-Path $Root '.env'

# 1. venv + dependencies
if (-not (Test-Path $venvPy)) {
  Write-Host 'Creating virtual environment and installing dependencies...'
  & powershell -ExecutionPolicy Bypass -File $installScript -Root $Root
}
else {
  Write-Host 'Virtual environment exists. Installing/updating package...'
  & $venvPy -m pip install -e $Root
  if (Test-Path (Join-Path $Root 'requirements.txt')) {
    & $venvPy -m pip install -r (Join-Path $Root 'requirements.txt')
  }
}

# 2. .env
if (-not (Test-Path $envFile) -and (Test-Path $envExample)) {
  Copy-Item $envExample $envFile
  Write-Host "Created .env from .env.example"
}

# 3. data/logs directories
@(
  (Join-Path $Root 'data\jobs'),
  (Join-Path $Root 'logs')
) | ForEach-Object {
  New-Item -ItemType Directory -Force -Path $_ | Out-Null
}

# 4. PM2
$pm2 = Get-Command pm2 -ErrorAction SilentlyContinue
if (-not $pm2) {
  Write-Warning 'PM2 is not installed. Install Node.js, then run: npm install -g pm2'
}
else {
  if (-not (Test-Path $EcosystemPath)) {
    throw "ecosystem config not found: $EcosystemPath"
  }

  $ecosystem = Get-Content $EcosystemPath -Raw
  $ecosystem = $ecosystem -replace "cwd:\s*'[^']*'", "cwd: '$($Root -replace '\\', '/')'"
  $patchedEcosystem = Join-Path $Root 'ecosystem.config.local.cjs'
  Set-Content -Path $patchedEcosystem -Value $ecosystem -Encoding UTF8

  & pm2 delete eve-api 2>$null | Out-Null
  & pm2 start $patchedEcosystem
  & pm2 save
  Write-Host 'PM2 started eve-api. Check: pm2 status'
}

# 5. nginx guidance
Write-Host ''
Write-Host 'nginx setup:'
Write-Host "  1. Copy deploy\nginx.conf to your nginx conf directory"
Write-Host '  2. Update server_name and paths as needed'
Write-Host '  3. Reload nginx: nginx -s reload'
Write-Host ''
Write-Host 'API health check: http://127.0.0.1:8001/health'
