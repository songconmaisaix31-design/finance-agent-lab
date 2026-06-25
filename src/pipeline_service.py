import argparse
import hashlib
import json
import os
import secrets
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from .city_registry import CityProfile, CityRegistryError, get_city_profile
from .fee_calc import compute_bill_crowd_order_counts, compute_hq_fee, compute_team_delivery_cost
from .field_mapper import map_billing_sheet
from .income_calc import compute_income
from .manifest import sha256_file
from .normalizer import load_billing_rows
from .reconcile import run_all_checks
from .report import generate_report
from .result_contract import (
    atomic_write_json,
    atomic_write_text,
    decimal_string,
    git_commit,
    json_safe,
    python_version,
    utc_now_iso,
    validate_contract,
)


class PipelineError(Exception):
    exit_code = 6
    error_code = "PIPELINE_FAILED"


class RequestValidationError(PipelineError):
    exit_code = 2
    error_code = "INVALID_REQUEST"


class PathSafetyError(PipelineError):
    exit_code = 3
    error_code = "PATH_SAFETY_REJECTED"


class InputValidationError(PipelineError):
    exit_code = 4
    error_code = "INPUT_VALIDATION_FAILED"


class UnknownBusinessTypeError(PipelineError):
    exit_code = 5
    error_code = "UNKNOWN_BUSINESS_TYPE"


class OutputContractError(PipelineError):
    exit_code = 7
    error_code = "OUTPUT_CONTRACT_INVALID"


class InputChangedError(PipelineError):
    exit_code = 8
    error_code = "INPUT_CHANGED"


@dataclass(frozen=True)
class RunRequest:
    city_id: str
    input_path: Path
    output_root: Path
    mode: str
    unknown_type_policy: str
    requested_at: str
    run_id: str | None = None


@dataclass(frozen=True)
class PipelineResult:
    status: str
    exit_code: int
    run_id: str | None
    run_dir: Path | None
    summary_path: Path | None
    manifest_path: Path | None
    message: str


def make_run_request(args: argparse.Namespace) -> RunRequest:
    if not getattr(args, "city", None):
        raise RequestValidationError("--city is required")
    if not getattr(args, "input", None):
        raise RequestValidationError("--input is required")
    if not getattr(args, "output", None):
        raise RequestValidationError("--output is required")

    mode = "plan" if args.command == "plan" else ("audit" if getattr(args, "audit", False) else "execute")
    policy = getattr(args, "unknown_type_policy", None) or ("report_only" if mode == "audit" else "error")

    return RunRequest(
        city_id=args.city,
        input_path=Path(args.input),
        output_root=Path(args.output),
        mode=mode,
        unknown_type_policy=policy,
        requested_at=utc_now_iso(),
    )


def plan_request(request: RunRequest) -> PipelineResult:
    profile = _load_profile(request.city_id)
    input_path, output_root = _validate_paths(request.input_path, request.output_root)
    _validate_required_inputs(input_path)
    return PipelineResult(
        status="planned",
        exit_code=0,
        run_id=None,
        run_dir=None,
        summary_path=None,
        manifest_path=None,
        message=f"planned city={profile.city_id} input={input_path.name} output={output_root}",
    )


