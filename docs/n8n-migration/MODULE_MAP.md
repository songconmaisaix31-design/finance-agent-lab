# Module Map

## Current Pipeline Modules

| Target Stage | Existing Module/Function | Notes |
| --- | --- | --- |
| intake | `src.pipeline_service.plan_request`, `_validate_paths`, `_validate_required_inputs`, `_input_manifest` | Path safety, city namespace checks, required files. |
| normalize | `src.field_mapper.map_billing_sheet`, `src.normalizer.load_billing_rows` | Excel field mapping and row normalization remain in Python. |
| calculate | `src.income_calc.compute_income`, `src.fee_calc.compute_hq_fee`, `src.fee_calc.compute_team_delivery_cost`, `src.crowd_cost_contract.build_crowd_cost_result` | Existing Decimal-based calculations are reused unchanged. |
| reconcile | `src.reconcile.run_all_checks`, `src.reconciliation_contract.build_reconciliation_contract` | Technical reconciliation and result contract generation. |
| report | `src.report.generate_report` | Excel report generation remains in Python. |

## Adapter Modules Added

| Module | Responsibility |
| --- | --- |
| `src.pipeline_adapter` | Platform-neutral stage contract, run records, artifact lookup, CLI/API shared adapter. |
| `src.api` | FastAPI HTTP adapter for n8n. |
| `orchestration/pipeline.yaml` | External pipeline definition referencing the existing standard profile. |
| `quality-gates.yaml` | n8n-readable quality gate definitions. |

## Business Logic Boundary

The adapter does not implement income, headquarters fee, team delivery cost, crowd cost, reconciliation formulas, or report calculations. The reconcile stage delegates to `src.pipeline_service.run_request`, which calls the existing modules.
