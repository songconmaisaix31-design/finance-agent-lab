import json
import tempfile
import unittest
from pathlib import Path

from src.manifest import sha256_file
from src.reconciliation_contract import (
    ReconciliationBuilder,
    ReconciliationContractError,
    build_reconciliation_contract,
    build_reconciliation_report,
)


CONFIG_HASH = "a" * 64
INPUT_HASH = "b" * 64


def make_contract_fixture():
    td = tempfile.TemporaryDirectory()
    run_dir = Path(td.name) / "runs" / "guan-test"
    artifact = run_dir / "artifacts" / "guan-synthetic-report.xlsx"
    artifact.parent.mkdir(parents=True)
    artifact.write_text("synthetic artifact", encoding="utf-8")
    artifact_entry = {
        "name": artifact.name,
        "path": "artifacts/guan-synthetic-report.xlsx",
        "media_type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "sha256": sha256_file(str(artifact)),
        "size_bytes": artifact.stat().st_size,
    }
    summary = {
        "schema_version": "1.0",
        "run_id": "guan-test",
        "city": {"id": "guan", "name": "guan"},
        "status": "success",
        "config": {"version": 1, "sha256": CONFIG_HASH, "approval_status": "unverified"},
        "costs": {
            "crowd": {
                "status": "complete",
                "currency": "CNY",
                "total": "100.00",
                "buckets": [
                    {"id": "catering_normal", "name": "catering_normal", "amount": "10.00", "completed_orders": "1", "approval_status": "unverified"},
                    {"id": "catering_group", "name": "catering_group", "amount": "20.00", "completed_orders": "2", "approval_status": "unverified"},
                    {"id": "retail_normal", "name": "retail_normal", "amount": "30.00", "completed_orders": "3", "approval_status": "unverified"},
                    {"id": "retail_group", "name": "retail_group", "amount": "40.00", "completed_orders": "4", "approval_status": "unverified"},
                ],
                "source_rows": 4,
                "accepted_rows": 4,
                "unknown_rows": 0,
                "rejected_rows": 0,
                "rule_approval_status": "unverified",
            }
        },
        "artifacts": [artifact_entry],
    }
    manifest = {
        "schema_version": "1.0",
        "run_id": "guan-test",
        "city_id": "guan",
        "status": "success",
        "config": {"sha256": CONFIG_HASH, "version": 1, "approval_status": "unverified"},
        "artifacts": [dict(artifact_entry)],
    }
    context = {
        "run_id": "guan-test",
        "city_id": "guan",
        "status": "success",
        "config_sha256": CONFIG_HASH,
        "unknown_type_policy": "error",
    }
    input_manifest = {
        "sha256": INPUT_HASH,
        "files": [{"path": "billing_food.xlsx", "size_bytes": 1, "sha256": "c" * 64}],
    }
    return td, run_dir, summary, manifest, context, input_manifest


def build_fixture_contract(summary_mutator=None, manifest_mutator=None, input_after_mutator=None):
    td, run_dir, summary, manifest, context, input_manifest = make_contract_fixture()
    input_after = json.loads(json.dumps(input_manifest))
    if summary_mutator:
        summary_mutator(summary)
    if manifest_mutator:
        manifest_mutator(manifest)
    if input_after_mutator:
        input_after_mutator(input_after)
    result = build_reconciliation_contract(
        summary=summary,
        manifest=manifest,
        run_dir=run_dir,
        request_context=context,
        input_before=input_manifest,
        input_after=input_after,
    )
    return td, result


def check_by_id(result, check_id):
    for check in result["checks"]:
        if check["check_id"] == check_id:
            return check
    raise AssertionError(f"missing check {check_id}")


