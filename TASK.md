# Current Task

## Objective

Review the six-city configuration, storage isolation, and business-rule gaps; confirm whether each city shares business parameters.

## Why Now

Phase 2F established six City Profiles, one Standard Pipeline Profile, isolated city data namespaces, city catalog generation, and rule-governance approval drafts. The platform can enumerate all six cities without copying `guan` business rules into the other five cities.

## Acceptance Criteria

- [ ] Review six City Profiles under `config/city_profiles/`.
- [ ] Review `config/pipeline_profiles/standard-finance-pipeline.yaml`.
- [ ] Review `config/rules/` and `approval-pack/`.
- [ ] Confirm storage isolation under the external finance data root.
- [ ] Confirm that non-`guan` formal runs remain blocked until rules are approved.
- [ ] Decide whether six-city fee rates, whitelists, field aliases, crowd-cost mappings, anomaly policies, cross-table rules, and tolerances are shared or city-specific.

## Scope

Human review of six-city architecture, data isolation, and business-rule governance.

## Out of Scope

Frontend, database, APIs, real finance files, production dry runs, remotes, UI, and second-city calculation before explicit approval.

## Required Inputs

- Business owner decision on shared vs city-specific parameters.
- Human approval of which city becomes the second synthetic validation city.

## Validation Plan

- Run `.\scripts\check.ps1`.
- Run `python -m unittest discover -s tests`.
- Run `python -m src.cli --help`.
- Run `python -m src.cli cities list`.
- Run `python -m src.cli cities validate`.
- Run `python -m src.cli storage init --root D:\AI-Workspace\Finance-Data`.
- Run `python -m src.cli storage validate --root D:\AI-Workspace\Finance-Data`.

## Known Blockers

The other five cities are intentionally blocked for formal runs because approved rule sets are missing. `guan` remains unverified and not production ready.

## Resume Context

- Last key files: `src/city_registry.py`, `src/storage.py`, `src/cli.py`, `config/city_profiles/`, `config/pipeline_profiles/`, `config/rules/`, `approval-pack/`
- Last project phase: Phase 2F six-city governance
- Next action: Review whether six-city rules are shared and approve city configuration completion.
