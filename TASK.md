# Current Task

## Objective

Review the Phase 2D crowd-cost contract and approve Phase 2E reconciliation hardening.

## Why Now

Phase 2D established synthetic crowd-cost fixtures, stable bucket IDs, fail-closed unknown handling, and `result-summary.json` crowd-cost output. The next high-value task is cross-table reconciliation policy hardening.

## Acceptance Criteria

- [ ] Review existing crowd-cost bucket IDs and synthetic coverage.
- [ ] Review `costs.crowd` in `schemas/run-result.schema.json`.
- [ ] Confirm negative, zero, duplicate, and unknown crowd-cost policies.
- [ ] Approve Phase 2E cross-table reconciliation strategy hardening.
- [ ] Confirm business owner follow-up for fee rates, whitelists, bucket mappings, and unknown-type policy.

## Scope

Human review of the crowd-cost result contract, synthetic test boundary, and next Phase 2E reconciliation task.

## Out of Scope

Implementation work, frontend, database, real finance files, existing `runs` cleanup, external APIs, notifications, remotes, UI, and second-city onboarding.

## Required Inputs

- Human review of Phase 2D outputs.
- Business confirmation of rules remains pending.

## Validation Plan

- Review Phase 2D final summary.
- Inspect `docs/BASELINE.md`, `README.md`, `schemas/`, and `src/crowd_cost_contract.py`.
- Approve or revise the proposed Phase 2E task.

## Known Blockers

Waiting for Phase 2E approval. Business owner must still confirm fee rates, whitelists, crowd-cost bucket rules, and final unknown-type policy.

## Resume Context

- Last files: src/crowd_cost_contract.py, src/crowd_cost.py, src/crowd_cost_fast.py, src/pipeline_service.py, tests/test_crowd_cost_contract.py
- Last command: .\scripts\check.ps1
- Last result: existing, Phase 2C, and Phase 2D tests passed
- Next action: 审核 Phase 2D 众包成本契约并批准 Phase 2E
