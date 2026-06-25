from __future__ import annotations

from collections import Counter
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from .manifest import sha256_file
from .result_contract import utc_now_iso


ENGINE_VERSION = "phase-2e.1"

CHECK_STATUSES = {"pass", "fail", "blocked", "not_applicable", "not_implemented"}
RESULT_STATUSES = {"passed", "failed", "blocked", "partial"}
CATEGORIES = {"structural", "arithmetic", "cross_table", "contract"}
SEVERITIES = {"info", "warning", "error", "blocking"}
APPROVAL_STATUSES = {"technical", "unverified", "approved"}
RULE_SOURCES = {"technical_invariant", "existing_code", "city_config", "documented_business_rule", "unknown"}


class ReconciliationContractError(ValueError):
    pass


class ReconciliationBuilder:
    def __init__(self):
        self._checks: list[dict[str, Any]] = []
        self._ids: set[str] = set()

    @property
    def checks(self) -> list[dict[str, Any]]:
        return list(self._checks)

    def add(
        self,
        check_id: str,
        category: str,
        status: str,
        severity: str,
        description: str,
        *,
        expected: str | None = None,
        actual: str | None = None,
        difference: str | None = None,
        tolerance: str | None = None,
        currency: str | None = None,
        source_components: list[str] | None = None,
        approval_status: str = "technical",
        rule_source: str = "technical_invariant",
        error_code: str | None = None,
        safe_message: str | None = None,
    ) -> dict[str, Any]:
        if check_id in self._ids:
            raise ReconciliationContractError(f"Duplicate reconciliation check_id: {check_id}")
        if status not in CHECK_STATUSES:
            raise ReconciliationContractError(f"Invalid reconciliation check status: {status}")
        if category not in CATEGORIES:
            raise ReconciliationContractError(f"Invalid reconciliation category: {category}")
        if severity not in SEVERITIES:
            raise ReconciliationContractError(f"Invalid reconciliation severity: {severity}")
        if approval_status not in APPROVAL_STATUSES:
            raise ReconciliationContractError(f"Invalid approval_status: {approval_status}")
        if rule_source not in RULE_SOURCES:
            raise ReconciliationContractError(f"Invalid rule_source: {rule_source}")

        check = {
            "check_id": check_id,
            "category": category,
            "status": status,
            "severity": severity,
            "description": description,
            "expected": expected,
            "actual": actual,
            "difference": difference,
            "tolerance": tolerance,
            "currency": currency,
            "source_components": source_components or [],
            "approval_status": approval_status,
            "rule_source": rule_source,
            "error_code": error_code,
            "safe_message": safe_message,
        }
        self._ids.add(check_id)
        self._checks.append(check)
        return check


def build_reconciliation_contract(
    *,
    summary: dict[str, Any],
    manifest: dict[str, Any],
    run_dir: Path,
    request_context: dict[str, Any],
    input_before: dict[str, Any],
    input_after: dict[str, Any],
) -> dict[str, Any]:
    builder = ReconciliationBuilder()

    _add_crowd_checks(builder, summary, request_context)
    _add_artifact_checks(builder, summary, manifest, run_dir)
    _add_contract_checks(builder, summary, manifest, request_context)
    _add_input_immutability_check(builder, input_before, input_after)
    _add_cross_table_business_boundary(builder)

    checks = builder.checks
    return {
        "schema_version": "1.0",
        "engine_version": ENGINE_VERSION,
        "status": _rollup_status(checks),
        "summary": _summarize_checks(checks),
        "checks": checks,
        "warnings": _warnings(checks),
        "errors": _errors(checks),
        "created_at": utc_now_iso(),
    }


def build_reconciliation_report(run_id: str, reconciliation: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "run_id": run_id,
        "status": reconciliation["status"],
        "summary": reconciliation["summary"],
        "checks": reconciliation["checks"],
        "warnings": reconciliation["warnings"],
        "errors": reconciliation["errors"],
        "created_at": reconciliation["created_at"],
        "engine_version": reconciliation["engine_version"],
    }


