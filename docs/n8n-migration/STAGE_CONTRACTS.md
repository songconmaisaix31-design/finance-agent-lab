# Stage Contracts

## Common Artifact Fields

Every declared intermediate artifact includes:

- `schema_version`
- `producer_stage`
- `path`
- `sha256`
- `size_bytes`

## Intake

Outputs:

- `input-manifest.json`
- `run-context.json`

The manifest includes relative input paths, file sizes, SHA-256 hashes, pipeline profile id/version, config hash, city namespace, and contract version.

## Normalize

Consumes:

- `input-manifest.json`
- `run-context.json`

Outputs:

- `normalized-data/normalized.sqlite`
- `normalization-manifest.json`
- `schema-report.json`

SQLite is used because it is available in the standard library. Money fields are stored as exact strings, not floats.

## Calculate

Consumes:

- normalized SQLite
- `normalization-manifest.json`

Outputs:

- `calculation-result.json`
- `calculation-manifest.json`

The stage calls the existing income, fee, team delivery cost, bill crowd count, and crowd cost modules. It does not call reconciliation or report generation.

## Reconcile

Consumes:

- `calculation-result.json`
- normalized artifact metadata

Outputs:

- `stage-reconciliation-report.json`
- `quality-gate-result.json`

The adapter no longer calls full `pipeline_service.run_request()` from reconcile.

## Report

Consumes:

- input manifest
- normalization manifest
- calculation result
- reconciliation quality gate
- run state

Outputs:

- `artifacts/*.xlsx`
- `artifact-manifest.json`
- `result-summary.json`
- `run-manifest.json`
- `reconciliation-report.json`
- `unknown-types.json`

Only report stage generates the final Excel workbook.
