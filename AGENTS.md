# Finance Agent Lab Agents

Purpose: maintain the income and expense accounting pipeline described in `README.md`.

Read first: `AGENTS.md`, then `TASK.md`; use `README.md` and tests only when needed.

Safety:
- Do not convert money amounts to `float`; use decimal-safe handling.
- Do not invent missing business rules.
- Do not silently ignore unknown income or expense types.
- Do not add real business data, bills, reports, `.env`, or credentials to Git.
- Do not overwrite original inputs unless a task explicitly approves it.
- Keep business rules configurable instead of scattering hard-coded rules.

Start:
- Run `.\scripts\check.ps1` from the project root.

Done means:
- Relevant tests pass or failures are clearly reported.
- Git status is understood.
- Update `docs/DECISIONS.md` for real decisions and `docs/LESSONS.md` only for verified reusable lessons.
