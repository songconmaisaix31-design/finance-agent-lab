$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root

$health = docker compose --env-file .env -f compose.yaml exec -T finance-pipeline-api python -c "import json, urllib.request; print(urllib.request.urlopen('http://127.0.0.1:8000/health').read().decode())"
$payload = $health | ConvertFrom-Json
if ($payload.status -ne "ok") {
  Write-Error "Finance Pipeline API health check failed."
}

Write-Host "Finance Pipeline API health: ok"
Write-Host "n8n URL: http://127.0.0.1:5678"
