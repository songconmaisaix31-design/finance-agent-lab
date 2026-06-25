# Current Task

## Objective

Safe public entrypoint and fixture smoke test.

## Why Now

The baseline audit found that the documented command points to a legacy script with absolute local finance file paths, while the richer city-specific pipeline has no fixture-level smoke test. The next development task should make the intended entrypoint safe before any business calculation changes.

## Acceptance Criteria

- [ ] The default documented command no longer depends on local absolute finance file paths.
- [ ] The authoritative pipeline entrypoint is explicit and fails clearly when required inputs are absent.
- [ ] A fixture-based smoke test creates only synthetic inputs in a temporary directory.
- [ ] The smoke test verifies generated outputs are confined to a temporary/run directory.
- [ ] The smoke test verifies input fixture hashes are unchanged after the run.
- [ ] The existing 15 baseline tests still pass through `scripts/check.ps1`.

## Scope

README usage, safe entrypoint selection, pipeline input/output boundary harness, and synthetic fixture smoke testing.

## Out of Scope

Income formulas, fee formulas, crowd-cost formulas, reconciliation policy changes, real finance files, existing `runs` cleanup, external APIs, notifications, remotes, and UI.

## Required Inputs

- Human confirmation of the authoritative pipeline entrypoint.
- Human confirmation of whether Phase 2C should keep one city/date or introduce minimal configurable input arguments.
- Synthetic fixture shape approved as sufficient for smoke testing.

## Validation Plan

- Run `.\scripts\check.ps1`.
- Run the new fixture smoke test without reading real finance files.
- Run `git diff --check`.
- Confirm no local machine-specific or real-data paths are required by the documented default command.

## Known Blockers

Phase 2C is not approved yet. Business owner must review `docs/BASELINE.md`, answer unknown rule questions, and approve or modify this recommended task.

## Resume Context

- Last files: docs/BASELINE.md, TASK.md, D:\AI-Workspace\Brain\10-Projects\Finance Agent Lab.md
- Last command: .\scripts\check.ps1
- Last result: 15 existing unit tests passed through scripts/check.ps1 during Phase 2B baseline verification
- Next action: 等待 Phase 2C 人工批准
