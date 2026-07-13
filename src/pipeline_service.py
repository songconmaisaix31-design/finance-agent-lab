import argparse
import hashlib
import json
import os
import secrets
import sqlite3
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

from .city_registry import CityProfile, CityRegistryError, get_city_profile
from .crowd_cost_contract import CrowdCostError, build_crowd_cost_result, crowd_result_for_summary
from .fee_calc import compute_bill_crowd_order_counts, compute_hq_fee, compute_team_delivery_cost
from .field_mapper import map_billing_sheet
from .income_calc import compute_income
from .manifest import sha256_file
from .normalizer import load_billing_rows
from .normalizer import NormalizedBillingRow
from .reconcile import run_all_checks
from .reconciliation_contract import (
    build_reconciliation_contract,
    build_reconciliation_report,
)
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


class CityRuleSetMissingError(PipelineError):
    exit_code = 5
    error_code = "CITY_RULE_SET_MISSING"


class CityNamespaceMismatchError(PipelineError):
    exit_code = 3
    error_code = "CITY_STORAGE_NAMESPACE_MISMATCH"


class OutputContractError(PipelineError):
    exit_code = 7
    error_code = "OUTPUT_CONTRACT_INVALID"


class InputChangedError(PipelineError):
    exit_code = 8
    error_code = "INPUT_CHANGED"


FOOD_BUSINESS = "food"
RETAIL_BUSINESS = "retail"


class StageDependencyError(PipelineError):
    exit_code = 9
    error_code = "STAGE_DEPENDENCY_NOT_SATISFIED"


class ArtifactIntegrityError(PipelineError):
    exit_code = 9
    error_code = "ARTIFACT_INTEGRITY_FAILED"


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


@dataclass(frozen=True)
class StageExecutionContext:
    request: RunRequest
    profile: CityProfile
    input_path: Path
    output_root: Path
    run_id: str
    run_dir: Path
    artifacts_dir: Path
    started_at: str


@dataclass(frozen=True)
class StageServiceResult:
    stage: str
    status: str
    metrics: dict[str, str]
    output_artifacts: list[dict[str, Any]]
    message: str
    result: dict[str, Any] | None = None


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
    input_path, output_root = _validate_paths(request.input_path, request.output_root, profile.city_id)
    _validate_city_namespace_paths(profile, input_path, output_root)
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

    context = create_stage_context(request, create_run_dir=True)
    status = "failed"
    error_code = None
    start_perf = time.perf_counter()
    logger = EventLogger(context.run_dir / "events.jsonl", context.run_id, context.profile.city_id)
    logger.event("info", "run_started", "request", "started")
    try:
        for stage_fn in (
            run_intake_stage,
            run_normalize_stage,
            run_calculate_stage,
            run_reconcile_stage,
            run_report_stage,
        ):
            result = stage_fn(context)
            logger.event("info", f"{result.stage}_completed", result.stage, result.status)
            if result.status not in {"success", "warning"}:
                break
        summary = _load_json(context.run_dir / "result-summary.json")
        status = summary.get("status", result.status if result else "failed")
        error_code = None if status == "success" else summary.get("error_code")
        exit_code = 0 if status == "success" else 5 if status == "blocked" else 6
    except Exception as exc:
        if isinstance(exc, CrowdCostError):
            wrapped = InputValidationError(f"{exc.error_code}: {exc.safe_message}")
            wrapped.error_code = exc.error_code
            error_code = exc.error_code
            logger.event("error", "pipeline_failed", "exception", "failed", error_code)
            raise wrapped from exc
        error_code = getattr(exc, "error_code", "PIPELINE_EXECUTION_FAILED")
        logger.event("error", "pipeline_failed", "exception", "failed", error_code)
        raise
    finally:
        duration_ms = int((time.perf_counter() - start_perf) * 1000)
        logger.event("info", "run_finished", "run", status, error_code, duration_ms)

    return PipelineResult(
        status=status,
        exit_code=exit_code,
        run_id=context.run_id,
        run_dir=context.run_dir,
        summary_path=context.run_dir / "result-summary.json",
        manifest_path=context.run_dir / "run-manifest.json",
        message=f"{status} run_id={context.run_id}",
    )


