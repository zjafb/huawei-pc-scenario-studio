param([int]$Port = 7861)
$ErrorActionPreference = 'Stop'
$projectDir = Split-Path -Parent $PSScriptRoot
$pythonExe = Join-Path $projectDir '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $pythonExe)) {
    throw 'Python environment missing. Run: python -m venv .venv ; then install requirements.txt as described in README.'
}
if ($Port -lt 1024 -or $Port -gt 65535) { throw 'Choose a port between 1024 and 65535.' }
$env:PORT = [string]$Port
$env:GRADIO_ANALYTICS_ENABLED = 'False'
$env:PYTHONIOENCODING = 'utf-8'
Push-Location -LiteralPath $projectDir
try {
    Write-Host "Starting local app at http://127.0.0.1:$Port/ ; stop with Ctrl+C."
    & $pythonExe run.py
    if ($LASTEXITCODE -ne 0) { throw 'Application stopped with an error. Review the message above.' }
} finally { Pop-Location }
