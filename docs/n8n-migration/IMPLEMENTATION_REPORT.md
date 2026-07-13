# Superseded Note

This report describes the earlier n8n adapter migration state. It is superseded for Phase 3 by `PHASE3_AUDIT.md`, `STAGE_CONTRACTS.md`, `RECOVERY_MODEL.md`, and `PHASE3_ACCEPTANCE_REPORT.md`.

# Implementation Report

Date: 2026-06-29

## Delivered

- Added platform-neutral pipeline definition: `orchestration/pipeline.yaml`.
- Added quality gates: `quality-gates.yaml`.
- Added JSON Schemas:
  - `schemas/run-request.schema.json`
  - `schemas/stage-result.schema.json`
  - `schemas/reconciliation-result.schema.json`
  - `schemas/artifact-manifest.schema.json`
- Added reusable adapter module: `src.pipeline_adapter`.
- Extended existing CLI without deleting or replacing it:
  - `run`
  - `intake`
  - `normalize`
  - `calculate`
  - `reconcile`
  - `report`
- Added FastAPI adapter: `src.api`.
- Added static OpenAPI snapshot: `docs/n8n-migration/openapi.json`.
- Added local n8n Docker Compose package under `infra/n8n`.
- Added workflow template package under `workflows`.
- Added n8n import, export, and sanitize scripts.
- Added adapter tests: `tests/test_n8n_adapter.py`.

## Business Logic Boundary

No existing income, headquarters fee, team delivery cost, crowd cost, reconciliation, or report formulas were rewritten. The `reconcile` stage delegates to `src.pipeline_service.run_request`, which uses the existing calculation modules.

## Test Results

Baseline before implementation:

```text
.\scripts\check.ps1
Ran 60 tests in 29.942s
OK
```

After implementation:

```text
.\scripts\check.ps1
Ran 65 tests in 34.742s
OK
```

Additional smoke checks:

- Workflow JSON parsed successfully.
- `infra\n8n\sanitize_n8n_export.py workflows` completed successfully.
- Static OpenAPI generated from FastAPI app.

## Acceptance Comparison

The same synthetic fixture was run through:

1. Python service layer: `src.pipeline_service.run_request`
2. CLI: `python -m src.cli run ... --execute`
3. API: `POST /runs` plus stages `intake`, `normalize`, `calculate`, `reconcile`, `report`

Comparable outputs matched exactly for:

- food income total: `10.00`
- retail income total: `0`
- food headquarters fee: `0.2000`
- retail headquarters fee: `0.00`
- food team delivery cost: `4.60`
- retail team delivery cost: `0.00`
- food order count: `1`
- retail order count: `0`
- crowd total: `100.00`
- crowd buckets:
  - `catering_normal`: `10.00`
  - `catering_group`: `20.00`
  - `retail_normal`: `30.00`
  - `retail_group`: `40.00`
- reconciliation status: `passed`
- reconciliation errors: `0`
- warnings: `1`
- artifact count: `1`
- report sheet count: `14`
- report sheet names: identical

Allowed differences:

- `run_id`
- timestamps
- local temporary paths

## Docker Status

Docker checks performed:

```text
docker version
Client Version: 29.5.3
Result: failed to connect to Docker Desktop Linux engine
```

```text
docker compose version
Docker Compose version v5.1.4
```

Containers were not started because the Docker daemon was not reachable. No system-level Docker changes were attempted.

## n8n

Configured local URL:

```text
http://127.0.0.1:5678
```

Workflow templates created:

- `FIN-00 Master`
- `FIN-10 Intake`
- `FIN-20 Normalize`
- `FIN-30 Calculate`
- `FIN-40 Reconcile`
- `FIN-50 Report`
- `FIN-90 Error`

Imported workflows:

- Not imported during implementation because Docker daemon was not reachable.

Manual import command after Docker is running:

```powershell
cd D:\AI-Workspace\Projects\finance-agent-lab\infra\n8n
Copy-Item .env.example .env
.\up.ps1
.\import-workflows.ps1
```

## Manual Items Remaining

- Start Docker Desktop or the configured Docker engine.
- Create local `infra\n8n\.env` from `.env.example` and set a real local `N8N_ENCRYPTION_KEY`.
- Run `infra\n8n\up.ps1`.
- Run `infra\n8n\import-workflows.ps1`.
- Execute `FIN-00 Master` manually in n8n against a synthetic or approved desensitized input path.

## Suggested Commits

1. `docs: add n8n migration audit and implementation report`
2. `feat: add pipeline stage contracts and adapter`
3. `feat: add finance pipeline FastAPI adapter`
4. `feat: add local n8n compose environment and workflows`
5. `test: add n8n adapter contract and smoke tests`