def create_stage_context(request: RunRequest, *, run_id: str | None = None, create_run_dir: bool = False) -> StageExecutionContext:
    profile = _load_profile(request.city_id)
    input_path, output_root = _validate_paths(request.input_path, request.output_root, profile.city_id)
    _validate_city_namespace_paths(profile, input_path, output_root)
    if profile.rule_status == "missing":
        raise CityRuleSetMissingError(f"Business rule set missing for city_id: {profile.city_id}")
    _validate_required_inputs(input_path)

    resolved_run_id = run_id or request.run_id or _generate_run_id(profile.city_id)
    run_dir = output_root / "runs" / resolved_run_id
    if create_run_dir and run_dir.exists():
        raise PathSafetyError(f"Run directory already exists: {resolved_run_id}")
    artifacts_dir = run_dir / "artifacts"
    if create_run_dir:
        artifacts_dir.mkdir(parents=True)
    else:
        artifacts_dir.mkdir(parents=True, exist_ok=True)
    return StageExecutionContext(
        request=request,
        profile=profile,
        input_path=input_path,
        output_root=output_root,
        run_id=resolved_run_id,
        run_dir=run_dir,
        artifacts_dir=artifacts_dir,
        started_at=request.requested_at or utc_now_iso(),
    )


def run_intake_stage(context: StageExecutionContext) -> StageServiceResult:
    context.run_dir.mkdir(parents=True, exist_ok=True)
    before_manifest = _input_manifest(context.input_path)
    manifest = {
        "schema_version": "1.0",
        "producer_stage": "intake",
        "contract_version": "1",
        "run_id": context.run_id,
        "city_id": context.profile.city_id,
        "city_namespace": context.profile.storage_namespace,
        "input_path": str(context.input_path),
        "profile": {
            "profile_id": context.profile.pipeline_profile.profile_id,
            "version": context.profile.pipeline_profile.version,
        },
        "config": {
            "sha256": context.profile.config_sha256,
            "version": context.profile.schema_version,
        },
        **before_manifest,
    }
    run_context = {
        "schema_version": "1.0",
        "producer_stage": "intake",
        "contract_version": "1",
        "run_id": context.run_id,
        "city_id": context.profile.city_id,
        "input_path": str(context.input_path),
        "output_root": str(context.output_root),
        "run_dir": str(context.run_dir),
        "mode": context.request.mode,
        "unknown_type_policy": context.request.unknown_type_policy,
        "requested_at": context.request.requested_at,
        "config_hash": context.profile.config_sha256,
    }
    atomic_write_json(context.run_dir / "input-manifest.json", manifest)
    atomic_write_json(context.run_dir / "run-context.json", run_context)
    return StageServiceResult(
        stage="intake",
        status="success",
        metrics={"input_file_count": str(manifest["file_count"])},
        output_artifacts=[
            _artifact_ref(context.run_dir, context.run_dir / "input-manifest.json", "intake"),
            _artifact_ref(context.run_dir, context.run_dir / "run-context.json", "intake"),
        ],
        message=f"intake complete city={context.profile.city_id}",
    )


def run_normalize_stage(context: StageExecutionContext) -> StageServiceResult:
    _require_file(context.run_dir / "input-manifest.json", "intake")
    cfg = context.profile.config
    normalized_dir = context.run_dir / "normalized-data"
    normalized_dir.mkdir(parents=True, exist_ok=True)
    db_path = normalized_dir / "normalized.sqlite"

    food_path = context.input_path / "billing_food.xlsx"
    retail_path = context.input_path / "billing_retail.xlsx"
    food_map = map_billing_sheet(str(food_path))
    retail_map = map_billing_sheet(str(retail_path))
    food_rows = load_billing_rows(str(food_path), food_map, FOOD_BUSINESS)
    retail_rows = load_billing_rows(str(retail_path), retail_map, RETAIL_BUSINESS)
    _write_normalized_sqlite(db_path, [*food_rows, *retail_rows])

    rejected_rows = len(_invalid_rows(food_rows)) + len(_invalid_rows(retail_rows))
    manifest = {
        "schema_version": "1.0",
        "producer_stage": "normalize",
        "contract_version": "1",
        "run_id": context.run_id,
        "row_count": len(food_rows) + len(retail_rows),
        "source_files": ["billing_food.xlsx", "billing_retail.xlsx"],
        "normalized_artifact": _artifact_ref(context.run_dir, db_path, "normalize"),
        "field_mapping_version": "field_mapper.v1",
        "field_mappings": {
            "food": _field_mapping_summary(food_map),
            "retail": _field_mapping_summary(retail_map),
        },
        "unknown_columns": [],
        "rejected_rows": rejected_rows,
        "config_hash": context.profile.config_sha256,
        "input_manifest_sha256": _load_json(context.run_dir / "input-manifest.json")["sha256"],
    }
    schema_report = {
        "schema_version": "1.0",
        "producer_stage": "normalize",
        "run_id": context.run_id,
        "storage": "sqlite",
        "decimal_storage": "string",
        "tables": {"billing_rows": len(food_rows) + len(retail_rows)},
    }
    atomic_write_json(context.run_dir / "normalization-manifest.json", manifest)
    atomic_write_json(context.run_dir / "schema-report.json", schema_report)
    return StageServiceResult(
        stage="normalize",
        status="success",
        metrics={"normalized_row_count": str(manifest["row_count"]), "rejected_rows": str(rejected_rows)},
        output_artifacts=[
            manifest["normalized_artifact"],
            _artifact_ref(context.run_dir, context.run_dir / "normalization-manifest.json", "normalize"),
            _artifact_ref(context.run_dir, context.run_dir / "schema-report.json", "normalize"),
        ],
        message="normalize complete",
    )


