# Implementation Plan

## Completed Direction

1. Add platform-neutral contracts without changing finance formulas.
2. Reuse `config/pipeline_profiles/standard-finance-pipeline.yaml`.
3. Add a shared Python adapter for CLI and FastAPI.
4. Keep n8n as metadata-only orchestration.
5. Add Docker Compose and workflow templates with Manual Trigger only.
6. Test the adapter with synthetic fixtures.

## Rollback Boundary

All new functionality is isolated in:

- `src.pipeline_adapter`
- `src.api`
- `orchestration/`
- new schemas
- `infra/n8n/`
- `workflows/`
- `docs/n8n-migration/`
- new tests

Existing business modules are not rewritten.
