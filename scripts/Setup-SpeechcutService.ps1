param(
  [string]$Root,
  [string]$nssm,
  [string]$py,
  [string]$log
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

if (-not $nssm)  { $nssm  = Join-Path $Root 'bin\nssm.exe' }
if (-not $py)    { $py    = Join-Path $Root '.venv\Scripts\python.exe' }
if (-not $log)   { $log   = Join-Path $Root 'logs\svc.log' }

Write-Host "scriptDir: $scriptDir"
Write-Host "Root: $Root"
Write-Host "nssm: $nssm"
Write-Host "py: $py"
Write-Host "log: $log"

if (-not (Test-Path $Root)) {
  throw "Project root not found: $Root"
}

# Python version info
& python -V


# ==== 준비 ====
New-Item -ItemType Directory -Force -Path (Join-Path $Root "logs") | Out-Null

# 혹시 기존 서비스가 있으면 중지/제거(원하면 유지해도 됩니다)
# & $nssm stop speechcut 2>$null | Out-Null
# & $nssm remove speechcut confirm 2>$null | Out-Null

# ==== 새 서비스 설치 ====
# Application/Parameters 한 번에
& $nssm install speechcut "$py" "-X utf8 -m speechcut --poll 60 --timeout 600"

# 작업 디렉터리(중요: 상대경로/ .env / 로그 경로 안정화)
& $nssm set speechcut AppDirectory "$Root"

# 표준출력/표준에러를 같은 파일로(배치 없이 병합)
& $nssm set speechcut AppStdout "$log"
& $nssm set speechcut AppStderr "$log"

# 환경변수(멀티 문자열: 각 항목은 '별도 인자'로 전달)
& $nssm set speechcut AppEnvironmentExtra `
  "PYTHONUNBUFFERED=1" `
  "PYTHONIOENCODING=UTF-8" `
  "PYTHONIOENCODING_ERRORS=replace"

# 자동 시작 + 크래시 재시작
& $nssm set speechcut Start SERVICE_AUTO_START
& $nssm set speechcut AppExit Default Restart

# 시작
& $nssm start speechcut

# 설정/상태 확인
# & $nssm dump speechcut
# sc query speechcut