def run_calculate_stage(context: StageExecutionContext) -> StageServiceResult:
    normalization_manifest = _load_required_json(context.run_dir / "normalization-manifest.json", "normalize")
    normalized_artifact = context.run_dir / normalization_manifest["normalized_artifact"]["path"]
    _verify_artifact(normalization_manifest["normalized_artifact"], context.run_dir)
    food_rows, retail_rows = _load_normalized_rows(normalized_artifact)
    data = _calculate_pipeline_data(context.input_path, context.profile, food_rows, retail_rows)
    result = {
        "schema_version": "1.0",
        "producer_stage": "calculate",
        "contract_version": "1",
        "run_id": context.run_id,
        "input_artifacts": [normalization_manifest["normalized_artifact"]],
        "config_hash": context.profile.config_sha256,
        "pipeline_data": json_safe(data),
    }
    atomic_write_json(context.run_dir / "calculation-result.json", result)
    manifest = {
        "schema_version": "1.0",
        "producer_stage": "calculate",
        "contract_version": "1",
        "run_id": context.run_id,
        "input_artifacts": [normalization_manifest["normalized_artifact"]],
        "output_artifacts": [_artifact_ref(context.run_dir, context.run_dir / "calculation-result.json", "calculate")],
        "config_hash": context.profile.config_sha256,
    }
    atomic_write_json(context.run_dir / "calculation-manifest.json", manifest)
    metrics = _metrics_from_pipeline_data(data)
    metrics.update({
        "crowd_total": str(data["costs"]["crowd"]["total"]),
        "warnings": "0",
    })
    return StageServiceResult(
        stage="calculate",
        status="success",
        metrics=metrics,
        output_artifacts=manifest["output_artifacts"],
        message="calculate complete",
        result={"summary": metrics},
    )


def run_reconcile_stage(context: StageExecutionContext) -> StageServiceResult:
    calculation = _load_required_json(context.run_dir / "calculation-result.json", "calculate")
    calc_artifact = _artifact_ref(context.run_dir, context.run_dir / "calculation-result.json", "calculate")
    _verify_artifact(calc_artifact, context.run_dir)
    normalization_manifest = _load_required_json(context.run_dir / "normalization-manifest.json", "normalize")
    normalized_artifact = context.run_dir / normalization_manifest["normalized_artifact"]["path"]
    food_rows, retail_rows = _load_normalized_rows(normalized_artifact)
    data = _restore_pipeline_data(calculation["pipeline_data"])
    cfg = context.profile.config
    recon = run_all_checks(
        data["food_income"], data["retail_income"], data["food_team"], data["retail_team"],
        data["food_crowd_bill"], data["retail_crowd_bill"], data["crowd_buckets"],
        data["crowd_reconciliation"], {"all_unchanged": True}, food_rows, retail_rows,
        cfg["_amount_tolerance_d"],
    )
    data["reconciliation"] = recon
    calculation["pipeline_data"] = json_safe(data)
    atomic_write_json(context.run_dir / "calculation-result.json", calculation)

    quality = {
        "schema_version": "1.0",
        "producer_stage": "reconcile",
        "contract_version": "1",
        "run_id": context.run_id,
        "status": "success" if recon.get("all_passed") else "failed",
        "reconciliation_errors": 0 if recon.get("all_passed") else 1,
        "input_artifacts": [calc_artifact, normalization_manifest["normalized_artifact"]],
    }
    stage_report = {
        "schema_version": "1.0",
        "producer_stage": "reconcile",
        "run_id": context.run_id,
        "technical_reconciliation": json_safe(recon),
        "quality_gate": quality,
    }
    atomic_write_json(context.run_dir / "stage-reconciliation-report.json", stage_report)
    atomic_write_json(context.run_dir / "quality-gate-result.json", quality)
    status = "success" if quality["status"] == "success" else "failed"
    return StageServiceResult(
        stage="reconcile",
        status=status,
        metrics={"reconciliation_errors": str(quality["reconciliation_errors"])},
        output_artifacts=[
            _artifact_ref(context.run_dir, context.run_dir / "stage-reconciliation-report.json", "reconcile"),
            _artifact_ref(context.run_dir, context.run_dir / "quality-gate-result.json", "reconcile"),
        ],
        message="reconcile complete",
        result=quality,
    )


