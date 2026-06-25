# Finance Agent Lab Agents

Purpose: maintain the multi-city finance calculation pipeline described in `README.md`.

Read first: `AGENTS.md`, then `TASK.md`; use `README.md` and tests only when needed.

Safety:
- Do not convert money amounts to `float`; use decimal-safe handling.
- Do not invent missing business rules.
- Do not silently ignore unknown income or expense types.
- Do not add real business data, bills, reports, `.env`, or credentials to Git.
- Do not overwrite original inputs unless a task explicitly approves it.
- Keep business rules configurable instead of scattering hard-coded rules.
- Use `python -m src.cli` as the public entrypoint; legacy `src.pipeline` must not run accounting by default.
- City differences must be explicit city profiles/config, not guessed from input files.
- Public result JSON must follow `schemas/` and must not expose absolute input paths.
- Unknown income or delivery types fail closed by default.

Start:
- Run `.\scripts\check.ps1` from the project root.

Done means:
- Relevant tests pass or failures are clearly reported.
- Git status is understood.
- Update `docs/DECISIONS.md` for real decisions and `docs/LESSONS.md` only for verified reusable lessons.
