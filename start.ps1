$ErrorActionPreference = 'Stop'
$labUrl = 'http://127.0.0.1:8774'
$labPython = Join-Path $env:USERPROFILE '.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'
if (-not (Test-Path -LiteralPath $labPython)) { throw 'Bundled Python unavailable. Run app.py with Python 3.12 or newer.' }
$labState = $null
try { $labState = Invoke-RestMethod "$labUrl/api/state" -TimeoutSec 2 } catch {}
if ($null -ne $labState -and $labState.app -ne 'emergence-sandbox') { throw 'Port 8774 is occupied by another application.' }
if ($null -eq $labState) {
  $labData = Join-Path $PSScriptRoot 'data'
  New-Item -ItemType Directory -Path $labData -Force | Out-Null
  $labScript = Join-Path $PSScriptRoot 'app.py'
  Start-Process -FilePath $labPython -ArgumentList @('-u', ('"' + $labScript + '"'), '--port', '8774') -WorkingDirectory $PSScriptRoot -WindowStyle Hidden -RedirectStandardOutput (Join-Path $labData 'server.log') -RedirectStandardError (Join-Path $labData 'server-error.log') | Out-Null
  for ($labAttempt=0; $labAttempt -lt 15; $labAttempt++) {
    Start-Sleep -Milliseconds 500
    try { $labState = Invoke-RestMethod "$labUrl/api/state" -TimeoutSec 2; break } catch {}
  }
}
if ($labState.app -ne 'emergence-sandbox') { throw 'Sandbox did not become ready. Inspect data/server-error.log.' }
Start-Process $labUrl