def run_report_stage(context: StageExecutionContext) -> StageServiceResult:
    calculation = _load_required_json(context.run_dir / "calculation-result.json", "calculate")
    quality = _load_required_json(context.run_dir / "quality-gate-result.json", "reconcile")
    if quality.get("status") not in {"success", "warning"}:
        raise StageDependencyError("Report stage requires a passing reconciliation quality gate")
    normalization_manifest = _load_required_json(context.run_dir / "normalization-manifest.json", "normalize")
    normalized_artifact = context.run_dir / normalization_manifest["normalized_artifact"]["path"]
    food_rows, retail_rows = _load_normalized_rows(normalized_artifact)
    data = _restore_pipeline_data(calculation["pipeline_data"])
    data["reconciliation"] = _restore_pipeline_data(data["reconciliation"])

    unknown = data["unknown"]
    unknown_income_count = len(unknown["unknown_income_types"])
    unknown_delivery_count = len(unknown["unknown_delivery_types"])
    unknown_crowd_count = len(unknown.get("unknown_crowd_cost_rows", []))
    rejected_crowd_count = data.get("costs", {}).get("crowd", {}).get("rejected_rows", 0)
    should_block = (
        context.request.unknown_type_policy == "error"
        and (unknown_income_count > 0 or unknown_delivery_count > 0 or unknown_crowd_count > 0 or rejected_crowd_count > 0)
    )
    audit_block = (
        context.request.mode == "audit"
        and (unknown_income_count > 0 or unknown_delivery_count > 0 or unknown_crowd_count > 0 or rejected_crowd_count > 0)
    )
    status = "blocked" if should_block or audit_block else "success"
    exit_code = 5 if should_block or audit_block else 0
    error_code = UnknownBusinessTypeError.error_code if should_block or audit_block else None
    error_message = (
        "Audit collected unknown business types"
        if audit_block else "Unknown or invalid business types detected"
        if should_block else None
    )

    report_path = context.artifacts_dir / f"{context.profile.city_id}-synthetic-report.xlsx"
    run_info = _report_run_info(context)
    generate_report(
        str(report_path), run_info, data["food_income"], data["retail_income"], data["food_hq"], data["retail_hq"],
        data["food_team"], data["retail_team"], data["crowd_buckets"], data["reconciliation"]["bill_cost_comparisons"],
        data["crowd_reconciliation"], data["food_income"]["unknown_types"], data["retail_income"]["unknown_types"],
        _invalid_rows(food_rows), _invalid_rows(retail_rows), data["unknown"]["unknown_delivery_types"],
        data["reconciliation"], [],
    )
    artifact_entries = _artifact_entries(context.artifacts_dir)
    input_before = _load_json(context.run_dir / "input-manifest.json")
    input_after = _input_manifest(context.input_path)
    if input_before.get("files") != input_after.get("files"):
        status = "failed"
        exit_code = InputChangedError.exit_code
        error_code = InputChangedError.error_code
        error_message = "Input files changed during run"

    unknown_doc = {
        "schema_version": "1.0",
        "producer_stage": "report",
        "run_id": context.run_id,
        "status": status,
        "unknown_type_policy": context.request.unknown_type_policy,
        "unknown_income_types": unknown["unknown_income_types"],
        "unknown_delivery_types": unknown["unknown_delivery_types"],
        "unknown_crowd_cost_rows": unknown.get("unknown_crowd_cost_rows", []),
        "created_at": utc_now_iso(),
    }
    atomic_write_json(context.run_dir / "unknown-types.json", unknown_doc)

    summary = _build_result_summary(
        context.run_id, context.profile, status, data, unknown_income_count,
        unknown_delivery_count, artifact_entries, context.started_at,
    )
    manifest = _build_run_manifest(
        context.run_id, context.profile, context.request, status, context.started_at, utc_now_iso(),
        input_before, artifact_entries, exit_code, error_code, error_message,
        ["intake", "normalize", "calculate", "reconcile", "report"],
    )
    reconciliation = build_reconciliation_contract(
        summary=summary,
        manifest=manifest,
        run_dir=context.run_dir,
        request_context=_reconciliation_context(context.run_id, context.profile, context.request, status),
        input_before=input_before,
        input_after=input_after,
    )
    if status == "success" and reconciliation["status"] in {"failed", "blocked"}:
        status = "blocked" if reconciliation["status"] == "blocked" else "failed"
        exit_code = 5 if status == "blocked" else 6
        error_code = "RECON_UPSTREAM_BLOCKED" if status == "blocked" else "RECONCILIATION_FAILED"
        error_message = "Reconciliation blocked" if status == "blocked" else "Reconciliation failed"
        summary = _build_result_summary(
            context.run_id, context.profile, status, data, unknown_income_count,
            unknown_delivery_count, artifact_entries, context.started_at,
        )
        manifest = _build_run_manifest(
            context.run_id, context.profile, context.request, status, context.started_at, utc_now_iso(),
            input_before, artifact_entries, exit_code, error_code, error_message,
            ["intake", "normalize", "calculate", "reconcile", "report"],
        )
        reconciliation = build_reconciliation_contract(
            summary=summary,
            manifest=manifest,
            run_dir=context.run_dir,
            request_context=_reconciliation_context(context.run_id, context.profile, context.request, status),
            input_before=input_before,
            input_after=input_after,
        )
    _attach_reconciliation(summary, reconciliation)
    summary = json_safe(summary)
    manifest = json_safe(manifest)
    reconciliation_report = json_safe(build_reconciliation_report(context.run_id, reconciliation))
    validate_contract("run-result.schema.json", summary)
    validate_contract("run-manifest.schema.json", manifest)
    atomic_write_json(context.run_dir / "result-summary.json", summary)
    atomic_write_json(context.run_dir / "run-manifest.json", manifest)
    atomic_write_json(context.run_dir / "reconciliation-report.json", reconciliation_report)
    artifact_manifest = {
        "schema_version": "1.0",
        "producer_stage": "report",
        "run_id": context.run_id,
        "artifacts": artifact_entries,
    }
    atomic_write_json(context.run_dir / "artifact-manifest.json", artifact_manifest)
    return StageServiceResult(
        stage="report",
        status="success" if status == "success" else "rejected" if status == "blocked" else "failed",
        metrics={
            **_metrics_from_pipeline_data(data),
            "warnings": str(summary["validation"]["warnings"]),
            "errors": str(summary["validation"]["reconciliation_errors"]),
            "artifact_count": str(len(artifact_entries)),
            "report_count": str(sum(1 for item in artifact_entries if item["name"].endswith(".xlsx"))),
        },
        output_artifacts=[
            *[_artifact_ref(context.run_dir, context.run_dir / item["path"], "report") for item in artifact_entries],
            _artifact_ref(context.run_dir, context.run_dir / "result-summary.json", "report"),
            _artifact_ref(context.run_dir, context.run_dir / "run-manifest.json", "report"),
            _artifact_ref(context.run_dir, context.run_dir / "artifact-manifest.json", "report"),
        ],
        message=f"{status} run_id={context.run_id}",
        result={"summary_path": str(context.run_dir / "result-summary.json"), "manifest_path": str(context.run_dir / "run-manifest.json")},
    )


