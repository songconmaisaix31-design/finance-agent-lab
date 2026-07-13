from __future__ import annotations

import json
import os
import secrets
import time
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .pipeline_service import (
    PipelineError,
    RunRequest,
    create_stage_context,
    run_calculate_stage,
    run_intake_stage,
    run_normalize_stage,
    run_reconcile_stage,
    run_report_stage,
)
from .result_contract import atomic_write_json, json_safe, utc_now_iso


PIPELINE_STATUSES = ("pending", "running", "success", "warning", "failed", "rejected", "skipped")
PIPELINE_STAGES = ("intake", "normalize", "calculate", "reconcile", "report")
TERMINAL_SUCCESS = {"success", "warning"}
TERMINAL_STATUSES = {"success", "warning", "failed", "rejected", "skipped"}
REPO_ROOT = Path(__file__).resolve().parents[1]


class StageContractError(PipelineError):
    exit_code = 9
    error_code = "STAGE_CONTRACT_INVALID"


class StageAlreadyRunningError(StageContractError):
    error_code = "STAGE_ALREADY_RUNNING"

    def __init__(self, stage: str, attempt_id: str, started_at: str):
        super().__init__(f"Stage already running: {stage}")
        self.details = {
            "stage": stage,
            "attempt_id": attempt_id,
            "started_at": started_at,
            "retry_after_seconds": 30,
        }


@dataclass(frozen=True)
class AdapterRunRequest:
    city_id: str
    input_path: Path
    output_root: Path
    mode: str = "execute"
    unknown_type_policy: str = "error"
    run_id: str | None = None


def generate_run_id(city_id: str) -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"{city_id}-{stamp}-{secrets.token_hex(4)}"


def create_run(request: AdapterRunRequest) -> dict[str, Any]:
    run_id = request.run_id or generate_run_id(request.city_id)
    _validate_allowed_roots(request.input_path, request.output_root)
    existing = _find_record_path(run_id, Path(request.output_root))
    if existing:
        record = json.loads(existing.read_text(encoding="utf-8"))
        _ensure_same_request(record, request)
        _write_api_index(record)
        return public_run(record)
    record = {
        "schema_version": "1.0",
        "run_id": run_id,
        "city_id": request.city_id,
        "input_path": str(Path(request.input_path).expanduser().resolve(strict=False)),
        "output_root": str(Path(request.output_root).expanduser().resolve(strict=False)),
        "mode": request.mode,
        "unknown_type_policy": request.unknown_type_policy,
        "status": "pending",
        "current_stage": None,
        "created_at": utc_now_iso(),
        "updated_at": utc_now_iso(),
        "stages": {stage: _stage_seed(run_id, stage) for stage in PIPELINE_STAGES},
        "artifacts": [],
    }
    _write_record(record)
    _write_stage_records(record)
    _write_api_index(record)
    return public_run(record)


def execute_stage(run_id: str, stage: str) -> dict[str, Any]:
    if stage not in PIPELINE_STAGES:
        raise StageContractError(f"Unknown pipeline stage: {stage}")
    record = load_run(run_id)
    existing = record["stages"].get(stage)
    if existing and existing.get("status") in TERMINAL_STATUSES:
        return existing

    with _stage_lock(record, stage):
        record = load_run(run_id)
        existing = record["stages"].get(stage)
        if existing and existing.get("status") in TERMINAL_STATUSES:
            return existing

        started = utc_now_iso()
        attempt_id = secrets.token_hex(8)
        start_perf = time.perf_counter()
        running = {
            **record["stages"].get(stage, _stage_seed(run_id, stage)),
            "status": "running",
            "attempt_id": attempt_id,
            "attempt": int(record["stages"].get(stage, {}).get("attempt", 0)) + 1,
            "started_at": started,
            "finished_at": None,
            "ended_at": None,
            "lease_heartbeat_at": started,
            "duration_ms": 0,
            "error": None,
        }
        record["status"] = "running"
        record["current_stage"] = stage
        record["stages"][stage] = running
        _write_record(record)
        _write_stage_record(record, stage, running)

        try:
            _ensure_prior_stages(record, stage)
            service_result = _call_stage_service(record, stage)
            ended = utc_now_iso()
            result = _stage_result(
                run_id=run_id,
                stage=stage,
                status=service_result.status,
                metrics=service_result.metrics,
                artifacts=service_result.output_artifacts,
                message=service_result.message,
                result=service_result.result,
                started_at=started,
                ended_at=ended,
                duration_ms=int((time.perf_counter() - start_perf) * 1000),
                attempt_id=attempt_id,
                attempt=running["attempt"],
            )
        except Exception as exc:
            ended = utc_now_iso()
            status = "rejected" if isinstance(exc, StageContractError) else "failed"
            error_code = getattr(exc, "error_code", "STAGE_FAILED")
            result = _stage_result(
                run_id=run_id,
                stage=stage,
                status=status,
                started_at=started,
                ended_at=ended,
                duration_ms=int((time.perf_counter() - start_perf) * 1000),
                error={"code": error_code, "message": _safe_stage_error(exc)},
                attempt_id=attempt_id,
                attempt=running["attempt"],
            )

        record["status"] = result["status"]
        record["current_stage"] = stage
        record["stages"][stage] = result
        record["updated_at"] = result["ended_at"]
        if stage == "report":
            record["artifacts"] = result.get("artifacts", record.get("artifacts", []))
        _write_record(record)
        _write_stage_record(record, stage, result)
        _write_api_index(record)
        return result


