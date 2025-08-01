# to install, run:
# powershell -ExecutionPolicy Bypass -File .\scripts\install.ps1

# to run, run:
# .\.venv\Scripts\speechcut.exe --poll 60 --timeout 600

param(
  [string]$Root = "$PSScriptRoot\..",
  [string]$Venv = "$Root\.venv",
  [string]$Wheelhouse = "$Root\vendor\wheelhouse"
  [string]$VcRedist = "$Root\vendor\etc\VC_redist.x64.exe"
)

Write-Host "Root: $Root"
Write-Host "Venv: $Venv"
Write-Host "Wheelhouse: $Wheelhouse"
Write-Host "VcRedist: $VcRedist"

# Python version info
& python -V

# venv creation
python -m venv $Venv
if (-not (Test-Path "$Venv\Scripts\pip.exe")) {
  throw "venv creation failed: $Venv"
}

# install dependencies (off-line)
if (-not (Test-Path $Wheelhouse)) {
  throw "Wheelhouse not found: $Wheelhouse"
}
& "$Venv\Scripts\pip.exe" install --no-index --find-links "$Wheelhouse" -r "$Root\requirements.txt"
& "$Venv\Scripts\pip.exe" install --no-index --find-links "$Wheelhouse" -e "$Root"

# make directory for logs
New-Item -ItemType Directory -Force -Path "$Root\logs" | Out-Null

# check FFmpeg and FFprobe
# (project-root\bin\ffmpeg.exe, ffprobe.exe MUST be ADDED)
$ffmpeg = Join-Path $Root "bin\ffmpeg.exe"
$ffprobe = Join-Path $Root "bin\ffprobe.exe"
if (Test-Path $ffmpeg) {
  & $ffmpeg -version | Select-Object -First 1 | Write-Host
} else {
  Write-Warning "ffmpeg.exe not found at $ffmpeg"
}
if (Test-Path $ffprobe) {
  & $ffprobe -version | Select-Object -First 1 | Write-Host
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
