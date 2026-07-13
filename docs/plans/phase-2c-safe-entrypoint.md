# Phase 2C Safe Entrypoint Plan

## Scope

- Add a safe public CLI with `plan` and `run` commands.
- Require explicit `--city`, `--input`, `--output`, and `--execute` for formal runs.
- Load `guan` through an explicit city registry and city profile.
- Run a synthetic fixture through real field mapping, normalization, income, fee, report, manifest, and result-contract boundaries.
- Produce versioned `run-manifest.json`, `result-summary.json`, `unknown-types.json`, `events.jsonl`, and report artifacts.

## Non-Goals

- No frontend, API service, database, remote integration, or notification work.
- No business-rule value changes.
- No new crowd-cost or reconciliation algorithms.
- No deletion of legacy pipeline files.
- No real finance data reads.

## Files To Modify

- `src/cli.py`
- `src/city_registry.py`
- `src/pipeline_service.py`
- `src/result_contract.py`
- `src/pipeline.py`
- `config/cities/guan.yaml`
- `schemas/run-result.schema.json`
- `schemas/run-manifest.schema.json`
- `tests/`
- `README.md`, `AGENTS.md`, `TASK.md`, `docs/DECISIONS.md`, `docs/BASELINE.md`
- Brain project card and optional Brain decision note

## Architecture Boundary

CLI parses arguments and returns stable exit codes. The city registry validates known cities and exposes configuration metadata. The standard pipeline service owns path safety, run directory creation, input immutability, status control, and artifact writing. Existing accounting modules remain responsible for normalization, income, fees, reconciliation summaries, and report generation.

## TDD Order

1. Add CLI and path safety tests.
2. Add city registry and configuration metadata tests.
3. Add legacy entrypoint safety tests.
4. Add result schema and synthetic smoke tests.
5. Implement the smallest production code to pass those tests.
6. Refactor only where it clarifies the new boundary.

## Risks

- Existing `src/pipeline.py` contains absolute local paths and must be made safe without deleting historical code.
- Existing full `pipeline_guan.py` expects local fixed filenames; Phase 2C should wrap reusable module boundaries rather than broaden it into a full multi-city framework.
- Crowd-cost and reconciliation paths are incomplete; the result contract must disclose limited capability instead of implying production readiness.

## Acceptance Criteria

- `python -m src.cli --help` has no business I/O.
- `plan` validates request and creates no run artifacts.
- `run --execute` creates an isolated run directory under `<output>\runs\<run-id>`.
- Synthetic `guan` smoke input produces contract files and a report artifact.
- Unknown income or delivery types default to `blocked`.
- Inputs are unchanged before and after execution.
- Result JSON conforms to schema and contains no local absolute input path.
- Existing 15 tests continue to pass.

## Rollback

Revert the Phase 2C project commit and the Brain status commit. No external systems, remotes, databases, or desktop source files are touched.
