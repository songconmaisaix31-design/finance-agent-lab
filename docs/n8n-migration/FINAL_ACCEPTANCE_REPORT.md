# Final Acceptance Report

Second-round acceptance date: 2026-06-29.

## Verdict

The second-round acceptance passed for the local synthetic fixture after importing and executing the n8n workflows in Docker Compose.

Important qualification: FIN-20 Normalize and FIN-30 Calculate are currently contract-only adapter stages, and FIN-40 Reconcile still invokes the existing full Python pipeline through `pipeline_service.run_request()`. This is recorded as an implementation risk, not hidden as real isolated stage execution.

## Docker and n8n

- Docker Compose project: `infra/n8n/compose.yaml`
- n8n image: `n8nio/n8n:2.26.8`
- n8n URL: `http://127.0.0.1:5678`
- API service: internal Compose network only, port `8000/tcp`
- Data mapping used for acceptance: host `D:\AI-Workspace\Projects\finance-agent-lab\runs\n8n-synthetic-data` to container `/finance-data`
- API health: `{"status":"ok","service":"finance-pipeline-api","version":"1.0.0"}`
- Final container status:
  - `n8n-finance-pipeline-api-1`: Up, healthy
  - `n8n-n8n-1`: Up, `127.0.0.1:5678->5678`

Imported workflows:

- `fin00master` / `FIN-00 Master`
- `fin10intake` / `FIN-10 Intake`
- `fin20normalize` / `FIN-20 Normalize`
- `fin30calculate` / `FIN-30 Calculate`
- `fin40reconcile` / `FIN-40 Reconcile`
- `fin50report` / `FIN-50 Report`
- `fin90error` / `FIN-90 Error`

FIN-00 remains Manual Trigger only. Sub-workflows are published/active so Execute Workflow can call them; no schedules, watchers, or notifications were added.

## Python Service

- Run id: `guan-service-round2-gated`
- Input: synthetic fixture under `runs/n8n-synthetic-data/guan/incoming`
- Status: `success`
- Summary: `runs/n8n-synthetic-data/guan/runs/guan-service-round2-gated/result-summary.json`
- Artifact: `artifacts/guan-synthetic-report.xlsx`

## CLI

- Command path: `python -m src.cli run ... --execute`
- Run id: `guan-cli-round2-gated`
- Status: `success`
- The CLI result matched Python service output on all compared financial metrics, row counts, reconciliation status, warnings/errors, artifact count, and report sheets.

## API

- Run id: `guan-api-round2-gated`
- Stages called through HTTP: `intake`, `normalize`, `calculate`, `reconcile`, `report`
- Status by stage:
  - `intake`: `success`
  - `normalize`: `success`, contract-only
  - `calculate`: `success`, contract-only
  - `reconcile`: `success`
  - `report`: `success`
- FastAPI success endpoints now declare response models: `HealthResponse`, `RunCreatedResponse`, `RunStatusResponse`, `StageResultResponse`, and `ArtifactListResponse`.
- Stage path parameter is limited to `intake`, `normalize`, `calculate`, `reconcile`, and `report`.
- Error responses use the unified error model for 400, 404, 409, 422, and 500.

## n8n FIN-00

- Actual FIN-00 execution run id: `guan-20260629T162806Z-203c3230`
- Execution mode used for local acceptance: n8n CLI execution of imported FIN-00 against the running API container.
- Result: `success`
- Last node: `Execute FIN-50 Report`
- FIN-00 includes per-stage gates after intake, normalize, and calculate, plus the final reconciliation quality gate.
- n8n did not pass detailed rows between nodes; it passed run ids, status, metrics, and artifact paths.

## Consistency Comparison

The same synthetic fixture was run through Python service, CLI, API, and n8n FIN-00. Comparison file: `runs/round2-acceptance-comparison.json`.

All four paths matched:

| Field | Value |
| --- | --- |
| `food_income_total` | `10.00` |
| `retail_income_total` | `0` |
| `food_hq_fee` | `0.2000` |
| `retail_hq_fee` | `0.00` |
| `food_team_delivery_cost` | `4.60` |
| `retail_team_delivery_cost` | `0.00` |
| `food_order_count` | `1` |
| `retail_order_count` | `0` |
| `crowd_total` | `100.00` |
| `catering_normal` | `10.00` |
| `catering_group` | `20.00` |
| `retail_normal` | `30.00` |
| `retail_group` | `40.00` |
| `reconciliation_status` | `passed` |
| `reconciliation_failed` | `0` |
| `warnings` | `1` |
| `errors` | `0` |
| `artifact_count` | `1` |
| `sheet_count` | `14` |

