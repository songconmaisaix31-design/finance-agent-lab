# Finance Agent Lab

Six-city finance calculation platform.

The project uses one standard pipeline for city-level finance runs. City differences are expressed through explicit city profiles, business rule sets, and isolated storage namespaces. `guan` / 固安 is the first reference city.

Current city scope:

- `guan` / 固安
- `xianghe` / 香河
- `yicheng` / 驿城
- `yongcheng` / 永城
- `queshan` / 确山
- `biyang` / 泌阳

The other five cities are registered but blocked for formal runs until business rule sets are approved.

## Usage

Plan a run without executing accounting:

```powershell
python -m src.cli plan --city guan --input <input-directory> --output <output-directory>
```

Execute only with explicit confirmation:

```powershell
python -m src.cli run --city guan --input <input-directory> --output <output-directory> --execute
```

Inspect city governance:

```powershell
python -m src.cli cities list
python -m src.cli cities show --city guan
python -m src.cli cities validate
```

Initialize or validate external city data storage:

```powershell
python -m src.cli storage init --root D:\AI-Workspace\Finance-Data
python -m src.cli storage validate --root D:\AI-Workspace\Finance-Data
```

Outputs are written under:

```text
<output-directory>\runs\<run-id>\
```

For the governed six-city storage model, runs must stay under:

```text
<finance-data-root>\<city-id>\runs\<run-id>
```

The future frontend-facing result contract is versioned in:

- `schemas/run-result.schema.json`
- `schemas/run-manifest.schema.json`

The authoritative reconciliation result is available in:

- `<output-directory>\runs\<run-id>\result-summary.json` under `reconciliation`
- `<output-directory>\runs\<run-id>\reconciliation-report.json`

Reconciliation status meanings:

- `passed`: required technical checks passed.
- `failed`: a blocking technical check failed.
- `blocked`: an upstream required result is blocked or unavailable.
- `partial`: only incomplete or not applicable checks are available.

Current reconciliation scope:

- Technical invariants use exact Decimal comparison and zero tolerance.
- Implemented checks cover crowd bucket totals, crowd row accounting, artifact consistency, contract consistency, upstream blocked propagation, and input immutability.
- Cross-table business relationships are reported as `not_implemented` with `approval_status: unverified` until approved rules exist.

Current crowd-cost status:

- `guan` synthetic smoke runs include crowd-cost extraction from `crowd_cost.xlsx`.
- The smoke path covers field mapping, normalization, income, headquarters fee, team delivery fee, crowd-cost extraction, report generation, and result contracts.
- Existing crowd-cost bucket rules are implemented and tested with synthetic data, but business approval remains `unverified`.

Current six-city governance status:

- All cities reference `config/pipeline_profiles/standard-finance-pipeline.yaml`.
- City profiles live under `config/city_profiles/`.
- Business rule governance lives under `config/rules/` and `approval-pack/`.
- External city data namespaces live under a user-provided finance data root, not inside this Git repository.
- The generated catalog is `<finance-data-root>\catalog\cities.json` and contains safe city metadata only.

Safety notes:

- Do not use real finance files in tests.
- Do not commit input data, reports, local run output, credentials, or `.env` files.
- Unknown income, delivery, or crowd-cost types fail closed by default and produce a blocked result.
- The legacy `python -m src.pipeline` entrypoint is deprecated and does not run accounting by default.
- Do not copy `guan` rules into other cities without approval.
- Do not read or write across city namespaces.
