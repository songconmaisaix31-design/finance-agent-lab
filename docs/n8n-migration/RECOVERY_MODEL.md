# Recovery Model

## Truth Source

Run-directory orchestration state is the source of truth:

```text
<output_root>/.orchestration/<run_id>/
  run.json
  stages/
    intake.json
    normalize.json
    calculate.json
    reconcile.json
    report.json
  locks/
```

`.pipeline-state` is a rebuildable index that points at `run.json`.

## Atomic Writes

JSON and text writes use:

1. same-directory temporary file
2. flush
3. fsync
4. atomic replace

## Rebuild

Run:

```powershell
python -m src.cli rebuild-run-index
```

The command scans `.orchestration/*/run.json`, rebuilds `.pipeline-state`, and reports skipped corrupt files.

## Idempotency

- Terminal stage states are returned as-is.
- Completed stages are not recalculated.
- Input/config drift must use a new run id; force overwrite is not implemented.

## Concurrency

Stage execution creates `<stage>.lock` under the run orchestration directory.

- First caller executes.
- Concurrent caller receives `STAGE_ALREADY_RUNNING`.
- The response includes `attempt_id`, `started_at`, `stage`, and `retry_after_seconds` in error details.

## Current Limit

Stale running detection is represented by lease fields in stage state and lock metadata, but automated stale interruption/resume policy remains a follow-up hardening item.