def pipeline_status_from_reconciliation(reconciliation: dict[str, Any], current_status: str) -> tuple[str, int, str | None, str | None]:
    if reconciliation["status"] == "blocked":
        return "blocked", 5, "RECON_UPSTREAM_BLOCKED", "Reconciliation blocked by required upstream status"
    if reconciliation["status"] == "failed":
        return "failed", 6, "RECONCILIATION_FAILED", "Reconciliation failed"
    if current_status == "success":
        return current_status, 0, None, None
    return current_status, 5 if current_status == "blocked" else 6, None, None


def _add_crowd_checks(builder: ReconciliationBuilder, summary: dict[str, Any], request_context: dict[str, Any]):
    crowd = summary.get("costs", {}).get("crowd")
    if not crowd:
        builder.add(
            "crowd.result_present",
            "structural",
            "blocked",
            "blocking",
            "Crowd cost result is required for Phase 2E reconciliation.",
            expected="present",
            actual="missing",
            error_code="RECON_REQUIRED_RESULT_MISSING",
            safe_message="Required crowd cost result is missing.",
        )
        return

    upstream_blocked = crowd.get("status") == "blocked" or crowd.get("unknown_rows", 0) > 0 or crowd.get("rejected_rows", 0) > 0
    if upstream_blocked and request_context.get("unknown_type_policy") == "error":
        builder.add(
            "crowd.upstream_status",
            "structural",
            "blocked",
            "blocking",
            "Crowd cost upstream status must not be treated as zero when unknown or rejected rows exist.",
            expected="complete with zero unknown/rejected rows",
            actual=f"status={crowd.get('status')} unknown={crowd.get('unknown_rows')} rejected={crowd.get('rejected_rows')}",
            error_code="RECON_UPSTREAM_BLOCKED",
            safe_message="Crowd cost reconciliation is blocked by unknown or rejected rows.",
        )
    else:
        builder.add(
            "crowd.upstream_status",
            "structural",
            "pass",
            "blocking",
            "Crowd cost upstream status is available for technical reconciliation.",
            expected="available",
            actual=str(crowd.get("status")),
        )

    buckets = crowd.get("buckets", [])
    try:
        expected_total = _decimal(crowd.get("total"))
        actual_total = sum((_decimal(b.get("amount")) for b in buckets), Decimal("0"))
        difference = actual_total - expected_total
        status = "pass" if difference == Decimal("0") else "fail"
        builder.add(
            "crowd.bucket_total",
            "arithmetic",
            status,
            "blocking",
            "Sum of crowd bucket amounts must exactly equal crowd total.",
            expected=_decimal_text(expected_total),
            actual=_decimal_text(actual_total),
            difference=_decimal_text(difference),
            tolerance="0.00",
            currency=crowd.get("currency", "CNY"),
            source_components=["costs.crowd.total", "costs.crowd.buckets[].amount"],
            error_code=None if status == "pass" else "RECON_AMOUNT_MISMATCH",
            safe_message=None if status == "pass" else "Crowd bucket amount total does not match declared crowd total.",
        )
    except (InvalidOperation, TypeError, ValueError) as exc:
        builder.add(
            "crowd.bucket_total",
            "arithmetic",
            "fail",
            "blocking",
            "Crowd bucket amounts and total must be Decimal-compatible strings.",
            expected="Decimal-compatible money strings",
            actual="invalid",
            tolerance="0.00",
            currency=crowd.get("currency", "CNY"),
            error_code="RECON_AMOUNT_MISMATCH",
            safe_message="Crowd money fields are not valid Decimal-compatible strings.",
        )

    required_row_fields = ["accepted_rows", "rejected_rows", "unknown_rows", "source_rows"]
    if all(field in crowd for field in required_row_fields):
        expected_rows = int(crowd["source_rows"])
        actual_rows = int(crowd["accepted_rows"]) + int(crowd["rejected_rows"]) + int(crowd["unknown_rows"])
        difference = actual_rows - expected_rows
        status = "pass" if difference == 0 else "fail"
        builder.add(
            "crowd.row_accounting",
            "arithmetic",
            status,
            "blocking",
            "Crowd accepted, rejected, and unknown rows must account for all source rows.",
            expected=str(expected_rows),
            actual=str(actual_rows),
            difference=str(difference),
            tolerance="0",
            source_components=required_row_fields,
            error_code=None if status == "pass" else "RECON_ROW_COUNT_MISMATCH",
            safe_message=None if status == "pass" else "Crowd row accounting does not match source rows.",
        )
    else:
        builder.add(
            "crowd.row_accounting",
            "arithmetic",
            "blocked",
            "blocking",
            "Crowd row accounting fields are required.",
            expected="accepted/rejected/unknown/source row counts",
            actual="missing",
            error_code="RECON_REQUIRED_RESULT_MISSING",
            safe_message="Crowd row accounting cannot run because required fields are missing.",
        )


