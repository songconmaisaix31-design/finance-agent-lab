$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot = Resolve-Path (Join-Path $Root "..\..")
$WorkflowRoot = Join-Path $RepoRoot "workflows"
$LocalExportRoot = Join-Path $RepoRoot "runs\n8n-workflow-export"
$ContainerExportRoot = "/tmp/n8n-workflow-export"

Set-Location $Root

function Invoke-Checked {
  param(
    [Parameter(Mandatory = $true)]
    [scriptblock] $Command,
    [Parameter(Mandatory = $true)]
    [string] $Description
  )
  & $Command
  if ($LASTEXITCODE -ne 0) {
    throw "$Description failed with exit code $LASTEXITCODE"
  }
}

for ($attempt = 1; $attempt -le 30; $attempt++) {
  try {
    $response = Invoke-WebRequest -UseBasicParsing http://127.0.0.1:5678/healthz -TimeoutSec 3
    if ($response.StatusCode -eq 200) {
      break
    }
  } catch {
    $null = $_
  }
  if ($attempt -eq 30) {
    throw "n8n health check did not become ready"
  }
  Start-Sleep -Seconds 2
}

for ($attempt = 1; $attempt -le 10; $attempt++) {
  docker compose --env-file .env -f compose.yaml exec -T n8n node -e "process.exit(0)" | Out-Null
  if ($LASTEXITCODE -eq 0) {
    break
  }
  if ($attempt -eq 10) {
    throw "n8n container exec did not become ready"
  }
  Start-Sleep -Seconds 2
}

if (Test-Path -LiteralPath $LocalExportRoot) {
  Remove-Item -LiteralPath $LocalExportRoot -Recurse -Force
}
New-Item -ItemType Directory -Force -Path $LocalExportRoot | Out-Null

Invoke-Checked { docker compose --env-file .env -f compose.yaml exec -T n8n sh -lc "rm -rf $ContainerExportRoot && mkdir -p $ContainerExportRoot && n8n export:workflow --backup --output=$ContainerExportRoot" } "n8n workflow export"

$containerId = docker compose --env-file .env -f compose.yaml ps -q n8n
if (-not $containerId) {
  throw "n8n container not found"
}

Invoke-Checked { docker cp "${containerId}:$ContainerExportRoot/." $LocalExportRoot } "docker cp workflow export"
Invoke-Checked { python .\sanitize_n8n_export.py $LocalExportRoot --output-dir $WorkflowRoot --normalize-filenames } "workflow sanitize"

Write-Host "Sanitized workflows exported to $WorkflowRoot"
