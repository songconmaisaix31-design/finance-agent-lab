# Stage Dependency Map

## Dependencies

| Stage | Requires | Allows Status |
| --- | --- | --- |
| intake | run request | pending |
| normalize | intake | success |
| calculate | normalize | success |
| reconcile | calculate | success, warning |
| report | reconcile and quality gate | success, warning |

Illegal ordering returns `STAGE_DEPENDENCY_NOT_SATISFIED`.

## Artifact Flow

```text
input Excel files
  -> intake
  -> input-manifest.json + run-context.json
  -> normalize
  -> normalized-data/normalized.sqlite + normalization-manifest.json + schema-report.json
  -> calculate
  -> calculation-result.json + calculation-manifest.json
  -> reconcile
  -> stage-reconciliation-report.json + quality-gate-result.json
  -> report
  -> result-summary.json + run-manifest.json + reconciliation-report.json + artifact-manifest.json + artifacts/*.xlsx
```

## Formula Ownership

No formulas were copied into n8n or the adapter. Stage services call existing formula modules directly.