class TestReconciliationContract(unittest.TestCase):

    def test_balanced_fixture_passes_technical_checks_and_marks_business_gap(self):
        td, result = build_fixture_contract()
        self.addCleanup(td.cleanup)

        self.assertEqual(result["status"], "passed")
        self.assertEqual(result["summary"]["failed"], 0)
        self.assertEqual(result["summary"]["blocked"], 0)
        self.assertEqual(check_by_id(result, "crowd.bucket_total")["difference"], "0.00")
        cross_table = check_by_id(result, "cross_table.business_rules")
        self.assertEqual(cross_table["status"], "not_implemented")
        self.assertEqual(cross_table["approval_status"], "unverified")

    def test_arithmetic_mismatch_fails_with_exact_decimal_difference(self):
        td, result = build_fixture_contract(lambda s: s["costs"]["crowd"].update({"total": "99.00"}))
        self.addCleanup(td.cleanup)

        bucket_total = check_by_id(result, "crowd.bucket_total")
        self.assertEqual(result["status"], "failed")
        self.assertEqual(bucket_total["status"], "fail")
        self.assertEqual(bucket_total["expected"], "99.00")
        self.assertEqual(bucket_total["actual"], "100.00")
        self.assertEqual(bucket_total["difference"], "1.00")
        self.assertEqual(bucket_total["tolerance"], "0.00")
        self.assertEqual(bucket_total["error_code"], "RECON_AMOUNT_MISMATCH")

    def test_negative_arithmetic_difference_is_stable(self):
        td, result = build_fixture_contract(lambda s: s["costs"]["crowd"].update({"total": "101.00"}))
        self.addCleanup(td.cleanup)

        bucket_total = check_by_id(result, "crowd.bucket_total")
        self.assertEqual(bucket_total["difference"], "-1.00")
        self.assertEqual(bucket_total["status"], "fail")

    def test_blocked_upstream_is_not_treated_as_zero(self):
        td, run_dir, summary, manifest, context, input_manifest = make_contract_fixture()
        self.addCleanup(td.cleanup)
        summary["status"] = "blocked"
        manifest["status"] = "blocked"
        context["status"] = "blocked"
        crowd = summary["costs"]["crowd"]
        crowd["status"] = "blocked"
        crowd["source_rows"] = 5
        crowd["accepted_rows"] = 4
        crowd["unknown_rows"] = 1

        result = build_reconciliation_contract(
            summary=summary,
            manifest=manifest,
            run_dir=run_dir,
            request_context=context,
            input_before=input_manifest,
            input_after=input_manifest,
        )

        upstream = check_by_id(result, "crowd.upstream_status")
        self.assertEqual(result["status"], "blocked")
        self.assertEqual(upstream["status"], "blocked")
        self.assertEqual(upstream["error_code"], "RECON_UPSTREAM_BLOCKED")
        self.assertEqual(check_by_id(result, "crowd.row_accounting")["status"], "pass")

    def test_artifact_manifest_mismatch_fails(self):
        td, run_dir, summary, manifest, context, input_manifest = make_contract_fixture()
        self.addCleanup(td.cleanup)
        (run_dir / "artifacts" / "guan-synthetic-report.xlsx").unlink()

        result = build_reconciliation_contract(
            summary=summary,
            manifest=manifest,
            run_dir=run_dir,
            request_context=context,
            input_before=input_manifest,
            input_after=input_manifest,
        )

        artifact_check = check_by_id(result, "artifact.manifest_actual_consistency")
        self.assertEqual(result["status"], "failed")
        self.assertEqual(artifact_check["status"], "fail")
        self.assertEqual(artifact_check["error_code"], "RECON_ARTIFACT_MISSING")

    def test_contract_mismatch_fails(self):
        td, result = build_fixture_contract(manifest_mutator=lambda m: m.update({"run_id": "other-run"}))
        self.addCleanup(td.cleanup)

        run_id = check_by_id(result, "contract.run_id")
        self.assertEqual(result["status"], "failed")
        self.assertEqual(run_id["status"], "fail")
        self.assertEqual(run_id["error_code"], "RECON_RUN_ID_MISMATCH")

    def test_input_manifest_change_fails_without_paths(self):
        td, result = build_fixture_contract(input_after_mutator=lambda m: m.update({"sha256": "d" * 64, "files": []}))
        self.addCleanup(td.cleanup)

        check = check_by_id(result, "input.manifest_unchanged")
        self.assertEqual(result["status"], "failed")
        self.assertEqual(check["status"], "fail")
        self.assertNotIn("\\", json.dumps(result, ensure_ascii=False))

    def test_report_is_safe_json_contract(self):
        td, result = build_fixture_contract()
        self.addCleanup(td.cleanup)

        report = build_reconciliation_report("guan-test", result)
        self.assertEqual(report["run_id"], "guan-test")
        self.assertEqual(report["engine_version"], result["engine_version"])
        self.assertEqual(report["checks"], result["checks"])

    def test_duplicate_check_id_and_invalid_status_are_rejected(self):
        builder = ReconciliationBuilder()
        builder.add("x", "contract", "pass", "blocking", "ok")
        with self.assertRaises(ReconciliationContractError):
            builder.add("x", "contract", "pass", "blocking", "duplicate")
        with self.assertRaises(ReconciliationContractError):
            ReconciliationBuilder().add("y", "contract", "PASS", "blocking", "bad")


if __name__ == "__main__":
    unittest.main()
