$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root

if (-not (Test-Path -LiteralPath ".env")) {
  Write-Error "Create infra\n8n\.env from .env.example before starting n8n."
}

docker version | Out-Host
docker compose version | Out-Host
docker compose --env-file .env -f compose.yaml up -d --build
