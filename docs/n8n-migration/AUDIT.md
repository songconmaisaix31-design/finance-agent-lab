# n8n Migration Audit

Date: 2026-06-29

## Repository State

- Repository: `D:\AI-Workspace\Projects\finance-agent-lab`
- CodeGraph: not indexed; `.codegraph/` was not present.
- Git status before implementation: clean.
- Public entrypoint: `python -m src.cli`
- Legacy entrypoint: `python -m src.pipeline`, deprecated and protected from running accounting by default.
- Existing test command: `.\scripts\check.ps1`

## Baseline Tests

- Command: `.\scripts\check.ps1`
- Result: passed
- Count: 60 tests
- Duration: 29.942 seconds

## Existing Output Contract

Runs write to:

```text
<output-root>\runs\<run-id>\
```

Current formal artifacts:

- `result-summary.json`
- `run-manifest.json`
- `reconciliation-report.json`
- `unknown-types.json`
- `events.jsonl`
- `artifacts/*.xlsx`

The public JSON contracts already present before this migration were:

- `schemas/run-result.schema.json`
- `schemas/run-manifest.schema.json`

## Safety Findings

- No real finance data was found in the repository file listing.
- Existing `.gitignore` excludes local run output and environment files.
- Existing tests already enforce no real data in synthetic smoke paths.
- No business formula changes were made during this audit.
