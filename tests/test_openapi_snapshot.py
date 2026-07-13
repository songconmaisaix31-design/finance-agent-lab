import json
import unittest
from pathlib import Path

from src.api import app


ROOT = Path(__file__).resolve().parents[1]


class TestOpenApiSnapshot(unittest.TestCase):
    def test_openapi_snapshot_is_current_and_success_schemas_are_explicit(self):
        current = app.openapi()
        snapshot_path = ROOT / "docs" / "n8n-migration" / "openapi.json"
        snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
        self.assertEqual(current, snapshot)

        required_models = {
            "HealthResponse",
            "RunCreatedResponse",
            "RunStatusResponse",
            "StageResultResponse",
            "ArtifactListResponse",
        }
        self.assertTrue(required_models.issubset(set(current["components"]["schemas"])))

        for path, methods in current["paths"].items():
            for method, operation in methods.items():
                if method not in {"get", "post"}:
                    continue
                schema = (
                    operation.get("responses", {})
                    .get("200", {})
                    .get("content", {})
                    .get("application/json", {})
                    .get("schema")
                )
                self.assertTrue(schema, f"{method.upper()} {path} has empty success schema")

        stage_param = current["paths"]["/api/v1/runs/{run_id}/stages/{stage}"]["post"]["parameters"][1]
        self.assertEqual(stage_param["schema"]["$ref"], "#/components/schemas/PipelineStage")
        self.assertEqual(
            set(current["components"]["schemas"]["PipelineStage"]["enum"]),
            {"intake", "normalize", "calculate", "reconcile", "report"},
        )

    def test_openapi_422_description_is_environment_stable(self):
        current = app.openapi()
        post_paths = [
            "/api/v1/runs",
            "/runs",
            "/api/v1/runs/{run_id}/stages/{stage}",
            "/runs/{run_id}/stages/{stage}",
        ]
        descriptions = [
            current["paths"][path]["post"]["responses"]["422"]["description"]
            for path in post_paths
        ]

        self.assertEqual(descriptions, ["Unprocessable Entity"] * len(post_paths))


if __name__ == "__main__":
    unittest.main()
