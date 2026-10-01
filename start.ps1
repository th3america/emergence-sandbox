[CmdletBinding()]
param(
  [int]$Port = 8774,
  [string]$Python,
  [string]$Data
)
$ErrorActionPreference = 'Stop'
$labUrl = "http://127.0.0.1:$Port"
$labPython = $Python
if (-not $labPython) { $labPython = $env:EMERGENCE_PYTHON }
if (-not $labPython) {
  $pythonCommand = Get-Command python -ErrorAction SilentlyContinue
  if ($null -ne $pythonCommand) { $labPython = $pythonCommand.Source }
}
if (-not $labPython) {
  $bundledPython = Join-Path $env:USERPROFILE '.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'
  if (Test-Path -LiteralPath $bundledPython) { $labPython = $bundledPython }
}
if (-not $labPython -or -not (Test-Path -LiteralPath $labPython)) {
  throw 'Python was not found. Supply -Python, set EMERGENCE_PYTHON, or put Python 3.10+ on PATH.'
}
$labState = $null
try { $labState = Invoke-RestMethod "$labUrl/api/state" -TimeoutSec 2 } catch {}
if ($null -ne $labState -and $labState.app -ne 'emergence-sandbox') { throw 'Port 8774 is occupied by another application.' }
if ($null -eq $labState) {
  $labData = if ($Data) { $Data } else { Join-Path $PSScriptRoot 'data' }
  New-Item -ItemType Directory -Path $labData -Force | Out-Null
  $labScript = Join-Path $PSScriptRoot 'app.py'
  $labDatabase = Join-Path $labData 'lab.sqlite'
  Start-Process -FilePath $labPython -ArgumentList @('-u', ('"' + $labScript + '"'), '--port', "$Port", '--data', ('"' + $labDatabase + '"')) -WorkingDirectory $PSScriptRoot -WindowStyle Hidden -RedirectStandardOutput (Join-Path $labData 'server.log') -RedirectStandardError (Join-Path $labData 'server-error.log') | Out-Null
  for ($labAttempt=0; $labAttempt -lt 15; $labAttempt++) {
    Start-Sleep -Milliseconds 500
    try { $labState = Invoke-RestMethod "$labUrl/api/state" -TimeoutSec 2; break } catch {}
  }
}
if ($labState.app -ne 'emergence-sandbox') { throw 'Sandbox did not become ready. Inspect data/server-error.log.' }
Start-Process $labUrl
