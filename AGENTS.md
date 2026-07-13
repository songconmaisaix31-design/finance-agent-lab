# Finance Agent Lab Agents

Purpose: maintain the multi-city finance calculation pipeline described in `README.md`.

Read first: `AGENTS.md`, then `TASK.md`; use `README.md` and tests only when needed.

Safety:
- Do not convert money amounts to `float`; use decimal-safe handling.
- Do not invent missing business rules.
- Do not silently ignore unknown income, expense, or crowd-cost types.
- Do not add real business data, bills, reports, `.env`, or credentials to Git.
- Do not overwrite original inputs unless a task explicitly approves it.
- Keep business rules configurable instead of scattering hard-coded rules.
- Use `python -m src.cli` as the public entrypoint; legacy `src.pipeline` must not run accounting by default.
- City differences must be explicit city profiles/config, not guessed from input files.
- Public result JSON must follow `schemas/` and must not expose absolute input paths.
- Unknown income, delivery, or crowd-cost types fail closed by default.
- Reconciliation must report differences only; it must not auto-correct or rebalance business data.
- Do not add amount tolerances unless an approved rule source explicitly provides them.
- Upstream `blocked` results must not be treated as zero in downstream reconciliation.
- Do not create duplicated city-specific pipeline implementations.
- Do not read from or write to another city's data namespace.
- Do not treat one city's business rules as another city's default rules.

Start:
- Run `.\scripts\check.ps1` from the project root.

Done means:
- Relevant tests pass or failures are clearly reported.
- Git status is understood.
- Update `docs/DECISIONS.md` for real decisions and `docs/LESSONS.md` only for verified reusable lessons.
