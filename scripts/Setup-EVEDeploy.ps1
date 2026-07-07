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
$cmdLauncher = Join-Path $Root 'scripts\start-eve-api.cmd'

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

function Get-Pm2Processes {
  $raw = & pm2 jlist 2>$null
  if (-not $raw) { return @() }
  try {
    return @($raw | ConvertFrom-Json)
  }
  catch {
    return @()
  }
}

function Remove-StalePm2Processes {
  foreach ($proc in Get-Pm2Processes) {
    if ($proc.name -eq 'eve-api' -or $proc.name -match 'ecosystem\.config') {
      Write-Host "Removing stale PM2 process: $($proc.name) (id=$($proc.pm_id))"
      & pm2 delete $proc.pm_id 2>&1 | Out-Null
    }
  }
}

function Test-EveApiOnline {
  param([int]$WaitSeconds = 15)

  $deadline = (Get-Date).AddSeconds($WaitSeconds)
  while ((Get-Date) -lt $deadline) {
    $eve = Get-Pm2Processes | Where-Object { $_.name -eq 'eve-api' } | Select-Object -First 1
    if ($eve -and $eve.pm2_env.status -eq 'online') {
      return $true
    }
  }
  return $false
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
  if (-not (Test-Path $cmdLauncher)) {
    throw "CMD launcher not found: $cmdLauncher"
  }

  $pythonw = Join-Path $Root '.venv\Scripts\pythonw.exe'
  if (-not (Test-Path $pythonw)) {
    throw "pythonw not found (required for headless PM2): $pythonw"
  }

  $templatePath = Join-Path $Root 'ecosystem.config.cjs'
  $template = Get-Content $templatePath -Raw
  if ($template -notmatch '__EVE_ROOT__') {
    Write-Warning 'ecosystem.config.cjs has no __EVE_ROOT__ placeholder (already patched?)'
  }

  $rootPosix = $Root -replace '\\', '/'
  $patched = $template -replace '__EVE_ROOT__', $rootPosix
  Set-Content -Path $EcosystemPath -Value $patched -Encoding UTF8
  Write-Host "Patched PM2 config: $EcosystemPath"

  Write-Host 'Syncing PM2 daemon (pm2 update)...'
  $prevEap = $ErrorActionPreference
  $ErrorActionPreference = 'SilentlyContinue'
  & pm2 update 2>&1 | Out-Null
  $ErrorActionPreference = $prevEap

  Remove-StalePm2Processes

  Write-Host 'Starting eve-api via ecosystem.config.cjs...'
  & pm2 start $EcosystemPath

  if (-not (Test-EveApiOnline)) {
    $bad = Get-Pm2Processes | Where-Object { $_.name -match 'ecosystem\.config' } | Select-Object -First 1
    if ($bad) {
      Write-Warning "PM2 did not load ecosystem config (process name: $($bad.name)). Falling back to direct CMD start."
      & pm2 delete $bad.pm_id 2>&1 | Out-Null
      $cmdPosix = $cmdLauncher -replace '\\', '/'
      & pm2 start $cmdPosix --name eve-api --cwd $rootPosix --interpreter none
    }
  }

  if (-not (Test-EveApiOnline)) {
    Write-Host ''
    Write-Host 'PM2 logs (last 40 lines):'
    & pm2 logs eve-api --lines 40 --nostream
    throw 'eve-api did not reach online status. Check logs above and C:\eve\logs\eve-api.log'
  }

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