def run_request(request: RunRequest) -> PipelineResult:
    if request.mode == "plan":
        return plan_request(request)

    profile = _load_profile(request.city_id)
    input_path, output_root = _validate_paths(request.input_path, request.output_root)
    _validate_required_inputs(input_path)

    run_id = request.run_id or _generate_run_id(profile.city_id)
    run_dir = output_root / "runs" / run_id
    if run_dir.exists():
        raise PathSafetyError(f"Run directory already exists: {run_id}")

    artifacts_dir = run_dir / "artifacts"
    artifacts_dir.mkdir(parents=True)
    events_path = run_dir / "events.jsonl"
    logger = EventLogger(events_path, run_id, profile.city_id)
    started = utc_now_iso()
    start_perf = time.perf_counter()
    logger.event("info", "run_started", "request", "started")

    before_manifest = _input_manifest(input_path)
    status = "failed"
    exit_code = 6
    error_code = None
    error_message = None
    artifact_entries = []
    summary = {}
    manifest = {}

    try:
        logger.event("info", "input_validated", "input", "success")
        pipeline_data = _run_standard_pipeline(input_path, artifacts_dir, profile)
        logger.event("info", "pipeline_completed", "pipeline", "success")

        unknown = pipeline_data["unknown"]
        unknown_income_count = len(unknown["unknown_income_types"])
        unknown_delivery_count = len(unknown["unknown_delivery_types"])
        should_block = (
            request.unknown_type_policy == "error"
            and (unknown_income_count > 0 or unknown_delivery_count > 0)
        )

        if should_block:
            status = "blocked"
            exit_code = 5
            error_code = UnknownBusinessTypeError.error_code
            error_message = "Unknown income or delivery types detected"
            logger.event("error", "unknown_types_blocked", "business_validation", "blocked", error_code)
        elif request.mode == "audit" and (unknown_income_count > 0 or unknown_delivery_count > 0):
            status = "blocked"
            exit_code = 5
            error_code = UnknownBusinessTypeError.error_code
            error_message = "Audit collected unknown business types"
            logger.event("warning", "unknown_types_reported", "business_validation", "blocked", error_code)
        else:
            status = "success"
            exit_code = 0

        after_manifest = _input_manifest(input_path)
        if before_manifest["files"] != after_manifest["files"]:
            status = "failed"
            exit_code = InputChangedError.exit_code
            error_code = InputChangedError.error_code
            error_message = "Input files changed during run"
            logger.event("error", "input_changed", "input_integrity", "failed", error_code)
        else:
            logger.event("info", "input_unchanged", "input_integrity", "success")

        artifact_entries = _artifact_entries(artifacts_dir)
        unknown_doc = {
            "schema_version": "1.0",
            "run_id": run_id,
            "status": status,
            "unknown_type_policy": request.unknown_type_policy,
            "unknown_income_types": unknown["unknown_income_types"],
            "unknown_delivery_types": unknown["unknown_delivery_types"],
            "created_at": utc_now_iso(),
        }
        atomic_write_json(run_dir / "unknown-types.json", unknown_doc)

        summary = _build_result_summary(
            run_id, profile, status, pipeline_data, unknown_income_count,
            unknown_delivery_count, artifact_entries, started,
        )
        manifest = _build_run_manifest(
            run_id, profile, request, status, started, utc_now_iso(),
            before_manifest, artifact_entries, exit_code, error_code,
            error_message, logger.stage_names,
        )

        summary = json_safe(summary)
        manifest = json_safe(manifest)
        validate_contract("run-result.schema.json", summary)
        validate_contract("run-manifest.schema.json", manifest)
        atomic_write_json(run_dir / "result-summary.json", summary)
        atomic_write_json(run_dir / "run-manifest.json", manifest)
        logger.event("info", "contracts_written", "contract", "success")

    except Exception as exc:
        if isinstance(exc, PipelineError):
            exit_code = exc.exit_code
            error_code = exc.error_code
            error_message = str(exc)
        else:
            exit_code = 6
            error_code = "PIPELINE_EXECUTION_FAILED"
            error_message = str(exc)
        logger.event("error", "pipeline_failed", "exception", "failed", error_code)
        raise
    finally:
        duration_ms = int((time.perf_counter() - start_perf) * 1000)
        logger.event("info", "run_finished", "run", status, error_code, duration_ms)

    return PipelineResult(
        status=status,
        exit_code=exit_code,
        run_id=run_id,
        run_dir=run_dir,
        summary_path=run_dir / "result-summary.json",
        manifest_path=run_dir / "run-manifest.json",
        message=f"{status} run_id={run_id}",
    )


