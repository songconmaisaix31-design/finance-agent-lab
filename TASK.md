# Current Task

## Objective

Review Phase 2C safe entrypoint and choose the next business-hardening task.

## Why Now

Phase 2C established a safe public CLI, explicit `guan` city loading, synthetic smoke coverage, and a versioned result contract. The next step is human review before hardening the next business-critical area.

## Acceptance Criteria

- [ ] Review `python -m src.cli plan/run` behavior and exit codes.
- [ ] Review `schemas/run-result.schema.json` and `schemas/run-manifest.schema.json` for frontend-readiness.
- [ ] Confirm `guan` remains the first reference city.
- [ ] Choose Phase 2D: crowd-cost fixture coverage or reconciliation policy hardening.
- [ ] Confirm business owner follow-up for fee rates, whitelists, and unknown-type policy.

## Scope

Human review of the safe entrypoint, solidified result contract, smoke-test boundary, and next Phase 2D task.

## Out of Scope

Implementation work, frontend, database, real finance files, existing `runs` cleanup, external APIs, notifications, remotes, and UI.

## Required Inputs

- Human review of Phase 2C outputs.
- Business confirmation of rules remains pending.

## Validation Plan

- Review Phase 2C final summary.
- Inspect `docs/BASELINE.md`, `README.md`, and `schemas/`.
- Approve or revise the proposed Phase 2D task.

## Known Blockers

Waiting for Phase 2D approval. Business owner must still confirm fee rates, whitelists, and final unknown-type policy.

## Resume Context

- Last files: src/cli.py, src/pipeline_service.py, schemas/run-result.schema.json, tests/test_phase2c_safe_entrypoint.py, README.md
- Last command: .\scripts\check.ps1
- Last result: existing and Phase 2C tests passed
- Next action: 审核 Phase 2C 安全入口和固安 smoke test