NORMALIZED_COLUMNS = [
    "source_file", "source_sheet", "source_row", "billing_date", "business_category",
    "order_id", "order_type", "delivery_type", "service_package_type",
    "settlement_amount", "gross_transaction_amount", "net_transaction_amount",
    "merchant_id", "merchant_name", "completed_at", "remark",
    "agent_delivery_subsidy", "amount_valid", "amount_error",
]


def _write_normalized_sqlite(path: Path, rows: list[NormalizedBillingRow]):
    if path.exists():
        path.unlink()
    conn = sqlite3.connect(path)
    try:
        conn.execute(
            """
            CREATE TABLE billing_rows (
              source_file TEXT, source_sheet TEXT, source_row INTEGER,
              billing_date TEXT, business_category TEXT, order_id TEXT,
              order_type TEXT, delivery_type TEXT, service_package_type TEXT,
              settlement_amount TEXT, gross_transaction_amount TEXT,
              net_transaction_amount TEXT, merchant_id TEXT, merchant_name TEXT,
              completed_at TEXT, remark TEXT, agent_delivery_subsidy TEXT,
              amount_valid INTEGER, amount_error TEXT
            )
            """
        )
        for row in rows:
            data = asdict(row)
            conn.execute(
                f"INSERT INTO billing_rows ({','.join(NORMALIZED_COLUMNS)}) VALUES ({','.join('?' for _ in NORMALIZED_COLUMNS)})",
                [_sqlite_value(data[column]) for column in NORMALIZED_COLUMNS],
            )
        conn.commit()
    finally:
        conn.close()


