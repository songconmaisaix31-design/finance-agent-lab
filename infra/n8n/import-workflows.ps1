$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root

python .\sanitize_n8n_export.py ..\..\workflows

$files = Get-ChildItem -LiteralPath "..\..\workflows" -Filter "*.json" | Sort-Object Name
foreach ($file in $files) {
  Write-Host "Importing $($file.Name)"
  docker compose --env-file .env -f compose.yaml exec -T n8n n8n import:workflow --input="/workflows/$($file.Name)"
}

$subWorkflows = @(
  "fin10intake",
  "fin20normalize",
  "fin30calculate",
  "fin40reconcile",
  "fin50report",
  "fin90error"
)

foreach ($workflowId in $subWorkflows) {
  Write-Host "Activating sub-workflow $workflowId"
  docker compose --env-file .env -f compose.yaml exec -T n8n n8n update:workflow --id=$workflowId --active=true
}

Write-Host "Restarting n8n so Execute Workflow sees the published sub-workflows"
docker compose --env-file .env -f compose.yaml restart n8n
