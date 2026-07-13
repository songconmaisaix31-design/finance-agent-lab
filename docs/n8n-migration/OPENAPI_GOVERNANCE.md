# OpenAPI Governance

## Canonical Snapshot

The committed snapshot is:

```text
docs/n8n-migration/openapi.json
```

Regenerate it with:

```powershell
python -m scripts.generate_openapi
```

## Test Gate

`tests/test_openapi_snapshot.py` verifies:

- `app.openapi()` exactly matches the committed snapshot.
- all successful responses have non-empty schemas.
- documented response models exist.
- stage path parameter uses `PipelineStage` enum.

## API Versioning

The canonical API path is `/api/v1/...`.

Legacy paths remain present and are marked deprecated in OpenAPI for compatibility with earlier local workflow exports.
