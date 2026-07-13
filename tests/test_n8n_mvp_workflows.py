import json
import importlib.util
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / "workflows"


def load_workflow(name: str) -> dict:
    return json.loads((WORKFLOWS / name).read_text(encoding="utf-8-sig"))


def node(workflow: dict, name: str) -> dict:
    return next(item for item in workflow["nodes"] if item["name"] == name)


def assignments(workflow: dict, node_name: str) -> dict[str, dict]:
    return {
        item["name"]: item
        for item in node(workflow, node_name)["parameters"]["assignments"]["assignments"]
    }


class TestN8nMvpWorkflows(unittest.TestCase):
    def test_all_workflow_json_files_parse(self):
        for path in sorted(WORKFLOWS.glob("FIN-*.json")):
            with self.subTest(path=path.name):
                workflow = json.loads(path.read_text(encoding="utf-8-sig"))
                node_names = {item["name"] for item in workflow["nodes"]}
                self.assertTrue(node_names)
                for source, outputs in workflow.get("connections", {}).items():
                    self.assertIn(source, node_names)
                    for output in outputs.get("main", []):
                        for connection in output:
                            self.assertIn(connection["node"], node_names)

    def test_fin00_references_existing_subworkflow_ids(self):
        master = load_workflow("FIN-00 Master.json")
        workflow_ids = {load_workflow(path.name)["id"] for path in WORKFLOWS.glob("FIN-*.json")}
        expected = {"fin10intake", "fin20normalize", "fin30calculate", "fin40reconcile", "fin50report", "fin90error"}
        self.assertTrue(expected.issubset(workflow_ids))
        for name in ["FIN-10 Intake", "FIN-20 Normalize", "FIN-30 Calculate", "FIN-40 Reconcile", "FIN-50 Report", "FIN-90 Error"]:
            wf = node(master, name)["parameters"]["workflowId"]["value"]
            self.assertIn(wf, workflow_ids)

    def test_run_parameters_defaults_are_complete_and_container_paths(self):
        master = load_workflow("FIN-00 Master.json")
        params = assignments(master, "Run Parameters")
        expected = {
            "city_id": "guan",
            "input_path": "/finance-data/guan/incoming",
            "output_root": "/finance-data/guan",
            "mode": "execute",
            "unknown_type_policy": "error",
        }
        for key, value in expected.items():
            self.assertEqual(params[key]["value"], value)
        self.assertNotIn("D:\\", json.dumps(params, ensure_ascii=False))

    def test_run_summary_mapping_has_mvp_fields_and_null_fallbacks(self):
        master = load_workflow("FIN-00 Master.json")
        summary = assignments(master, "Run Summary")
        expected = {
            "run_id", "status", "city_id", "row_count", "food_income_total",
            "retail_income_total", "food_hq_fee", "retail_hq_fee",
            "food_team_delivery_cost", "retail_team_delivery_cost", "crowd_total",
            "reconciliation_status", "warnings", "errors", "report_path",
            "duration_seconds",
        }
        self.assertEqual(set(summary), expected)
        for key in expected - {"duration_seconds"}:
            self.assertIn("null", str(summary[key]["value"]))
        self.assertIn("duration_ms", summary["duration_seconds"]["value"])

    def test_fin90_error_summary_mapping_is_fixed_and_safe(self):
        error = load_workflow("FIN-90 Error.json")
        summary = assignments(error, "Error Summary")
        self.assertEqual(
            set(summary),
            {"run_id", "status", "failed_stage", "error_code", "message", "retryable", "artifact_path"},
        )
        self.assertEqual(summary["status"]["value"], "failed")
        self.assertIn("replace", summary["message"]["value"])
        self.assertIn("retryable", summary["retryable"]["value"])
        self.assertIn("null", summary["artifact_path"]["value"])

    def test_n8n_service_does_not_mount_finance_data_directly(self):
        compose = (ROOT / "infra" / "n8n" / "compose.yaml").read_text(encoding="utf-8")
        n8n_section = compose.split("  finance-pipeline-api:", 1)[0]
        self.assertNotIn(":/finance-data", n8n_section)
        self.assertIn("../../workflows:/workflows:ro", n8n_section)

    def test_sanitize_removes_credentials_and_sensitive_headers(self):
        script = ROOT / "infra" / "n8n" / "sanitize_n8n_export.py"
        spec = importlib.util.spec_from_file_location("sanitize_n8n_export", script)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        workflow = {
            "name": "Sensitive",
            "credentials": {"http": {"id": "1"}},
            "pinData": {"node": []},
            "nodes": [
                {
                    "name": "HTTP",
                    "type": "n8n-nodes-base.httpRequest",
                    "credentials": {"httpHeaderAuth": {"id": "2"}},
                    "parameters": {
                        "sendHeaders": True,
                        "headerParameters": {
                            "parameters": [
                                {"name": "Authorization", "value": "Bearer abc.def"},
                                {"name": "X-API-Key", "value": "secret-value"},
                                {"name": "X-Trace", "value": "ok"},
                            ]
                        },
                        "url": "={{$env.SECRET_TOKEN}}",
                    },
                }
            ],
        }
        sanitized = module.sanitize_workflow(workflow)
        text = json.dumps(sanitized, ensure_ascii=False)
        self.assertNotIn("secret-value", text)
        self.assertNotIn("abc.def", text)
        self.assertNotIn("$env.SECRET_TOKEN", text)
        self.assertNotIn("credentials", sanitized)
        self.assertNotIn("credentials", sanitized["nodes"][0])
        headers = sanitized["nodes"][0]["parameters"]["headerParameters"]["parameters"]
        self.assertEqual(headers[0]["value"], "REDACTED")
        self.assertEqual(headers[1]["value"], "REDACTED")
        self.assertEqual(headers[2]["value"], "ok")


if __name__ == "__main__":
    unittest.main()