def run_all_stages(request: AdapterRunRequest) -> dict[str, Any]:
    run = create_run(request)
    final = None
    for stage in PIPELINE_STAGES:
        final = execute_stage(run["run_id"], stage)
        if final["status"] not in TERMINAL_SUCCESS:
            break
    return {"run": get_run(run["run_id"]), "result": final}


def get_run(run_id: str) -> dict[str, Any]:
    return public_run(load_run(run_id))


def get_artifacts(run_id: str) -> dict[str, Any]:
    record = load_run(run_id)
    return {
        "schema_version": "1.0",
        "run_id": run_id,
        "artifacts": record.get("artifacts", []),
        "manifest_path": _manifest_path(record),
    }


def rebuild_run_index() -> dict[str, Any]:
    rebuilt = []
    skipped = []
    for path in _scan_record_paths():
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
            _write_api_index(record)
            rebuilt.append({"run_id": record["run_id"], "record_path": str(path)})
        except Exception as exc:
            skipped.append({"record_path": str(path), "error": str(exc)})
    return {"rebuilt": rebuilt, "skipped": skipped, "rebuilt_count": len(rebuilt), "skipped_count": len(skipped)}


def load_run(run_id: str) -> dict[str, Any]:
    index = _api_index_path(run_id)
    if index.exists():
        pointer = json.loads(index.read_text(encoding="utf-8"))
        path = Path(pointer["record_path"])
    else:
        path = _find_record_path(run_id)
        if path is None:
            raise StageContractError(f"Run not found: {run_id}")
    if not path.exists():
        raise StageContractError(f"Run record missing: {run_id}")
    record = json.loads(path.read_text(encoding="utf-8"))
    _write_api_index(record)
    return record


def public_run(record: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": record["schema_version"],
        "run_id": record["run_id"],
        "city_id": record["city_id"],
        "status": record["status"],
        "current_stage": record.get("current_stage"),
        "mode": record["mode"],
        "created_at": record["created_at"],
        "updated_at": record["updated_at"],
        "stages": record["stages"],
        "run_dir": _run_dir(record),
        "summary_path": _summary_path(record),
        "manifest_path": _manifest_path(record),
        "artifacts": record.get("artifacts", []),
    }


def stage_summary_from_result(result) -> dict[str, Any]:
    return {
        "status": _map_pipeline_status(result.status),
        "exit_code": result.exit_code,
        "run_id": result.run_id,
        "run_dir": str(result.run_dir) if result.run_dir else None,
        "summary_path": str(result.summary_path) if result.summary_path else None,
        "manifest_path": str(result.manifest_path) if result.manifest_path else None,
        "message": result.message,
    }


def _call_stage_service(record: dict[str, Any], stage: str):
    context = create_stage_context(_service_request(record, mode=record["mode"], run_id=record["run_id"]), run_id=record["run_id"])
    if stage == "intake":
        return run_intake_stage(context)
    if stage == "normalize":
        return run_normalize_stage(context)
    if stage == "calculate":
        return run_calculate_stage(context)
    if stage == "reconcile":
        return run_reconcile_stage(context)
    if stage == "report":
        return run_report_stage(context)
    raise StageContractError(f"Unknown pipeline stage: {stage}")