The report has 14 sheets because `src/report.py::generate_report()` creates 14 worksheets:

1. `01_总览`
2. `02_餐饮收入`
3. `03_零售收入`
4. `04_餐饮支出`
5. `05_零售支出`
6. `06_众包成本分层`
7. `07_账单成本单量对账`
8. `08_成本表内部对账`
9. `09_未配置收入类型`
10. `10_未识别配送类型`
11. `11_异常数据`
12. `12_运行信息`
13. `13_自动对账结果`
14. `14_自配送到店自取三方代补警告`

This is consistent with the old output contract and was not changed by the n8n adapter.

## Error Workflow

- Error-path run id: `guan-20260629T162914Z-d5d223c2`
- Fault injected: temporarily removed `billing_food.xlsx` from the synthetic fixture and restored it after execution.
- FIN-00 route: `Execute FIN-10 Intake` -> `Intake Gate` false branch -> `Execute FIN-90 Error`
- FIN-90 output:
  - `run_id`: `guan-20260629T162914Z-d5d223c2`
  - `stage`: `intake`
  - `error_code`: `INPUT_VALIDATION_FAILED`
  - `message`: `Missing required synthetic-compatible inputs: ['billing_food.xlsx']`
  - `artifact_path`: empty string

## Idempotency Test

Repeated calls to completed `reconcile` and `report` for run `guan-20260629T161537Z-6379c602` returned the existing terminal success results.

- `reconcile` repeat HTTP status: 200
- `report` repeat HTTP status: 200
- `result-summary.json` SHA unchanged: true
- report `.xlsx` SHA unchanged: true
- report stage remained `success`

## Container Restart Recovery

The API container was restarted and queried after health recovery.

- `GET /health`: recovered successfully
- `GET /runs/guan-20260629T161537Z-6379c602`: HTTP 200
- run status after restart: `success`
- report stage after restart: `success`
- artifact count after restart: 1

This validates persisted run state via run-directory files and the API state index, not memory-only state.

## Path Isolation

Path isolation was verified inside the API container.

| Scenario | Result |
| --- | --- |
| Windows host path `D:\...` passed to container API | HTTP 409, `STAGE_CONTRACT_INVALID`, outside allowlist |
| Output directory nested inside input directory | intake failed, `PATH_SAFETY_REJECTED` |
| City `guan` using `/finance-data/xianghe/incoming` | intake failed, `CITY_STORAGE_NAMESPACE_MISMATCH` |

The API must receive container paths such as `/finance-data/guan/incoming`; it must not rely on `D:\...` paths inside the container.

## Large Data Performance

- Test: `FINANCE_RUN_LARGE_TESTS=1 python -m unittest tests.test_large_synthetic_performance`
- Synthetic size: more than 100,000 generated rows
- Result: `OK`
- Runtime: 42.743 seconds
- Data source: generated synthetic workbook, no real financial data

## Test Results

- Workflow JSON parse smoke: OK
- `python -m unittest tests.test_n8n_adapter`: 10 tests, OK
- `.\scripts\check.ps1`: 71 tests, OK, 1 skipped by default
- `FINANCE_RUN_LARGE_TESTS=1 python -m unittest tests.test_large_synthetic_performance`: 1 test, OK
- Docker health check: OK
- n8n FIN-00 success execution: OK
- n8n FIN-90 error execution: OK

## Not Completed / Manual Items

- True isolated `normalize`, `calculate`, `reconcile`, and `report` Python stages are not yet implemented. The current adapter preserves compatibility by keeping formulas inside the existing pipeline.
- The n8n UI is available at `http://127.0.0.1:5678`; user login and credential setup, if any, remain manual local operations.
- Production `.env` creation remains manual. Only `.env.example` should be versioned.
- No production directory watcher, schedule, DingTalk notification, or other business automation was enabled.

## Suggested Commits

1. `docs: add n8n migration audit and acceptance documentation`
2. `feat: add finance pipeline adapter cli and fastapi contracts`
3. `feat: add docker compose n8n workflow package`
4. `test: add adapter contract idempotency path and performance coverage`