def _load_normalized_rows(path: Path) -> tuple[list[NormalizedBillingRow], list[NormalizedBillingRow]]:
    if not path.exists():
        raise ArtifactIntegrityError(f"Normalized artifact missing: {path.name}")
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    try:
        rows = [_row_from_sqlite(dict(row)) for row in conn.execute("SELECT * FROM billing_rows ORDER BY source_file, source_row")]
    finally:
        conn.close()
    food = [row for row in rows if row.business_category == FOOD_BUSINESS]
    retail = [row for row in rows if row.business_category == RETAIL_BUSINESS]
    return food, retail


def _row_from_sqlite(data: dict[str, Any]) -> NormalizedBillingRow:
    return NormalizedBillingRow(
        source_file=data["source_file"],
        source_sheet=data["source_sheet"],
        source_row=int(data["source_row"]),
        billing_date=data["billing_date"],
        business_category=data["business_category"],
        order_id=data["order_id"],
        order_type=data["order_type"],
        delivery_type=data["delivery_type"],
        service_package_type=data["service_package_type"],
        settlement_amount=_optional_decimal(data["settlement_amount"]),
        gross_transaction_amount=_optional_decimal(data["gross_transaction_amount"]),
        net_transaction_amount=_optional_decimal(data["net_transaction_amount"]),
        merchant_id=data["merchant_id"],
        merchant_name=data["merchant_name"],
        completed_at=data["completed_at"],
        remark=data["remark"],
        agent_delivery_subsidy=_optional_decimal(data["agent_delivery_subsidy"]),
        amount_valid=bool(data["amount_valid"]),
        amount_error=data["amount_error"] or "",
    )


def _sqlite_value(value):
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, bool):
        return 1 if value else 0
    if value is None:
        return ""
    return value


def _optional_decimal(value: str | None) -> Decimal | None:
    if value is None or value == "":
        return None
    return Decimal(str(value))


def _calculate_pipeline_data(
    input_path: Path,
    profile: CityProfile,
    food_rows: list[NormalizedBillingRow],
    retail_rows: list[NormalizedBillingRow],
) -> dict:
    cfg = profile.config
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
    crowd_cost_file = input_path / cfg["crowd_cost"].get("input_file_name", "crowd_cost.xlsx")
    crowd_cost_result = build_crowd_cost_result(crowd_cost_file, cfg)
    crowd_buckets = crowd_cost_result["raw_buckets"]
    crowd_reconciliation = {
        "all_passed": True,
        "checks": [],
        "capability_status": "partial_unverified",
    }
    unknown_delivery = _unknown_delivery(food_rows, retail_rows, cfg)
    return {
        "food_income": food_income,
        "retail_income": retail_income,
        "food_hq": food_hq,
        "retail_hq": retail_hq,
        "food_team": food_team,
        "retail_team": retail_team,
        "food_crowd_bill": food_crowd_bill,
        "retail_crowd_bill": retail_crowd_bill,
        "crowd_buckets": crowd_buckets,
        "crowd_reconciliation": crowd_reconciliation,
        "reconciliation": {"all_passed": False, "bill_cost_comparisons": []},
        "unknown": {
            "unknown_income_types": [
                {"business": FOOD_BUSINESS, **u} for u in food_income["unknown_types"]
            ] + [
                {"business": RETAIL_BUSINESS, **u} for u in retail_income["unknown_types"]
            ],
            "unknown_delivery_types": unknown_delivery,
            "unknown_crowd_cost_rows": crowd_cost_result["unknown_rows"],
        },
        "costs": {
            "crowd": crowd_result_for_summary(crowd_cost_result),
        },
        "capabilities": {
            "crowd_cost": "complete" if crowd_cost_result["status"] == "complete" else "blocked",
            "reconciliation": "partial_unverified",
            "report": "generated",
        },
    }


def _metrics_from_pipeline_data(data: dict) -> dict[str, str]:
    return {
        "food_income_total": decimal_string(data["food_income"]["total_settlement"]),
        "retail_income_total": decimal_string(data["retail_income"]["total_settlement"]),
        "food_hq_fee": decimal_string(data["food_hq"]["hq_fee"]),
        "retail_hq_fee": decimal_string(data["retail_hq"]["hq_fee"]),
        "food_team_delivery_cost": decimal_string(data["food_team"]["total_team_cost"]),
        "retail_team_delivery_cost": decimal_string(data["retail_team"]["total_team_cost"]),
        "food_order_count": str(data["food_income"]["total_distinct_orders"]),
        "retail_order_count": str(data["retail_income"]["total_distinct_orders"]),
    }


