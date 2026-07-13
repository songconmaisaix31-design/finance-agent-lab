# Project Memory

## Long-Term Context

- `finance-agent-lab` is a local-first multi-city finance calculation and reconciliation project.
- Real finance inputs, bills, reports, databases, runtime exports, absolute input paths, `.env` files, and credentials are not publishable source artifacts.
- Business rules remain approval-gated. Unknown rule types fail closed and must not be guessed or silently normalized.

## Decisions

- Use `python -m src.cli` as the public entrypoint; `src.pipeline` remains legacy and must not run accounting by default.
- Keep city data namespaces isolated and keep city-specific rules in explicit configuration.
- GitHub publication must use a non-default branch and Draft PR. New remote repositories default to private visibility.
- Publication validation must run `scripts/check.ps1` and the focused commands documented in `TASK.md` when the local environment supports them.
- 2026-07-13: The deprecated `src.pipeline` compatibility entrypoint contains no accounting implementation or local input paths. It fails closed and points users to `python -m src.cli`.

## Security Notes

- Never store secret values or real business data in this file.
- Git checks may inspect filenames and metadata, but must not print the contents of credential-like or real finance files.