def _service_request(record: dict[str, Any], mode: str, run_id: str | None = None) -> RunRequest:
    return RunRequest(
        city_id=record["city_id"],
        input_path=Path(record["input_path"]),
        output_root=Path(record["output_root"]),
        mode=mode,
        unknown_type_policy=record["unknown_type_policy"],
        requested_at=record["created_at"],
        run_id=run_id,
    )


def _ensure_prior_stages(record: dict[str, Any], stage: str):
    index = PIPELINE_STAGES.index(stage)
    for prior in PIPELINE_STAGES[:index]:
        status = record["stages"].get(prior, {}).get("status")
        if status not in TERMINAL_SUCCESS:
            exc = StageContractError(f"Stage {stage} requires {prior} to finish first")
            exc.error_code = "STAGE_DEPENDENCY_NOT_SATISFIED"
            raise exc


def _ensure_same_request(record: dict[str, Any], request: AdapterRunRequest):
    requested = {
        "city_id": request.city_id,
        "input_path": str(Path(request.input_path).expanduser().resolve(strict=False)),
        "output_root": str(Path(request.output_root).expanduser().resolve(strict=False)),
        "mode": request.mode,
        "unknown_type_policy": request.unknown_type_policy,
    }
    existing = {key: record.get(key) for key in requested}
    if existing != requested:
        raise StageContractError(f"Run id already exists with a different request: {record['run_id']}")


def _validate_allowed_roots(input_path: Path, output_root: Path):
    raw = os.environ.get("FINANCE_PIPELINE_ALLOW_ROOTS")
    if not raw:
        return
    allowed = [Path(item).expanduser().resolve(strict=False) for item in raw.split(os.pathsep) if item.strip()]
    if not allowed:
        return
    paths = [Path(input_path).expanduser().resolve(strict=False), Path(output_root).expanduser().resolve(strict=False)]
    for path in paths:
        if not any(_is_relative_to(path, root) or path == root for root in allowed):
            raise StageContractError(f"Path outside configured allowlist: {path}")


def _is_relative_to(child: Path, parent: Path) -> bool:
    try:
        child.relative_to(parent)
        return True
    except ValueError:
        return False


def _stage_seed(run_id: str, stage: str) -> dict[str, Any]:
    return _stage_result(run_id=run_id, stage=stage, status="pending")


def _stage_result(
    *,
    run_id: str,
    stage: str,
    status: str,
    metrics: dict[str, str] | None = None,
    artifacts: list[dict[str, Any]] | None = None,
    message: str | None = None,
    result: dict[str, Any] | None = None,
    started_at: str | None = None,
    ended_at: str | None = None,
    duration_ms: int = 0,
    error: dict[str, str] | None = None,
    attempt_id: str | None = None,
    attempt: int = 0,
) -> dict[str, Any]:
    if status not in PIPELINE_STATUSES:
        raise StageContractError(f"Invalid stage status: {status}")
    data = {
        "schema_version": "1.0",
        "run_id": run_id,
        "stage": stage,
        "status": status,
        "message": message,
        "metrics": metrics or {},
        "artifacts": artifacts or [],
        "started_at": started_at,
        "ended_at": ended_at,
        "finished_at": ended_at,
        "duration_ms": duration_ms,
        "attempt_id": attempt_id,
        "attempt": attempt,
        "contract_version": "1",
        "error": error,
    }
    if result is not None:
        data["result"] = result
    return json_safe(data)


@contextmanager
def _stage_lock(record: dict[str, Any], stage: str):
    lock_path = _orchestration_run_dir(record) / "locks" / f"{stage}.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    started_at = utc_now_iso()
    attempt_id = secrets.token_hex(8)
    try:
        fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError as exc:
        details = _load_json(lock_path)
        raise StageAlreadyRunningError(
            stage,
            str(details.get("attempt_id", "unknown")),
            str(details.get("started_at", "unknown")),
        ) from exc
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump({"stage": stage, "attempt_id": attempt_id, "started_at": started_at}, handle)
            handle.flush()
            os.fsync(handle.fileno())
        yield
    finally:
        try:
            lock_path.unlink()
        except FileNotFoundError:
            pass