def _restore_pipeline_data(value):
    if isinstance(value, dict):
        return {key: _restore_pipeline_data(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_restore_pipeline_data(item) for item in value]
    if isinstance(value, str) and _looks_decimal(value):
        return Decimal(value)
    return value


def _looks_decimal(value: str) -> bool:
    if not value:
        return False
    allowed = set("0123456789.-")
    return set(value) <= allowed and any(ch.isdigit() for ch in value)


def _field_mapping_summary(mapping) -> dict[str, Any]:
    return {
        "source_file": Path(mapping.source_file).name,
        "source_sheet": mapping.source_sheet,
        "header_row": mapping.header_row,
        "data_start_row": mapping.data_start_row,
        "columns": sorted(mapping.column_map),
    }


def _report_run_info(context: StageExecutionContext) -> dict:
    cfg = context.profile.config
    return {
        "run_id": context.run_id,
        "city": context.profile.display_name,
        "agent_id": cfg["agent_id"],
        "billing_date": cfg["billing_date"],
        "headquarters_fee_rate": str(cfg["headquarters_fee_rate"]),
        "team_group_unit_cost": str(cfg["team_delivery"]["group_unit_cost"]),
        "team_normal_unit_cost": str(cfg["team_delivery"]["normal_unit_cost"]),
        "started_at": utc_now_iso(),
        "capability_note": "Synthetic smoke run; crowd cost extraction is characterized with unverified business rules. Full reconciliation is not complete.",
    }


def _artifact_ref(run_dir: Path, path: Path, producer_stage: str) -> dict[str, Any]:
    if not path.exists():
        raise ArtifactIntegrityError(f"Artifact missing: {path}")
    return {
        "schema_version": "1.0",
        "producer_stage": producer_stage,
        "name": path.name,
        "path": path.relative_to(run_dir).as_posix(),
        "media_type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        if path.suffix.lower() == ".xlsx" else "application/octet-stream",
        "sha256": sha256_file(str(path)),
        "size_bytes": path.stat().st_size,
    }


def _verify_artifact(artifact: dict[str, Any], run_dir: Path):
    path = run_dir / artifact["path"]
    if not path.exists():
        raise ArtifactIntegrityError(f"Required artifact missing: {artifact['path']}")
    current = sha256_file(str(path))
    if current != artifact.get("sha256"):
        raise ArtifactIntegrityError(f"Artifact hash mismatch: {artifact['path']}")


def _require_file(path: Path, stage: str):
    if not path.exists():
        raise StageDependencyError(f"{stage} artifact missing: {path.name}")


def _load_required_json(path: Path, producer_stage: str) -> dict:
    _require_file(path, producer_stage)
    return _load_json(path)


def _load_json(path: Path | None) -> dict[str, Any]:
    if not path or not Path(path).exists():
        return {}
    return json.loads(Path(path).read_text(encoding="utf-8"))


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


def _validate_paths(input_path: Path, output_root: Path, city_id: str) -> tuple[Path, Path]:
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
    if _is_relative_to(resolved_input, resolved_output) and not _is_allowed_city_root_input(resolved_input, resolved_output, city_id):
        raise PathSafetyError("Input path must not be inside output root")
    return resolved_input, resolved_output


def _is_allowed_city_root_input(input_path: Path, output_root: Path, city_id: str) -> bool:
    try:
        rel = input_path.relative_to(output_root)
    except ValueError:
        return False
    return output_root.name.lower() == city_id and rel.parts == ("incoming",)


def _validate_city_namespace_paths(profile: CityProfile, input_path: Path, output_root: Path):
    input_city = _detect_city_namespace(input_path)
    output_city = _detect_city_namespace(output_root)
    if input_city and input_city != profile.city_id:
        raise CityNamespaceMismatchError(f"Input namespace belongs to {input_city}, not {profile.city_id}")
    if output_city and output_city != profile.city_id:
        raise CityNamespaceMismatchError(f"Output namespace belongs to {output_city}, not {profile.city_id}")


def _detect_city_namespace(path: Path) -> str | None:
    city_ids = {"guan", "xianghe", "yicheng", "yongcheng", "queshan", "biyang"}
    namespace_names = {"incoming", "staging", "runs", "exports", "quarantine", "archive"}
    parts = [part.lower() for part in path.parts]
    for index, part in enumerate(parts):
        if part in city_ids:
            if index == len(parts) - 1 or (index + 1 < len(parts) and parts[index + 1] in namespace_names):
                return part
    return None


def _validate_required_inputs(input_path: Path):
    required = ["billing_food.xlsx", "billing_retail.xlsx", "crowd_cost.xlsx"]
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
    food_rows = load_billing_rows(str(food_path), food_map, FOOD_BUSINESS)
    retail_rows = load_billing_rows(str(retail_path), retail_map, RETAIL_BUSINESS)

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
    crowd_cost_file = input_path / cfg["crowd_cost"].get("input_file_name", "crowd_cost.xlsx")
    crowd_cost_result = build_crowd_cost_result(crowd_cost_file, cfg)
    crowd_buckets = crowd_cost_result["raw_buckets"]
    crowd_reconciliation = {
        "all_passed": True,
        "checks": [],
        "capability_status": "partial_unverified",
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
        "city": profile.display_name,
        "agent_id": cfg["agent_id"],
        "billing_date": cfg["billing_date"],
        "headquarters_fee_rate": str(cfg["headquarters_fee_rate"]),
        "team_group_unit_cost": str(cfg["team_delivery"]["group_unit_cost"]),
        "team_normal_unit_cost": str(cfg["team_delivery"]["normal_unit_cost"]),
        "started_at": utc_now_iso(),
        "capability_note": "Synthetic smoke run; crowd cost extraction is characterized with unverified business rules. Full reconciliation is not complete.",
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
                {"business": FOOD_BUSINESS, **u} for u in food_income["unknown_types"]
            ] + [
                {"business": RETAIL_BUSINESS, **u} for u in retail_income["unknown_types"]
            ],
            "unknown_delivery_types": unknown_delivery,
            "unknown_crowd_cost_rows": crowd_cost_result["unknown_rows"],
        },
        "costs": {
            "crowd": crowd_result_for_summary(crowd_cost_result),
        },
        "capabilities": {
            "crowd_cost": "complete" if crowd_cost_result["status"] == "complete" else "blocked",
            "reconciliation": "partial_unverified",
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
    for business, rows in [(FOOD_BUSINESS, food_rows), (RETAIL_BUSINESS, retail_rows)]:
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
    if data["capabilities"]["crowd_cost"] != "complete":
        warnings += 1
    return {
        "schema_version": "1.0",
        "run_id": run_id,
        "city": {"id": profile.city_id, "name": profile.display_name},
        "pipeline": {
            "profile_id": profile.pipeline_profile.profile_id,
            "version": profile.pipeline_profile.version,
        },
        "storage": {
            "namespace": profile.storage_namespace,
        },
        "rules": {
            "rule_set_id": profile.rule_set_id,
            "status": profile.rule_status,
        },
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
            "unknown_crowd_cost_rows": len(data["unknown"].get("unknown_crowd_cost_rows", [])),
            "rejected_crowd_cost_rows": data["costs"]["crowd"].get("rejected_rows", 0),
            "reconciliation_errors": 0 if recon.get("all_passed") else 1,
            "warnings": warnings,
        },
        "costs": data["costs"],
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
        "pipeline": {
            "profile_id": profile.pipeline_profile.profile_id,
            "version": profile.pipeline_profile.version,
        },
        "storage": {
            "namespace": profile.storage_namespace,
        },
        "rules": {
            "rule_set_id": profile.rule_set_id,
            "status": profile.rule_status,
        },
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


def _reconciliation_context(run_id: str, profile: CityProfile, request: RunRequest, status: str) -> dict:
    return {
        "run_id": run_id,
        "city_id": profile.city_id,
        "status": status,
        "config_sha256": profile.config_sha256,
        "pipeline_profile_id": profile.pipeline_profile.profile_id,
        "pipeline_profile_version": profile.pipeline_profile.version,
        "storage_namespace": profile.storage_namespace,
        "rule_set_id": profile.rule_set_id,
        "rule_status": profile.rule_status,
        "unknown_type_policy": request.unknown_type_policy,
    }


def _attach_reconciliation(summary: dict, reconciliation: dict):
    summary["reconciliation"] = reconciliation
    recon_errors = reconciliation["summary"]["failed"] + reconciliation["summary"]["blocked"]
    summary["validation"]["reconciliation_errors"] = recon_errors
    summary["validation"]["warnings"] += len(reconciliation.get("warnings", []))
    if reconciliation["status"] == "passed":
        if reconciliation["summary"].get("not_implemented", 0):
            summary["capabilities"]["reconciliation"] = "technical_passed_business_unverified"
        else:
            summary["capabilities"]["reconciliation"] = "passed"
    elif reconciliation["status"] == "blocked":
        summary["capabilities"]["reconciliation"] = "blocked"
    elif reconciliation["status"] == "failed":
        summary["capabilities"]["reconciliation"] = "failed"
    else:
        summary["capabilities"]["reconciliation"] = "partial_unverified"


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
        check_id: str | None = None,
        category: str | None = None,
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
        if check_id is not None:
            data["check_id"] = check_id
        if category is not None:
            data["category"] = category
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(data, ensure_ascii=False, separators=(",", ":")) + "\n")
