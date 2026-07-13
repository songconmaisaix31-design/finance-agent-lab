import json
import os
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

from tests.test_phase2c_safe_entrypoint import make_smoke_input


class TestPhase3StagePipeline(unittest.TestCase):
    def test_adapter_reconcile_does_not_call_full_run_request_and_report_outputs_summary(self):
        from src.pipeline_adapter import AdapterRunRequest, create_run, execute_stage

        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            os.environ["FINANCE_PIPELINE_STATE_DIR"] = str(base / "api-state")
            input_dir = make_smoke_input(base)
            run = create_run(AdapterRunRequest("guan", input_dir, base / "out", run_id="guan-phase3-isolated"))

            with mock.patch("src.pipeline_adapter.run_request", side_effect=AssertionError("run_request must not be called"), create=True):
                for stage in ["intake", "normalize", "calculate", "reconcile", "report"]:
                    result = execute_stage(run["run_id"], stage)
                    self.assertIn(result["status"], {"success", "warning"})

            run_dir = base / "out" / "runs" / "guan-phase3-isolated"
            self.assertTrue((run_dir / "input-manifest.json").exists())
            self.assertTrue((run_dir / "normalized-data" / "normalized.sqlite").exists())
            self.assertTrue((run_dir / "calculation-result.json").exists())
            self.assertTrue((run_dir / "quality-gate-result.json").exists())
            self.assertTrue((run_dir / "result-summary.json").exists())

            calc = json.loads((run_dir / "calculation-result.json").read_text(encoding="utf-8"))
            self.assertEqual(calc["producer_stage"], "calculate")
            self.assertEqual(calc["pipeline_data"]["food_income"]["total_settlement"], "10.00")

    def test_run_index_rebuild_uses_orchestration_run_json_truth_source(self):
        from src.pipeline_adapter import AdapterRunRequest, create_run, execute_stage, get_run, rebuild_run_index

        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            finance_root = base / "finance"
            os.environ["FINANCE_DATA_ROOT"] = str(finance_root)
            os.environ["FINANCE_PIPELINE_STATE_DIR"] = str(finance_root / ".pipeline-state")
            input_dir = make_smoke_input(base)
            run = create_run(AdapterRunRequest("guan", input_dir, finance_root / "guan", run_id="guan-index-rebuild"))
            execute_stage(run["run_id"], "intake")
            for state_file in (finance_root / ".pipeline-state").glob("*.json"):
                state_file.unlink()

            rebuilt = rebuild_run_index()
            loaded = get_run("guan-index-rebuild")

        self.assertEqual(rebuilt["rebuilt_count"], 1)
        self.assertEqual(loaded["stages"]["intake"]["status"], "success")

    def test_same_stage_concurrent_request_returns_already_running(self):
        from src.pipeline_adapter import AdapterRunRequest, StageAlreadyRunningError, create_run, execute_stage

        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            os.environ["FINANCE_PIPELINE_STATE_DIR"] = str(base / "api-state")
            input_dir = make_smoke_input(base)
            run = create_run(AdapterRunRequest("guan", input_dir, base / "out", run_id="guan-concurrent"))
            original_sleep = time.sleep
            gate = threading.Event()
            release = threading.Event()
            outcomes = []

            def slow_stage(context):
                gate.set()
                release.wait(5)
                from src.pipeline_service import run_intake_stage
                return run_intake_stage(context)

            def first():
                with mock.patch("src.pipeline_adapter.run_intake_stage", side_effect=slow_stage):
                    outcomes.append(execute_stage(run["run_id"], "intake")["status"])

            thread = threading.Thread(target=first)
            thread.start()
            self.assertTrue(gate.wait(5))
            try:
                with self.assertRaises(StageAlreadyRunningError):
                    execute_stage(run["run_id"], "intake")
            finally:
                release.set()
                thread.join(5)

        self.assertEqual(outcomes, ["success"])


if __name__ == "__main__":
    unittest.main()
