# Phase 2E Reconciliation Contract Plan

## Objective

Build a single authoritative technical reconciliation contract for the safe public pipeline without inventing business tolerances or changing existing city rules.

## Baseline

- Project baseline: `5fcf56f` or successor.
- Brain baseline: `1b206ac` or successor.
- Public entrypoint: `python -m src.cli plan/run`.
- Reference city: `guan` / 固安.
- Real finance files remain out of scope.

## Audit Findings

| Area | Current status | Trust | Evidence |
| --- | --- | --- | --- |
| Public run summary and manifest | implemented | verified_by_test | `src/pipeline_service.py`, schemas, smoke tests |
| Input SHA before/after check | implemented | verified_by_test | `src/pipeline_service.py`, Phase 2C smoke tests |
| Crowd-cost result model | implemented | verified_by_test | `src/crowd_cost_contract.py`, Phase 2D tests |
| Income arithmetic checks in legacy reconciler | partial | implemented_unverified | `src/reconcile.py` uses configured tolerance |
| Team-cost arithmetic checks in legacy reconciler | partial | implemented_unverified | `src/reconcile.py` uses configured tolerance |
| Bill-vs-cost-table helper | placeholder | unknown | `src/reconcile.py` contains an empty loop body |
| Cross-table business reconciliation | missing | unknown | no approved business rule source is documented |
| Legacy reconciliation module | unsafe | unknown | `src/reconciliation.py` uses tolerance/rounding behavior outside the public contract |

## Authoritative Entry

`src.reconciliation_contract.build_reconciliation_contract` is the authoritative Phase 2E reconciliation entry for public result status. Existing report-oriented helpers remain legacy/report-only and do not decide the public run contract.

## Implemented Check Scope

Technical checks only:

- Crowd bucket total exact Decimal identity.
- Crowd row accounting identity.
- Safe artifact list consistency.
- Run id, city id, status, config hash, and schema version consistency.
- Crowd upstream blocked propagation.
- Input manifest immutability.

Business checks:

- Cross-table business relationships are explicitly `not_implemented` with `approval_status: unverified` until an approved rule source exists.

## Status Rules

- Any failed blocking check makes reconciliation `failed`.
- Any blocked check makes reconciliation `blocked`.
- If all necessary technical checks pass, reconciliation is `passed`.
- Not implemented cross-table business rules remain visible and do not become `approved`.
- A failed or blocked reconciliation prevents a `success` run status.

## Fixtures

- Balanced synthetic run: technical reconciliation passes, cross-table business rule remains not implemented.
- Arithmetic mismatch fixture: in-memory contract fixture mutates the crowd total and must fail with an exact Decimal difference.
- Blocked upstream fixture: unknown crowd rows block reconciliation and run status.
- Artifact mismatch fixture: missing or undeclared artifact fails the contract.

## Out of Scope

- Real finance input inspection.
- Business tolerance invention.
- Auto-correction or auto-balancing.
- Frontend, API, database, second city, remotes, or production dry runs.
