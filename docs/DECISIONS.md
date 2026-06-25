# Decisions

- The project copy under `D:\AI-Workspace\Projects\finance-agent-lab` is the future development entry.
- The original desktop project remains in place for now.
- Real business data, generated reports, credentials, and local outputs must not enter Git or Brain.
- The project harness uses progressive reading: start with `AGENTS.md` and `TASK.md`.
- The product direction is a multi-city finance calculation platform with one standard pipeline.
- `guan` / 固安 is the first reference city for end-to-end validation.
- The public CLI and city implementation are decoupled: `python -m src.cli` is the public entrypoint, while city behavior is loaded through explicit profiles/config.
- City differences must be expressed through explicit configuration, not guessed from file names or directory contents.
- Future frontend consumption depends on versioned result contracts under `schemas/`.
- Unknown income and delivery types fail closed by default.
- Current fee rates, whitelists, and field rules retain `rule_approval_status: unverified` until business approval is recorded.
- Crowd cost enters the public pipeline through a stable result model instead of ad hoc JSON.
- Crowd cost bucket IDs must remain stable unless a schema and migration review approves a change.
- Unknown crowd-cost categories fail closed by default.
- Existing crowd-cost bucket rules retain `approval_status: unverified` until business approval is recorded.
