# Current Task

## Objective

Review the Phase 2E reconciliation contract and decide the next approved phase.

## Why Now

Phase 2E established a single technical reconciliation contract for the safe public pipeline. The system now exposes deterministic checks in `result-summary.json` and `reconciliation-report.json` without inventing business tolerances or reading real finance data.

## Acceptance Criteria

- [ ] Review `src.reconciliation_contract.build_reconciliation_contract` as the authoritative reconciliation entry.
- [ ] Review the implemented technical checks and their `rule_source` / `approval_status`.
- [ ] Confirm that legacy `src.reconcile` remains report-oriented and not authoritative.
- [ ] Confirm that cross-table business reconciliation remains `not_implemented` / `unverified`.
- [ ] Choose the next phase: second-city configuration validation or business-rule approval workflow.

## Scope

Human review of the Phase 2E reconciliation contract, synthetic fixtures, status propagation, and result contract extension.

## Out of Scope

Frontend, database, APIs, real finance files, production dry runs, remotes, UI, and second-city onboarding before explicit approval.

## Required Inputs

- Human review of Phase 2E outputs.
- Business owner decision on approved cross-table relationships and amount tolerances remains pending.

## Validation Plan

- Run `.\scripts\check.ps1`.
- Run `python -m unittest discover -s tests`.
- Run `python -m src.cli --help`.
- Inspect a balanced synthetic run for `reconciliation.status: passed`.
- Inspect mismatch, blocked, and artifact mismatch tests.

## Known Blockers

Business owner must still approve any real cross-table reconciliation rules, non-zero tolerances, negative/reversal/zero/duplicate policies, fee rates, whitelists, and crowd-cost bucket meanings.

## Resume Context

- Last key files: `src/reconciliation_contract.py`, `src/pipeline_service.py`, `schemas/run-result.schema.json`, `tests/test_reconciliation_contract.py`
- Last project phase: Phase 2E reconciliation contract
- Next action: Review Phase 2E reconciliation contract and choose second-city validation or business-rule approval workflow.
