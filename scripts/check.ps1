$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

$python = Get-Command python -ErrorAction SilentlyContinue
if (-not $python) {
  Write-Error "Python not found. Install Python 3.11+ or activate a local environment."
  exit 4
}

Write-Host "Running existing unit tests"
& $python.Source -m unittest discover -s tests -p "*test*.py"
exit $LASTEXITCODE
