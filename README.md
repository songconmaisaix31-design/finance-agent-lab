# Finance Agent Lab

Multi-city finance calculation platform.

The project uses one standard pipeline for city-level finance runs. City differences are expressed through explicit city profiles and configuration. `guan` / 固安 is the first reference city.

## Usage

Plan a run without executing accounting:

```powershell
python -m src.cli plan --city guan --input <input-directory> --output <output-directory>
```

Execute only with explicit confirmation:

```powershell
python -m src.cli run --city guan --input <input-directory> --output <output-directory> --execute
```

Outputs are written under:

```text
<output-directory>\runs\<run-id>\
```

The future frontend-facing result contract is versioned in:

- `schemas/run-result.schema.json`
- `schemas/run-manifest.schema.json`

Safety notes:

- Do not use real finance files in tests.
- Do not commit input data, reports, local run output, credentials, or `.env` files.
- Unknown income or delivery types fail closed by default and produce a blocked result.
- The legacy `python -m src.pipeline` entrypoint is deprecated and does not run accounting by default.
