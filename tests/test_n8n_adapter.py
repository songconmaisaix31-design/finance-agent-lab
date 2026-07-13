import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import jsonschema
from fastapi.testclient import TestClient

from tests.test_phase2c_safe_entrypoint import make_smoke_input


ROOT = Path(__file__).resolve().parents[1]


def run_cli(args: list[str], env: dict[str, str]):
    return subprocess.run(
        [sys.executable, "-m", "src.cli", *args],
        cwd=ROOT,
        env={**os.environ, **env},
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


class TestN8nAdapterContracts(unittest.TestCase):

    def test_stage_result_schema_accepts_adapter_output(self):
        from src.pipeline_adapter import AdapterRunRequest, create_run, execute_stage

        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            os.environ["FINANCE_PIPELINE_STATE_DIR"] = str(base / "api-state")
            input_dir = make_smoke_input(base)
            output = base / "out"
            run = create_run(AdapterRunRequest("guan", input_dir, output, run_id="guan-contract"))
            result = execute_stage(run["run_id"], "intake")
            schema = json.loads((ROOT / "schemas" / "stage-result.schema.json").read_text(encoding="utf-8"))
            jsonschema.Draft202012Validator(schema).validate(result)

        self.assertEqual(result["status"], "success")
        self.assertEqual(result["stage"], "intake")

    def test_stage_order_rejects_out_of_sequence_execution(self):
        from src.pipeline_adapter import AdapterRunRequest, create_run, execute_stage

        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            os.environ["FINANCE_PIPELINE_STATE_DIR"] = str(base / "api-state")
            input_dir = make_smoke_input(base)
            run = create_run(AdapterRunRequest("guan", input_dir, base / "out", run_id="guan-order"))
            result = execute_stage(run["run_id"], "report")

        self.assertEqual(result["status"], "rejected")
        self.assertEqual(result["error"]["code"], "STAGE_DEPENDENCY_NOT_SATISFIED")

    def test_repeated_stage_call_is_idempotent(self):
        from src.pipeline_adapter import AdapterRunRequest, create_run, execute_stage

        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            os.environ["FINANCE_PIPELINE_STATE_DIR"] = str(base / "api-state")
            input_dir = make_smoke_input(base)
            run = create_run(AdapterRunRequest("guan", input_dir, base / "out", run_id="guan-idempotent"))
            for stage in ["intake", "normalize", "calculate", "reconcile", "report"]:
                first = execute_stage(run["run_id"], stage)
                second = execute_stage(run["run_id"], stage)
                self.assertEqual(first, second)
            run_dir = base / "out" / "runs" / "guan-idempotent"
            self.assertEqual(len(list((base / "out" / "runs").iterdir())), 1)
            self.assertTrue((run_dir / "result-summary.json").exists())

    def test_state_can_be_reloaded_from_run_directory_after_index_loss(self):
        from src.pipeline_adapter import AdapterRunRequest, create_run, execute_stage, get_run

        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            finance_root = base / "finance-data"
            os.environ["FINANCE_DATA_ROOT"] = str(finance_root)
            os.environ["FINANCE_PIPELINE_STATE_DIR"] = str(finance_root / ".pipeline-state")
            input_dir = make_smoke_input(base)
            output = finance_root / "guan"
            run = create_run(AdapterRunRequest("guan", input_dir, output, run_id="guan-reload"))
            execute_stage(run["run_id"], "intake")
            for state_file in (finance_root / ".pipeline-state").glob("*.json"):
                state_file.unlink()
            loaded = get_run("guan-reload")

        self.assertEqual(loaded["run_id"], "guan-reload")
        self.assertEqual(loaded["stages"]["intake"]["status"], "success")

    def test_allowlist_rejects_paths_outside_configured_roots(self):
        from src.pipeline_adapter import AdapterRunRequest, StageContractError, create_run

        old = os.environ.get("FINANCE_PIPELINE_ALLOW_ROOTS")
        try:
            with tempfile.TemporaryDirectory() as td:
                base = Path(td)
                allowed = base / "allowed"
                blocked = base / "blocked"
                allowed.mkdir()
                blocked.mkdir()
                os.environ["FINANCE_PIPELINE_ALLOW_ROOTS"] = str(allowed)
                os.environ["FINANCE_PIPELINE_STATE_DIR"] = str(base / "api-state")
                with self.assertRaises(StageContractError):
                    create_run(AdapterRunRequest("guan", blocked, allowed / "out", run_id="guan-allowlist"))
        finally:
            if old is None:
                os.environ.pop("FINANCE_PIPELINE_ALLOW_ROOTS", None)
            else:
                os.environ["FINANCE_PIPELINE_ALLOW_ROOTS"] = old

    def test_cross_city_and_directory_escape_rejections_surface_as_stage_results(self):
        from src.pipeline_adapter import AdapterRunRequest, create_run, execute_stage

        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            os.environ["FINANCE_PIPELINE_STATE_DIR"] = str(base / "api-state")
            input_dir = make_smoke_input(base)
            cross = create_run(AdapterRunRequest("guan", input_dir, base / "xianghe", run_id="guan-cross-city"))
            cross_result = execute_stage(cross["run_id"], "intake")
            child = create_run(AdapterRunRequest("guan", input_dir, input_dir / "child", run_id="guan-dir-escape"))
            child_result = execute_stage(child["run_id"], "intake")

        self.assertEqual(cross_result["status"], "failed")
        self.assertIn("CITY_STORAGE_NAMESPACE_MISMATCH", cross_result["error"]["code"])
        self.assertEqual(child_result["status"], "failed")
        self.assertEqual(child_result["error"]["code"], "PATH_SAFETY_REJECTED")
    def test_cli_run_outputs_json_and_preserves_financial_metrics(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            env = {"FINANCE_PIPELINE_STATE_DIR": str(base / "api-state")}
            input_dir = make_smoke_input(base)
            output = base / "out"
            result = run_cli([
                "run", "--city", "guan", "--input", str(input_dir), "--output", str(output),
                "--execute", "--run-id", "guan-cli-json",
            ], env)

            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
            payload = json.loads(result.stdout)
            self.assertEqual(payload["status"], "success")
            summary = json.loads((output / "runs" / "guan-cli-json" / "result-summary.json").read_text(encoding="utf-8"))
            self.assertEqual(summary["metrics"]["food_income_total"], "10.00")
            self.assertEqual(summary["metrics"]["food_hq_fee"], "0.2000")
            self.assertEqual(summary["metrics"]["food_team_delivery_cost"], "4.60")
            self.assertEqual(summary["costs"]["crowd"]["total"], "100.00")

    def test_cli_report_stage_runs_to_artifacts(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            env = {"FINANCE_PIPELINE_STATE_DIR": str(base / "api-state")}
            input_dir = make_smoke_input(base)
            result = run_cli([
                "report", "--city", "guan", "--input", str(input_dir), "--output", str(base / "out"),
                "--run-id", "guan-stage-cli",
            ], env)
            self.assertNotEqual(result.returncode, 0)

            result = run_cli([
                "report", "--city", "guan", "--input", str(input_dir), "--output", str(base / "out2"),
            ], env)
            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
            payload = json.loads(result.stdout)
            self.assertEqual(payload["stage"], "report")
            self.assertGreaterEqual(int(payload["metrics"]["artifact_count"]), 1)


class TestFastApiAdapter(unittest.TestCase):

    def test_api_health_and_full_stage_smoke(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            os.environ["FINANCE_PIPELINE_STATE_DIR"] = str(base / "api-state")
            from src.api import app

            client = TestClient(app)
            input_dir = make_smoke_input(base)
            output = base / "out"

            health = client.get("/health")
            self.assertEqual(health.status_code, 200)
            self.assertEqual(health.json()["status"], "ok")
            self.assertIn("HealthResponse", json.dumps(client.get("/openapi.json").json()))

            created = client.post("/runs", json={
                "city_id": "guan",
                "input_path": str(input_dir),
                "output_root": str(output),
                "run_id": "guan-api-smoke",
            })
            self.assertEqual(created.status_code, 200, created.text)

            final = None
            for stage in ["intake", "normalize", "calculate", "reconcile", "report"]:
                response = client.post(f"/runs/guan-api-smoke/stages/{stage}")
                self.assertEqual(response.status_code, 200, response.text)
                final = response.json()

            self.assertEqual(final["stage"], "report")
            self.assertEqual(final["status"], "success")

            artifacts = client.get("/runs/guan-api-smoke/artifacts")
            self.assertEqual(artifacts.status_code, 200)
            self.assertTrue(artifacts.json()["artifacts"])

            missing = client.get("/runs/no-such-run")
            self.assertEqual(missing.status_code, 404)
            self.assertEqual(missing.json()["error_code"], "STAGE_CONTRACT_INVALID")

            bad_stage = client.post("/runs/guan-api-smoke/stages/not-a-stage")
            self.assertEqual(bad_stage.status_code, 422)

    def test_api_missing_file_error_is_safe_stage_result_for_error_workflow(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            os.environ["FINANCE_PIPELINE_STATE_DIR"] = str(base / "api-state")
            from src.api import app

            client = TestClient(app)
            input_dir = base / "input"
            input_dir.mkdir()
            output = base / "out"
            created = client.post("/runs", json={
                "city_id": "guan",
                "input_path": str(input_dir),
                "output_root": str(output),
                "run_id": "guan-api-error",
            })
            self.assertEqual(created.status_code, 200)
            response = client.post("/runs/guan-api-error/stages/intake")
            self.assertEqual(response.status_code, 200)
            payload = response.json()
            self.assertEqual(payload["run_id"], "guan-api-error")
            self.assertEqual(payload["stage"], "intake")
            self.assertEqual(payload["status"], "failed")
            self.assertEqual(payload["error"]["code"], "INPUT_VALIDATION_FAILED")
            self.assertNotIn(str(input_dir), payload["error"]["message"])


if __name__ == "__main__":
    unittest.main()
