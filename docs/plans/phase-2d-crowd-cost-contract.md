# Phase 2D Crowd Cost Contract Plan

## Scope

- Characterize current crowd-cost extraction behavior with synthetic Excel inputs.
- Add a stable internal crowd-cost result model and safe error model.
- Extend the `guan` smoke path so public pipeline runs include crowd-cost extraction.
- Add optional `costs.crowd` to `result-summary.json`.
- Update docs and Brain status after verification.

## Current Evidence

- Entry extractor: `src/crowd_cost.py::extract_crowd_cost_buckets`.
- Fast row loader: `src/crowd_cost_fast.py::load_crowd_cost_rows_fast`.
- Current bucket IDs come from existing code/config: `catering_normal`, `catering_group`, `retail_normal`, `retail_group`.
- Current public pipeline service uses `_zero_crowd_buckets`, so Phase 2C smoke did not exercise actual crowd-cost extraction.

## Files Planned

- `src/crowd_cost.py`
- `src/crowd_cost_fast.py`
- `src/crowd_cost_contract.py`
- `src/pipeline_service.py`
- `schemas/run-result.schema.json`
- `tests/test_crowd_cost_contract.py`
- `tests/test_phase2c_safe_entrypoint.py`
- `README.md`, `AGENTS.md`, `TASK.md`, `docs/BASELINE.md`, `docs/DECISIONS.md`

## TDD Order

1. Characterize happy path for four existing buckets using synthetic workbook data.
2. Characterize invalid, empty, missing sheet/header, and unknown classification behavior.
3. Add result model and stable crowd error codes.
4. Integrate crowd-cost result into `pipeline_service` and `result-summary.json`.
5. Extend smoke tests and run the complete suite.

## Risks

- Existing loader silently converts some invalid numeric values to zero. If exposed, this must be treated as a safety fix, not a business-rule change.
- Existing bucket rules are implemented but business approval is still unverified.
- Cross-table reconciliation remains incomplete and must stay out of scope.

## Acceptance Criteria

- Every existing bucket has synthetic test coverage.
- Unknown or unclassifiable rows are reported and fail closed at the application boundary.
- Decimal amounts are preserved and serialized as strings.
- Crowd-cost input SHA-256 is unchanged after runs.
- `result-summary.json` contains schema-valid `costs.crowd`.
- Existing Phase 2C tests continue to pass.

## Rollback

Revert the Phase 2D project commits and the Brain status commit. No remotes, real finance files, desktop source files, or external systems are touched.
