# Local n8n Environment

Version: `v0.3-n8n-mvp`

This package runs n8n plus the Finance Pipeline API adapter.

- n8n image: `n8nio/n8n:2.26.8`
- API base URL inside Docker: `http://finance-pipeline-api:8000`
- Browser URL: `http://127.0.0.1:5678`
- n8n binds only to `127.0.0.1:5678`
- the API is only available on the internal Docker network
- n8n does not mount `/finance-data`; only `finance-pipeline-api` can access the mounted finance data directory
- `/workflows` is mounted read-only inside n8n

Create a local `.env` from `.env.example`; do not commit `.env`.

```powershell
Copy-Item .env.example .env
.\up.ps1
.\import-workflows.ps1
```

If `N8N_ENCRYPTION_KEY` is rotated, update the local ignored `.env` and the n8n instance config in the persistent volume before restarting n8n. Do not print or commit the key.

Workflow export writes to a container temp directory first, copies the export back to the ignored `runs/n8n-workflow-export` folder, sanitizes credentials/headers/tokens, and then updates `workflows/*.json`.

MVP execution path:

1. Open `http://127.0.0.1:5678`.
2. Log in.
3. Open `FIN-00 Master`.
4. Edit only `Run Parameters` if needed.
5. Click `Execute Workflow`.
6. Review `Run Summary`.

Do not use schedules, file watchers, DingTalk notifications, API keys, `/rest/workflows`, browser automation, or `n8n execute` for MVP acceptance.
