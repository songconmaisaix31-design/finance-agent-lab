import hashlib
import importlib
import json
import os
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import jsonschema
import openpyxl


ROOT = Path(__file__).resolve().parents[1]


def sha256_tree(path: Path) -> dict[str, str]:
    hashes = {}
    for file_path in sorted(p for p in path.rglob("*") if p.is_file()):
        rel = file_path.relative_to(path).as_posix()
        h = hashlib.sha256()
        with file_path.open("rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                h.update(chunk)
        hashes[rel] = h.hexdigest()
    return hashes


def write_billing_workbook(path: Path, rows: list[dict]):
    headers = [
        "账单日期", "结算金额", "订单号", "配送方式", "服务包类型", "毛交易额", "净交易额",
        "订单类型", "业务类型", "商户ID", "商户名称", "订单完成时间", "备注", "代理商配送费活动补贴",
    ]
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Sheet0"
    ws.append(headers)
    for row in rows:
        ws.append([row.get(h, "") for h in headers])
    wb.save(path)


def make_smoke_input(base: Path, *, unknown_income=False, unknown_delivery=False) -> Path:
    input_dir = base / "input guan 合成"
    input_dir.mkdir(parents=True)
    service_package = "合成未知服务包" if unknown_income else "代理商E配送"
    delivery_type = "合成配送" if unknown_delivery else "蜂鸟团队"
    write_billing_workbook(input_dir / "billing_food.xlsx", [
        {
            "账单日期": "2026-06-23",
            "结算金额": "10.00",
            "订单号": "SYN-ORDER-0001",
            "配送方式": delivery_type,
            "服务包类型": service_package,
            "毛交易额": "20.00",
            "净交易额": "18.00",
            "订单类型": "正向单",
            "业务类型": "合成餐饮",
            "商户ID": "SYN-MERCHANT-001",
            "商户名称": "合成商户A",
            "订单完成时间": "2026-06-23 12:00:00",
            "备注": "synthetic",
            "代理商配送费活动补贴": "0",
        }
    ])
    write_billing_workbook(input_dir / "billing_retail.xlsx", [])
    return input_dir


def run_cli(args: list[str], cwd: Path = ROOT):
    return subprocess.run(
        [sys.executable, "-m", "src.cli", *args],
        cwd=cwd,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


class TestCliSafety(unittest.TestCase):

    def test_help_has_no_side_effects(self):
        with tempfile.TemporaryDirectory() as td:
            before = set(Path(td).iterdir())
            result = run_cli(["--help"])
            after = set(Path(td).iterdir())
        self.assertEqual(result.returncode, 0)
        self.assertIn("plan", result.stdout)
        self.assertEqual(before, after)

    def test_missing_and_unknown_city_are_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            input_dir = make_smoke_input(base)
            out = base / "out"
            missing = run_cli(["plan", "--input", str(input_dir), "--output", str(out)])
            missing_input = run_cli(["plan", "--city", "guan", "--output", str(out)])
            missing_output = run_cli(["plan", "--city", "guan", "--input", str(input_dir)])
            unknown = run_cli(["plan", "--city", "unknown", "--input", str(input_dir), "--output", str(out)])
        self.assertEqual(missing.returncode, 2)
        self.assertEqual(missing_input.returncode, 2)
        self.assertEqual(missing_output.returncode, 2)
        self.assertEqual(unknown.returncode, 2)
        self.assertIn("UNKNOWN_CITY", unknown.stderr + unknown.stdout)

    def test_run_without_execute_does_not_create_run(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            input_dir = make_smoke_input(base)
            out = base / "out"
            result = run_cli(["run", "--city", "guan", "--input", str(input_dir), "--output", str(out)])
            self.assertEqual(result.returncode, 2)
            self.assertFalse((out / "runs").exists())


class TestPathSafety(unittest.TestCase):

    def test_rejects_missing_or_non_directory_input(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            file_input = base / "not-a-dir.xlsx"
            file_input.write_text("synthetic", encoding="utf-8")
            missing = run_cli(["plan", "--city", "guan", "--input", str(base / "missing"), "--output", str(base / "out")])
            not_dir = run_cli(["plan", "--city", "guan", "--input", str(file_input), "--output", str(base / "out")])
        self.assertEqual(missing.returncode, 4)
        self.assertEqual(not_dir.returncode, 4)

    def test_rejects_unsafe_paths_and_supports_spaces(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            input_dir = make_smoke_input(base)
            same = run_cli(["plan", "--city", "guan", "--input", str(input_dir), "--output", str(input_dir)])
            child = run_cli(["plan", "--city", "guan", "--input", str(input_dir), "--output", str(input_dir / "child")])
            out_parent = base / "out parent"
            nested_input = out_parent / "nested input"
            nested_input.mkdir(parents=True)
            write_billing_workbook(nested_input / "billing_food.xlsx", [])
            write_billing_workbook(nested_input / "billing_retail.xlsx", [])
            nested = run_cli(["plan", "--city", "guan", "--input", str(nested_input), "--output", str(out_parent)])
            ok = run_cli(["plan", "--city", "guan", "--input", str(input_dir), "--output", str(base / "out with spaces")])
        self.assertEqual(same.returncode, 3)
        self.assertEqual(child.returncode, 3)
        self.assertEqual(nested.returncode, 3)
        self.assertEqual(ok.returncode, 0)

    def test_run_id_conflict_is_rejected(self):
        from src.pipeline_service import RunRequest, run_request

        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            input_dir = make_smoke_input(base)
            out = base / "out"
            existing = out / "runs" / "guan-collision"
            existing.mkdir(parents=True)
            request = RunRequest(
                city_id="guan",
                input_path=input_dir,
                output_root=out,
                mode="execute",
                unknown_type_policy="error",
                requested_at="2026-06-25T00:00:00Z",
                run_id="guan-collision",
            )
            with self.assertRaises(Exception) as ctx:
                run_request(request)
        self.assertEqual(getattr(ctx.exception, "exit_code", None), 3)


class TestCityRegistry(unittest.TestCase):

    def test_guan_profile_is_explicit_and_unverified(self):
        from src.city_registry import get_city_profile

        profile = get_city_profile("guan")
        self.assertEqual(profile.city_id, "guan")
        self.assertEqual(profile.display_name, "固安")
        self.assertEqual(profile.schema_version, 1)
        self.assertEqual(profile.rule_approval_status, "unverified")
        self.assertEqual(len(profile.config_sha256), 64)


class TestLegacyEntrypointSafety(unittest.TestCase):

    def test_import_pipeline_has_no_business_io(self):
        module = importlib.import_module("src.pipeline")
        self.assertTrue(hasattr(module, "main"))

    def test_legacy_entrypoint_no_args_is_deprecated(self):
        result = subprocess.run(
            [sys.executable, "-m", "src.pipeline"],
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("python -m src.cli", result.stdout + result.stderr)


class TestSmokeContract(unittest.TestCase):

    def test_synthetic_guan_run_generates_valid_contracts_and_preserves_input(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            input_dir = make_smoke_input(base)
            out = base / "out"
            before = sha256_tree(input_dir)
            result = run_cli(["run", "--city", "guan", "--input", str(input_dir), "--output", str(out), "--execute"])
            after = sha256_tree(input_dir)

            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
            self.assertEqual(before, after)

            runs = list((out / "runs").iterdir())
            self.assertEqual(len(runs), 1)
            run_dir = runs[0]
            summary_path = run_dir / "result-summary.json"
            manifest_path = run_dir / "run-manifest.json"
            unknown_path = run_dir / "unknown-types.json"
            events_path = run_dir / "events.jsonl"
            report_files = list((run_dir / "artifacts").glob("*.xlsx"))

            self.assertTrue(summary_path.exists())
            self.assertTrue(manifest_path.exists())
            self.assertTrue(unknown_path.exists())
            self.assertTrue(events_path.exists())
            self.assertTrue(report_files)

            summary = json.loads(summary_path.read_text(encoding="utf-8"))
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            result_schema = json.loads((ROOT / "schemas" / "run-result.schema.json").read_text(encoding="utf-8"))
            manifest_schema = json.loads((ROOT / "schemas" / "run-manifest.schema.json").read_text(encoding="utf-8"))
            jsonschema.Draft202012Validator(result_schema).validate(summary)
            jsonschema.Draft202012Validator(manifest_schema).validate(manifest)

            self.assertEqual(summary["status"], "success")
            self.assertEqual(summary["city"]["id"], "guan")
            self.assertNotIn("Desktop", json.dumps(summary, ensure_ascii=False))
            self.assertNotIn(str(input_dir), json.dumps(summary, ensure_ascii=False))
            self.assertIsInstance(summary["metrics"]["food_income_total"], str)

            events = [json.loads(line) for line in events_path.read_text(encoding="utf-8").splitlines()]
            self.assertTrue(all(e["run_id"] == summary["run_id"] for e in events))
            self.assertTrue(all("Desktop" not in json.dumps(e, ensure_ascii=False) for e in events))

    def test_read_only_input_is_not_modified(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            input_dir = make_smoke_input(base)
            files = list(input_dir.glob("*.xlsx"))
            for file_path in files:
                os.chmod(file_path, stat.S_IREAD)
            try:
                before = sha256_tree(input_dir)
                result = run_cli(["run", "--city", "guan", "--input", str(input_dir), "--output", str(base / "out"), "--execute"])
                after = sha256_tree(input_dir)
            finally:
                for file_path in files:
                    os.chmod(file_path, stat.S_IWRITE | stat.S_IREAD)
            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
            self.assertEqual(before, after)

    def test_repeated_runs_create_independent_directories(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            input_dir = make_smoke_input(base)
            out = base / "out"
            first = run_cli(["run", "--city", "guan", "--input", str(input_dir), "--output", str(out), "--execute"])
            second = run_cli(["run", "--city", "guan", "--input", str(input_dir), "--output", str(out), "--execute"])
            self.assertEqual(first.returncode, 0)
            self.assertEqual(second.returncode, 0)
            self.assertEqual(len(list((out / "runs").iterdir())), 2)


class TestUnknownTypePolicy(unittest.TestCase):

    def test_unknown_income_defaults_to_blocked(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            input_dir = make_smoke_input(base, unknown_income=True)
            out = base / "out"
            result = run_cli(["run", "--city", "guan", "--input", str(input_dir), "--output", str(out), "--execute"])
            self.assertEqual(result.returncode, 5)
            run_dir = next((out / "runs").iterdir())
            summary = json.loads((run_dir / "result-summary.json").read_text(encoding="utf-8"))
            unknown = json.loads((run_dir / "unknown-types.json").read_text(encoding="utf-8"))
            self.assertEqual(summary["status"], "blocked")
            self.assertEqual(summary["validation"]["unknown_income_types"], 1)
            self.assertEqual(len(unknown["unknown_income_types"]), 1)

    def test_unknown_delivery_defaults_to_blocked(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            input_dir = make_smoke_input(base, unknown_delivery=True)
            out = base / "out"
            result = run_cli(["run", "--city", "guan", "--input", str(input_dir), "--output", str(out), "--execute"])
            self.assertEqual(result.returncode, 5)
            run_dir = next((out / "runs").iterdir())
            summary = json.loads((run_dir / "result-summary.json").read_text(encoding="utf-8"))
            unknown = json.loads((run_dir / "unknown-types.json").read_text(encoding="utf-8"))
            self.assertEqual(summary["status"], "blocked")
            self.assertEqual(summary["validation"]["unknown_delivery_types"], 1)
            self.assertEqual(len(unknown["unknown_delivery_types"]), 1)

    def test_audit_mode_with_unknowns_does_not_declare_success(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            input_dir = make_smoke_input(base, unknown_income=True)
            out = base / "out"
            result = run_cli([
                "run", "--city", "guan", "--input", str(input_dir), "--output", str(out),
                "--execute", "--audit", "--unknown-type-policy", "report_only",
            ])
            self.assertEqual(result.returncode, 5)
            run_dir = next((out / "runs").iterdir())
            summary = json.loads((run_dir / "result-summary.json").read_text(encoding="utf-8"))
            self.assertEqual(summary["status"], "blocked")


if __name__ == "__main__":
    unittest.main()