def _add_artifact_checks(builder: ReconciliationBuilder, summary: dict[str, Any], manifest: dict[str, Any], run_dir: Path):
    summary_artifacts = _artifact_index(summary.get("artifacts", []))
    manifest_artifacts = _artifact_index(manifest.get("artifacts", []))
    actual_artifacts = _actual_artifact_index(run_dir)

    if summary_artifacts != manifest_artifacts:
        builder.add(
            "artifact.summary_manifest_consistency",
            "structural",
            "fail",
            "blocking",
            "Result summary and run manifest must declare the same artifacts.",
            expected=_safe_keys(summary_artifacts),
            actual=_safe_keys(manifest_artifacts),
            error_code="RECON_ARTIFACT_UNDECLARED",
            safe_message="Result summary artifact list does not match run manifest.",
        )
    else:
        builder.add(
            "artifact.summary_manifest_consistency",
            "structural",
            "pass",
            "blocking",
            "Result summary and run manifest declare the same artifacts.",
            expected=_safe_keys(summary_artifacts),
            actual=_safe_keys(manifest_artifacts),
        )

    if manifest_artifacts != actual_artifacts:
        error_code = "RECON_ARTIFACT_MISSING" if set(manifest_artifacts) - set(actual_artifacts) else "RECON_ARTIFACT_UNDECLARED"
        builder.add(
            "artifact.manifest_actual_consistency",
            "structural",
            "fail",
            "blocking",
            "Run manifest artifact declarations must match safe files under artifacts/.",
            expected=_safe_keys(manifest_artifacts),
            actual=_safe_keys(actual_artifacts),
            error_code=error_code,
            safe_message="Artifact manifest does not match generated artifact files.",
        )
    else:
        builder.add(
            "artifact.manifest_actual_consistency",
            "structural",
            "pass",
            "blocking",
            "Run manifest artifact declarations match safe files under artifacts/.",
            expected=_safe_keys(manifest_artifacts),
            actual=_safe_keys(actual_artifacts),
        )


def _add_contract_checks(
    builder: ReconciliationBuilder,
    summary: dict[str, Any],
    manifest: dict[str, Any],
    request_context: dict[str, Any],
):
    _add_equality_check(
        builder,
        "contract.run_id",
        "Run id must match request, result summary, and run manifest.",
        expected=request_context.get("run_id"),
        actual=[summary.get("run_id"), manifest.get("run_id")],
        error_code="RECON_RUN_ID_MISMATCH",
    )
    _add_equality_check(
        builder,
        "contract.city_id",
        "City id must match request, result summary, and run manifest.",
        expected=request_context.get("city_id"),
        actual=[summary.get("city", {}).get("id"), manifest.get("city_id")],
        error_code="RECON_RUN_ID_MISMATCH",
    )
    _add_equality_check(
        builder,
        "contract.status",
        "Run status must match result summary and run manifest.",
        expected=request_context.get("status"),
        actual=[summary.get("status"), manifest.get("status")],
        error_code="RECON_STATUS_MISMATCH",
    )
    _add_equality_check(
        builder,
        "contract.config_hash",
        "Config hash must match profile, result summary, and run manifest.",
        expected=request_context.get("config_sha256"),
        actual=[summary.get("config", {}).get("sha256"), manifest.get("config", {}).get("sha256")],
        error_code="RECON_CONFIG_HASH_MISMATCH",
    )
    _add_equality_check(
        builder,
        "contract.schema_version",
        "Result summary and run manifest schema versions must remain 1.0.",
        expected="1.0",
        actual=[summary.get("schema_version"), manifest.get("schema_version")],
        error_code="RECON_STATUS_MISMATCH",
    )


