# Phase 3 Review Findings

Version: `v0.3-n8n-mvp`

Review date: 2026-06-30.

## Current Status

1. Five Python stages are real persisted stages.
   - `intake` writes input manifest and run context.
   - `normalize` writes normalized SQLite data and manifests.
   - `calculate` writes calculation result and manifest.
   - `reconcile` writes quality gate and reconciliation stage outputs.
   - `report` generates the final 14 Sheet Excel report and final run contracts.

2. n8n MVP visual workflow is manual and browser-driven.
   - Official MVP operation path is opening `http://127.0.0.1:5678`, opening `FIN-00 Master`, and clicking `Execute Workflow`.
   - n8n API keys are not required for MVP acceptance.
   - `n8n execute` is not the MVP path because it conflicts with the running web container task broker.

3. FIN-00 Master is organized as a visual business flow.
   - Users only edit `Run Parameters`.
   - Success path ends at `Run Summary`.
   - All failure branches go to `FIN-90 Error`.

4. FIN-90 Error now emits a fixed safe error summary.
   - It includes run id, failed stage, error code, readable message, retryable flag, and artifact path.
   - It does not send notifications or expose credentials.

5. No new business features were added.
   - No schedules, watchers, DingTalk notifications, queues, Redis, Celery, new formulas, or new city-specific rules were introduced.

6. Local n8n secret handling was tightened.
   - The ignored local `infra/n8n/.env` encryption key was rotated without printing the value.
   - The persistent n8n volume config was updated to match the rotated key.
   - No encryption key is stored in tracked files.

7. n8n no longer has direct finance data access.
   - The n8n service mounts only its persistent app volume and read-only `/workflows`.
   - Only `finance-pipeline-api` mounts `/finance-data`.

8. Workflow export no longer writes into read-only `/workflows`.
   - Export writes to container `/tmp`, copies to ignored `runs/n8n-workflow-export`, sanitizes, and then updates tracked workflow templates.

## Backlog

- Automated stale lease detection and explicit resume remain backlog items, outside `v0.3-n8n-mvp`.
- Full manual browser execution evidence must be captured by the user after logging into n8n.
- Additional UI screenshots can be added later, but browser automation is intentionally not part of this MVP.

## Notes

- Docker Compose keeps n8n bound to `127.0.0.1:5678`.
- The API remains internal to the Docker network.
- Real `.env`, tokens, cookies, credentials, and financial source data must remain out of Git.
