# to install, run:
# powershell -ExecutionPolicy Bypass -File .\scripts\install.ps1

# to run, run:
# .\.venv\Scripts\speechcut.exe --poll 60 --timeout 600

param(
  [string]$Root,
  [string]$Venv,
  [string]$Wheelhouse,
  [string]$VcRedist
)

$ErrorActionPreference = 'Stop'

# get script directory

$scriptDir = $null

if ($MyInvocation.MyCommand.Path) {
  $scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
}
elseif ($PSCommandPath) {
  # PS 5+
  $scriptDir = Split-Path -Parent $PSCommandPath
}
elseif ($PSScriptRoot) {
  # PS 3+
  $scriptDir = $PSScriptRoot
}
else {
  $scriptDir = (Get-Location).Path
}

if (-not $PSBoundParameters.ContainsKey('Root')) {
  # install.ps1 상위 폴더를 프로젝트 루트로
  $Root = [System.IO.Path]::GetFullPath((Join-Path $scriptDir '..'))
} else {
  $Root = [System.IO.Path]::GetFullPath($Root)
}

if (-not $Venv)        { $Venv        = Join-Path $Root '.venv' }
if (-not $Wheelhouse)  { $Wheelhouse  = Join-Path $Root 'vendor\wheelhouse' }
if (-not $VcRedist)    { $VcRedist    = Join-Path $Root 'vendor\etc\VC_redist.x64.exe' }

Write-Host "scriptDir: $scriptDir"
Write-Host "Root: $Root"
Write-Host "Venv: $Venv"
Write-Host "Wheelhouse: $Wheelhouse"
Write-Host "VcRedist: $VcRedist"

if (-not (Test-Path $Root)) {
  throw "Project root not found: $Root"
}

# Python version info
& python -V

# venv creation
Write-Host "Creating venv at $Venv ..."

python -m venv $Venv
if (-not (Test-Path "$Venv\Scripts\pip.exe")) {
  throw "venv creation failed: $Venv"
}

$pip = Join-Path $Venv 'Scripts\pip.exe'
if (-not (Test-Path $pip)) {
  throw "venv creation failed (pip not found): $Venv"
}

# install dependencies (off-line)
if (-not (Test-Path $Wheelhouse)) {
  throw "Wheelhouse not found: $Wheelhouse"
}

$regFile = Join-Path $Root 'requirements.txt'
if (-not (Test-Path $regFile)) {
  throw "requirements.txt not fount: $regFile"
}

Write-Host "Installing requirements from wheelhouse (offline) ..."
& $pip install --no-index --find-links "$Wheelhouse" -r "$regFile"

Write-Host "Installling project in editable mode (offline) ..."
& $pip install --no-index --find-links "$Wheelhouse" -e "$Root"

# make directory for logs
$logDir = Join-Path $Root 'logs'
New-Item -ItemType Directory -Force -Path "$logDir" | Out-Null

# check FFmpeg and FFprobe
# (project-root\bin\ffmpeg.exe, ffprobe.exe MUST be ADDED)
$ffmpeg = Join-Path $Root "bin\ffmpeg.exe"
$ffprobe = Join-Path $Root "bin\ffprobe.exe"

if (Test-Path $ffmpeg) {
  try {
    & $ffmpeg -version | Select-Object -First 1 | Write-Host
  } catch {
    Write-Warning "ffmpeg exists but failed to run: $ffmpeg. $_"
  }
} else {
  Write-Warning "ffmpeg.exe not found at $ffmpeg"
}
if (Test-Path $ffprobe) {
  try {
    & $ffprobe -version | Select-Object -First 1 | Write-Host
  } catch {
    Write-Warning "ffprobe exists but failed to run: $ffprobe. $_"
  }
} else {
  Write-Warning "ffprobe.exe not found at $ffprobe"
}

# check VC++ runtime and install

function Test-VcRedistInstalled {
  $key = "HKLM:\SOFTWARE\Microsoft\VisualStudio\14.0\VC\Runtimes\x64"
  if (Test-Path $key) {
    $v = (Get-ItemProperty $key).Installed
    return ($v -eq 1)
  }
  return $false
}

if (-not (Test-VcRedistInstalled)) {
  if (Test-Path $VcRedist) {
    Write-Host "Installing VC++ Redistributable (x64)..."
    Start-Process -FilePath $VcRedist -ArgumentList "/install","/quiet","/norestart" -Wait
  } else {
    Write-Warning "VC_redist.x64.exe not found at $VcRedist. Torch may fail to load (WinError 126)."
  }
}

Write-Host "Installed. To run:"
Write-Host "`"$Venv\Scripts\speechcut.exe`" --poll 60 --timeout 600"