def _add_input_immutability_check(builder: ReconciliationBuilder, input_before: dict[str, Any], input_after: dict[str, Any]):
    before_hash = input_before.get("sha256")
    after_hash = input_after.get("sha256")
    same = input_before.get("files") == input_after.get("files")
    builder.add(
        "input.manifest_unchanged",
        "contract",
        "pass" if same else "fail",
        "blocking",
        "Input manifest must remain unchanged before and after the run.",
        expected=before_hash,
        actual=after_hash,
        error_code=None if same else "RECON_STATUS_MISMATCH",
        safe_message=None if same else "Input files changed during reconciliation boundary.",
    )


def _add_cross_table_business_boundary(builder: ReconciliationBuilder):
    builder.add(
        "cross_table.business_rules",
        "cross_table",
        "not_implemented",
        "warning",
        "Cross-table business reconciliation has no approved rule source in Phase 2E.",
        expected="approved documented business rule",
        actual="missing_business_rule",
        approval_status="unverified",
        rule_source="unknown",
        error_code="RECON_RULE_NOT_IMPLEMENTED",
        safe_message="Cross-table business reconciliation is not implemented until rules are approved.",
    )


def _add_equality_check(
    builder: ReconciliationBuilder,
    check_id: str,
    description: str,
    *,
    expected: Any,
    actual: list[Any],
    error_code: str,
):
    values = [expected, *actual]
    ok = all(value == expected for value in actual)
    builder.add(
        check_id,
        "contract",
        "pass" if ok else "fail",
        "blocking",
        description,
        expected=_safe_value(expected),
        actual=_safe_value(values),
        error_code=None if ok else error_code,
        safe_message=None if ok else "Contract field mismatch detected.",
    )


def _rollup_status(checks: list[dict[str, Any]]) -> str:
    if any(c["status"] == "fail" and c["severity"] == "blocking" for c in checks):
        return "failed"
    if any(c["status"] == "blocked" for c in checks):
        return "blocked"
    if not checks or all(c["status"] in {"not_implemented", "not_applicable"} for c in checks):
        return "partial"
    return "passed"


def _summarize_checks(checks: list[dict[str, Any]]) -> dict[str, int]:
    counts = Counter(c["status"] for c in checks)
    return {
        "passed": counts["pass"],
        "failed": counts["fail"],
        "blocked": counts["blocked"],
        "not_applicable": counts["not_applicable"],
        "not_implemented": counts["not_implemented"],
        "total": len(checks),
    }


def _warnings(checks: list[dict[str, Any]]) -> list[dict[str, str]]:
    return [
        _error_object(check)
        for check in checks
        if check["severity"] == "warning" and check.get("error_code")
    ]


def _errors(checks: list[dict[str, Any]]) -> list[dict[str, str]]:
    return [
        _error_object(check)
        for check in checks
        if check["status"] in {"fail", "blocked"} and check.get("error_code")
    ]


def _error_object(check: dict[str, Any]) -> dict[str, str]:
    return {
        "error_code": check["error_code"],
        "check_id": check["check_id"],
        "stage": "reconciliation",
        "safe_message": check.get("safe_message") or "Reconciliation check requires attention.",
        "expected": _safe_value(check.get("expected")),
        "actual": _safe_value(check.get("actual")),
        "difference": _safe_value(check.get("difference")),
    }


def _artifact_index(items: list[dict[str, Any]]) -> dict[str, tuple[str, int]]:
    return {
        item["path"]: (item.get("sha256"), item.get("size_bytes"))
        for item in items
    }


def _actual_artifact_index(run_dir: Path) -> dict[str, tuple[str, int]]:
    artifacts_dir = run_dir / "artifacts"
    if not artifacts_dir.exists():
        return {}
    index = {}
    for file_path in sorted(p for p in artifacts_dir.rglob("*") if p.is_file()):
        rel = file_path.relative_to(run_dir).as_posix()
        index[rel] = (sha256_file(str(file_path)), file_path.stat().st_size)
    return index


def _decimal(value: Any) -> Decimal:
    return Decimal(str(value))


def _decimal_text(value: Decimal) -> str:
    return str(value)


def _safe_keys(index: dict[str, Any]) -> str:
    return ",".join(sorted(index))


def _safe_value(value: Any) -> str:
    if isinstance(value, list):
        return "|".join(_safe_value(item) for item in value)
    if value is None:
        return ""
    return str(value)
