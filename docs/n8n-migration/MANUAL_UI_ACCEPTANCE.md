# Manual UI Acceptance

Version: `v0.3-n8n-mvp`

Use the browser UI as the official MVP execution path.

1. Confirm Docker is running: `infra/n8n/up.ps1`.
2. Open `http://127.0.0.1:5678` in a browser and log in.
3. Open `FIN-00 Master`.
4. Edit only `Run Parameters` if needed; paths must use `/finance-data/...`, not `D:\...`.
5. Click `Execute Workflow`.
6. Confirm `FIN-10 Intake`, `FIN-20 Normalize`, `FIN-30 Calculate`, `FIN-40 Reconcile`, and `FIN-50 Report` all show success.
7. Confirm `Run Summary` shows `run_id`, financial metrics, warning/error counts, and `report_path`.
8. Open the report path on the mounted data directory and confirm the Excel workbook has 14 sheets.

Do not use API keys, `/rest/workflows`, browser automation, schedules, or `n8n execute` for MVP acceptance.