def _load_profile(city_id: str) -> CityProfile:
    try:
        return get_city_profile(city_id)
    except CityRegistryError as exc:
        err = RequestValidationError(str(exc))
        err.error_code = exc.error_code
        raise err from exc


def _resolve(path: Path) -> Path:
    return path.expanduser().resolve(strict=False)


def _is_relative_to(child: Path, parent: Path) -> bool:
    try:
        child.relative_to(parent)
        return True
    except ValueError:
        return False


def _validate_paths(input_path: Path, output_root: Path) -> tuple[Path, Path]:
    resolved_input = _resolve(input_path)
    resolved_output = _resolve(output_root)
    if not resolved_input.exists():
        raise InputValidationError(f"Input path does not exist: {input_path}")
    if not resolved_input.is_dir():
        raise InputValidationError(f"Input path is not a directory: {input_path}")
    if resolved_input == resolved_output:
        raise PathSafetyError("Input path and output root must be different")
    if _is_relative_to(resolved_output, resolved_input):
        raise PathSafetyError("Output root must not be inside input path")
    if _is_relative_to(resolved_input, resolved_output):
        raise PathSafetyError("Input path must not be inside output root")
    return resolved_input, resolved_output


def _validate_required_inputs(input_path: Path):
    required = ["billing_food.xlsx", "billing_retail.xlsx"]
    missing = [name for name in required if not (input_path / name).is_file()]
    if missing:
        raise InputValidationError(f"Missing required synthetic-compatible inputs: {missing}")


def _generate_run_id(city_id: str) -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"{city_id}-{stamp}-{secrets.token_hex(4)}"