def _safe_stage_error(exc: Exception) -> str:
    message = str(exc)
    cwd = str(REPO_ROOT)
    return message.replace(cwd, "<repo>")


def _map_pipeline_status(status: str | None) -> str:
    if status == "success":
        return "success"
    if status in {"blocked", "rejected"}:
        return "rejected"
    if status in {"warning", "partial"}:
        return "warning"
    if status in {"planned", "pending"}:
        return "pending"
    return "failed"


def _artifact_manifest(record: dict[str, Any], summary: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "run_id": record["run_id"],
        "artifacts": [
            {
                **artifact,
                "absolute_path": str(Path(record["output_root"]) / "runs" / record["run_id"] / artifact["path"]),
            }
            for artifact in summary.get("artifacts", [])
        ],
    }


def _load_json(path: Path | None) -> dict[str, Any]:
    if not path or not Path(path).exists():
        return {}
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _write_record(record: dict[str, Any]):
    path = _record_path(record)
    atomic_write_json(path, record)


def _write_stage_records(record: dict[str, Any]):
    for stage, result in record.get("stages", {}).items():
        _write_stage_record(record, stage, result)


def _write_stage_record(record: dict[str, Any], stage: str, result: dict[str, Any]):
    atomic_write_json(_stage_record_path(record, stage), result)


def _write_api_index(record: dict[str, Any]):
    atomic_write_json(_api_index_path(record["run_id"]), {"run_id": record["run_id"], "record_path": str(_record_path(record))})


def _record_path(record: dict[str, Any]) -> Path:
    return _orchestration_run_dir(record) / "run.json"


def _stage_record_path(record: dict[str, Any], stage: str) -> Path:
    return _orchestration_run_dir(record) / "stages" / f"{stage}.json"


def _orchestration_run_dir(record: dict[str, Any]) -> Path:
    return Path(record["output_root"]) / ".orchestration" / record["run_id"]


def _api_state_dir() -> Path:
    default = Path(os.environ.get("FINANCE_DATA_ROOT", REPO_ROOT / "runs")) / ".pipeline-state"
    return Path(os.environ.get("FINANCE_PIPELINE_STATE_DIR", default)).resolve(strict=False)


def _api_index_path(run_id: str) -> Path:
    return _api_state_dir() / f"{run_id}.json"


def _find_record_path(run_id: str, output_root: Path | None = None) -> Path | None:
    candidates = []
    if output_root is not None:
        root = Path(output_root).expanduser().resolve(strict=False)
        candidates.append(root / ".orchestration" / run_id / "run.json")
        candidates.append(root / ".orchestration" / f"{run_id}.json")
    finance_root = os.environ.get("FINANCE_DATA_ROOT")
    if finance_root:
        root = Path(finance_root).expanduser().resolve(strict=False)
        candidates.extend(root.glob(f"*/.orchestration/{run_id}/run.json"))
        candidates.extend(root.glob(f"*/.orchestration/{run_id}.json"))
        candidates.append(root / ".orchestration" / run_id / "run.json")
        candidates.append(root / ".orchestration" / f"{run_id}.json")
    candidates.append(REPO_ROOT / "runs" / ".orchestration" / run_id / "run.json")
    candidates.append(REPO_ROOT / "runs" / ".orchestration" / f"{run_id}.json")
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def _scan_record_paths() -> list[Path]:
    roots = []
    finance_root = os.environ.get("FINANCE_DATA_ROOT")
    if finance_root:
        roots.append(Path(finance_root).expanduser().resolve(strict=False))
    roots.append(REPO_ROOT / "runs")
    paths = []
    for root in roots:
        if not root.exists():
            continue
        paths.extend(root.glob("*/.orchestration/*/run.json"))
        paths.extend(root.glob(".orchestration/*/run.json"))
    return sorted(set(paths))


def _run_dir(record: dict[str, Any]) -> str | None:
    path = Path(record["output_root"]) / "runs" / record["run_id"]
    return str(path) if path.exists() else None


def _summary_path(record: dict[str, Any]) -> str | None:
    path = Path(record["output_root"]) / "runs" / record["run_id"] / "result-summary.json"
    return str(path) if path.exists() else None


def _manifest_path(record: dict[str, Any]) -> str | None:
    path = Path(record["output_root"]) / "runs" / record["run_id"] / "run-manifest.json"
    return str(path) if path.exists() else None
