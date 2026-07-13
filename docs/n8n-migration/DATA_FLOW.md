# Data Flow

## Principle

n8n carries orchestration metadata only. Detailed Excel rows stay inside the Python process and are read from local mounted paths.

## Metadata Passed Through n8n

- `run_id`
- `city_id`
- `input_path`
- `output_root`
- stage status
- small metrics
- artifact paths
- error codes and safe messages

## Data Kept Out Of n8n

- Raw billing detail rows
- Normalized detail rows
- 290k-row JSON payloads
- Real credentials, cookies, tokens, or `.env`
- Financial formulas

## HTTP Boundary

n8n calls the FastAPI adapter:

- `GET /health`
- `POST /runs`
- `POST /runs/{run_id}/stages/{stage}`
- `GET /runs/{run_id}`
- `GET /runs/{run_id}/artifacts`

The adapter delegates to the existing Python service layer.