def _input_manifest(input_path: Path) -> dict:
    files = []
    for file_path in sorted(p for p in input_path.rglob("*") if p.is_file()):
        files.append({
            "path": file_path.relative_to(input_path).as_posix(),
            "size_bytes": file_path.stat().st_size,
            "sha256": sha256_file(str(file_path)),
        })
    canonical = json.dumps(files, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return {
        "algorithm": "sha256",
        "file_count": len(files),
        "files": files,
        "sha256": hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
    }


def _zero_crowd_buckets() -> dict:
    zero = {
        "completed_orders": Decimal("0"),
        "total_cost": Decimal("0"),
        "avg_cost_per_order": Decimal("0"),
        "cost_table_completed_orders": Decimal("0"),
        "cost_table_total_cost": Decimal("0"),
        "final_order_count": Decimal("0"),
        "final_cost": Decimal("0"),
        "final_avg_cost": Decimal("0"),
        "capability_status": "not_evaluated_in_smoke",
    }
    return {key: dict(zero) for key in ["catering_normal", "catering_group", "retail_normal", "retail_group"]}


def _run_standard_pipeline(input_path: Path, artifacts_dir: Path, profile: CityProfile) -> dict:
    cfg = profile.config
    food_path = input_path / "billing_food.xlsx"
    retail_path = input_path / "billing_retail.xlsx"
    food_map = map_billing_sheet(str(food_path))
    retail_map = map_billing_sheet(str(retail_path))
    food_rows = load_billing_rows(str(food_path), food_map, "餐饮")
    retail_rows = load_billing_rows(str(retail_path), retail_map, "零售")

    food_income = compute_income(food_rows, cfg["food_income_whitelist"])
    retail_income = compute_income(retail_rows, cfg["retail_income_whitelist"])
    food_hq = compute_hq_fee(food_income, cfg["_headquarters_fee_rate_d"])
    retail_hq = compute_hq_fee(retail_income, cfg["_headquarters_fee_rate_d"])
    food_team = compute_team_delivery_cost(
        food_rows, cfg["food_delivery_categories"],
        cfg["_team_group_unit_cost_d"], cfg["_team_normal_unit_cost_d"],
    )
    retail_team = compute_team_delivery_cost(
        retail_rows, cfg["retail_delivery_categories"],
        cfg["_team_group_unit_cost_d"], cfg["_team_normal_unit_cost_d"],
    )
    food_crowd_bill = compute_bill_crowd_order_counts(food_rows, cfg["food_delivery_categories"], positive_only=True)
    retail_crowd_bill = compute_bill_crowd_order_counts(retail_rows, cfg["retail_delivery_categories"], positive_only=True)
    crowd_buckets = _zero_crowd_buckets()
    crowd_reconciliation = {
        "all_passed": True,
        "checks": [],
        "capability_status": "not_evaluated_in_smoke",
    }
    recon = run_all_checks(
        food_income, retail_income, food_team, retail_team,
        food_crowd_bill, retail_crowd_bill, crowd_buckets, crowd_reconciliation,
        {"all_unchanged": True}, food_rows, retail_rows, cfg["_amount_tolerance_d"],
    )

    unknown_delivery = _unknown_delivery(food_rows, retail_rows, cfg)
    food_invalid = _invalid_rows(food_rows)
    retail_invalid = _invalid_rows(retail_rows)
    report_path = artifacts_dir / f"{profile.city_id}-synthetic-report.xlsx"
    run_info = {
        "run_id": artifacts_dir.parent.name,
        "城市": profile.display_name,
        "代理商ID": cfg["agent_id"],
        "核算日期": cfg["billing_date"],
        "总部抽点比例": str(cfg["headquarters_fee_rate"]),
        "专送拼团单均成本": str(cfg["team_delivery"]["group_unit_cost"]),
        "专送正常单单均成本": str(cfg["team_delivery"]["normal_unit_cost"]),
        "开始时间": utc_now_iso(),
        "capability_note": "Synthetic smoke run; crowd cost and full reconciliation are not business-validated in Phase 2C.",
    }
    generate_report(
        str(report_path), run_info, food_income, retail_income, food_hq, retail_hq,
        food_team, retail_team, crowd_buckets, recon["bill_cost_comparisons"],
        crowd_reconciliation, food_income["unknown_types"], retail_income["unknown_types"],
        food_invalid, retail_invalid, unknown_delivery, recon, [],
    )

    return {
        "food_income": food_income,
        "retail_income": retail_income,
        "food_hq": food_hq,
        "retail_hq": retail_hq,
        "food_team": food_team,
        "retail_team": retail_team,
        "reconciliation": recon,
        "unknown": {
            "unknown_income_types": [
                {"business": "餐饮", **u} for u in food_income["unknown_types"]
            ] + [
                {"business": "零售", **u} for u in retail_income["unknown_types"]
            ],
            "unknown_delivery_types": unknown_delivery,
        },
        "capabilities": {
            "crowd_cost": "not_evaluated_in_smoke",
            "reconciliation": "limited_smoke_checks",
            "report": "generated",
        },
    }


def _unknown_delivery(food_rows, retail_rows, cfg: dict) -> list[dict]:
    allowed = {
        category["delivery_method"]
        for group in (cfg["food_delivery_categories"], cfg["retail_delivery_categories"])
        for category in group.values()
    }
    unknown = []
    for business, rows in [("餐饮", food_rows), ("零售", retail_rows)]:
        counts = {}
        for row in rows:
            if row.delivery_type and row.delivery_type not in allowed:
                counts[row.delivery_type] = counts.get(row.delivery_type, 0) + 1
        unknown.extend(
            {"business": business, "delivery_type": delivery_type, "count": count}
            for delivery_type, count in sorted(counts.items())
        )
    return unknown


def _invalid_rows(rows) -> list[dict]:
    return [
        {
            "source_file": row.source_file,
            "source_row": row.source_row,
            "order_id": row.order_id,
            "error": row.amount_error,
        }
        for row in rows
        if not row.amount_valid
    ]


def _artifact_entries(artifacts_dir: Path) -> list[dict]:
    entries = []
    for file_path in sorted(p for p in artifacts_dir.rglob("*") if p.is_file()):
        entries.append({
            "name": file_path.name,
            "path": file_path.relative_to(artifacts_dir.parent).as_posix(),
            "media_type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            if file_path.suffix.lower() == ".xlsx" else "application/octet-stream",
            "sha256": sha256_file(str(file_path)),
            "size_bytes": file_path.stat().st_size,
        })
    return entries


def _build_result_summary(
    run_id: str,
    profile: CityProfile,
    status: str,
    data: dict,
    unknown_income_count: int,
    unknown_delivery_count: int,
    artifacts: list[dict],
    created_at: str,
) -> dict:
    recon = data["reconciliation"]
    warnings = 0
    if data["capabilities"]["crowd_cost"] != "validated":
        warnings += 1
    return {
        "schema_version": "1.0",
        "run_id": run_id,
        "city": {"id": profile.city_id, "name": profile.display_name},
        "status": status,
        "period": {"start": None, "end": None},
        "config": {
            "version": profile.schema_version,
            "sha256": profile.config_sha256,
            "approval_status": profile.rule_approval_status,
        },
        "metrics": {
            "food_income_total": decimal_string(data["food_income"]["total_settlement"]),
            "retail_income_total": decimal_string(data["retail_income"]["total_settlement"]),
            "food_hq_fee": decimal_string(data["food_hq"]["hq_fee"]),
            "retail_hq_fee": decimal_string(data["retail_hq"]["hq_fee"]),
            "food_team_delivery_cost": decimal_string(data["food_team"]["total_team_cost"]),
            "retail_team_delivery_cost": decimal_string(data["retail_team"]["total_team_cost"]),
            "food_order_count": str(data["food_income"]["total_distinct_orders"]),
            "retail_order_count": str(data["retail_income"]["total_distinct_orders"]),
        },
        "validation": {
            "unknown_income_types": unknown_income_count,
            "unknown_delivery_types": unknown_delivery_count,
            "reconciliation_errors": 0 if recon.get("all_passed") else 1,
            "warnings": warnings,
        },
        "capabilities": data["capabilities"],
        "artifacts": artifacts,
        "created_at": created_at,
    }


def _build_run_manifest(
    run_id: str,
    profile: CityProfile,
    request: RunRequest,
    status: str,
    started_at: str,
    ended_at: str,
    input_manifest: dict,
    artifacts: list[dict],
    exit_code: int,
    error_code: str | None,
    error_message: str | None,
    stages: list[str],
) -> dict:
    return {
        "schema_version": "1.0",
        "run_id": run_id,
        "city_id": profile.city_id,
        "mode": request.mode,
        "status": status,
        "started_at": started_at,
        "ended_at": ended_at,
        "input": {
            "local_path": str(_resolve(request.input_path)),
            "manifest_sha256": input_manifest["sha256"],
            "file_count": input_manifest["file_count"],
            "private_local_only": True,
        },
        "config": {
            "sha256": profile.config_sha256,
            "version": profile.schema_version,
            "approval_status": profile.rule_approval_status,
        },
        "application": {
            "commit": git_commit(),
            "python_version": python_version(),
            "entrypoint": "python -m src.cli",
        },
        "stages": stages,
        "exit_code": exit_code,
        "error_code": error_code,
        "error_message": error_message,
        "artifacts": artifacts,
    }


class EventLogger:
    def __init__(self, path: Path, run_id: str, city_id: str):
        self.path = path
        self.run_id = run_id
        self.city_id = city_id
        self.stage_names = []

    def event(
        self,
        level: str,
        event: str,
        stage: str,
        outcome: str,
        error_code: str | None = None,
        duration_ms: int = 0,
    ):
        if stage not in self.stage_names:
            self.stage_names.append(stage)
        data = {
            "timestamp_utc": utc_now_iso(),
            "run_id": self.run_id,
            "level": level,
            "event": event,
            "stage": stage,
            "city_id": self.city_id,
            "outcome": outcome,
            "duration_ms": duration_ms,
            "error_code": error_code,
        }
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(data, ensure_ascii=False, separators=(",", ":")) + "\n")
