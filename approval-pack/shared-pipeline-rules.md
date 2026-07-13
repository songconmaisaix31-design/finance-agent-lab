# Shared Pipeline and Technical Rules

Status: technical draft

Six cities share `standard-finance-pipeline` version `1`.

Approved technical invariants in the current project:

- Explicit city id is required for plan/run.
- City data namespaces must be isolated.
- Result contracts must not expose absolute input paths.
- Reconciliation reports differences and does not auto-correct upstream data.
- Decimal technical checks use exact comparison unless an approved rule source states otherwise.

Business parameters are not approved by this document.
