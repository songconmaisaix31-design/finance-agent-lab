import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from src.city_registry import CITY_ORDER, get_city_profile, list_city_profiles, validate_city_profiles
from src.pipeline_service import RunRequest, run_request
from src.storage import (
    STORAGE_NAMESPACES,
    StorageNamespaceMismatchError,
    assert_path_in_city_namespace,
    initialize_storage,
    resolve_city_storage,
    validate_storage,
)


ROOT = Path(__file__).resolve().parents[1]


def run_cli(args: list[str]):
    return subprocess.run(
        [sys.executable, "-m", "src.cli", *args],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


class TestSixCityRegistry(unittest.TestCase):

    def test_all_six_city_profiles_are_registered_with_one_pipeline(self):
        profiles = list_city_profiles()
        self.assertEqual([profile.city_id for profile in profiles], list(CITY_ORDER))
        self.assertEqual(len({profile.city_id for profile in profiles}), 6)
        self.assertEqual({profile.pipeline_profile.profile_id for profile in profiles}, {"standard-finance-pipeline"})
        self.assertEqual({profile.pipeline_profile.version for profile in profiles}, {1})
        self.assertEqual([profile.storage_namespace for profile in profiles], list(CITY_ORDER))
        self.assertEqual(validate_city_profiles(), [])

    def test_city_display_names_and_rule_status_are_explicit(self):
        expected_names = {
            "guan": "固安",
            "xianghe": "香河",
            "yicheng": "驿城",
            "yongcheng": "永城",
            "queshan": "确山",
            "biyang": "泌阳",
        }
        profiles = {profile.city_id: profile for profile in list_city_profiles()}
        for city_id, display_name in expected_names.items():
            self.assertEqual(profiles[city_id].display_name, display_name)
        self.assertEqual(profiles["guan"].rule_status, "unverified")
        for city_id in CITY_ORDER:
            if city_id != "guan":
                self.assertEqual(profiles[city_id].rule_status, "missing")
                self.assertEqual(profiles[city_id].rule_set_id, "pending")
                self.assertFalse(profiles[city_id].config)

    def test_unknown_city_is_rejected(self):
        with self.assertRaises(Exception) as ctx:
            get_city_profile("not-a-city")
        self.assertEqual(getattr(ctx.exception, "error_code", None), "UNKNOWN_CITY")

    def test_missing_rule_city_formal_run_is_blocked_before_required_inputs(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            input_dir = base / "xianghe" / "incoming"
            input_dir.mkdir(parents=True)
            output_root = base / "xianghe"
            request = RunRequest(
                city_id="xianghe",
                input_path=input_dir,
                output_root=output_root,
                mode="execute",
                unknown_type_policy="error",
                requested_at="2026-06-25T00:00:00Z",
                run_id="xianghe-blocked",
            )
            with self.assertRaises(Exception) as ctx:
                run_request(request)
        self.assertEqual(getattr(ctx.exception, "error_code", None), "CITY_RULE_SET_MISSING")
        self.assertEqual(getattr(ctx.exception, "exit_code", None), 5)


class TestCityStorageIsolation(unittest.TestCase):

    def test_storage_init_creates_all_city_namespaces_and_catalog(self):
        with tempfile.TemporaryDirectory(prefix="finance data root ") as td:
            root = Path(td)
            first = initialize_storage(root)
            second = initialize_storage(root)

            self.assertTrue(first["valid"], first)
            self.assertTrue(second["valid"], second)
            catalog = json.loads((root / "catalog" / "cities.json").read_text(encoding="utf-8"))
            self.assertEqual([city["city_id"] for city in catalog["cities"]], list(CITY_ORDER))
            self.assertFalse(any("amount" in json.dumps(city, ensure_ascii=False).lower() for city in catalog["cities"]))
            for city_id in CITY_ORDER:
                storage = resolve_city_storage(city_id, root)
                self.assertEqual(storage.city_root, root.resolve() / city_id)
                for namespace in STORAGE_NAMESPACES:
                    self.assertTrue(getattr(storage, namespace).is_dir())
                marker = json.loads((storage.city_root / ".finance-data-namespace.json").read_text(encoding="utf-8"))
                self.assertEqual(marker["city_id"], city_id)
                self.assertFalse(marker["contains_business_data"])

    def test_storage_validation_reports_missing_catalog(self):
        with tempfile.TemporaryDirectory() as td:
            result = validate_storage(Path(td))
        self.assertFalse(result["valid"])
        self.assertTrue(any(issue["error_code"] == "CITY_CATALOG_MISSING" for issue in result["issues"]))

    def test_cross_city_path_is_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            initialize_storage(root)
            xianghe_incoming = root / "xianghe" / "incoming"
            with self.assertRaises(StorageNamespaceMismatchError):
                assert_path_in_city_namespace(xianghe_incoming, "guan", root, "incoming")

    def test_namespace_escape_is_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            initialize_storage(root)
            with self.assertRaises(Exception) as ctx:
                assert_path_in_city_namespace(root / "guan" / "incoming" / ".." / ".." / "xianghe", "guan", root, "incoming")
        self.assertIn(getattr(ctx.exception, "error_code", ""), {"CITY_STORAGE_NAMESPACE_MISMATCH", "CITY_STORAGE_ESCAPE"})


class TestSixCityCli(unittest.TestCase):

    def test_cities_cli_outputs_catalog_safe_summary(self):
        result = run_cli(["cities", "list"])
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        data = json.loads(result.stdout)
        self.assertEqual([city["city_id"] for city in data["cities"]], list(CITY_ORDER))
        self.assertNotIn("D:\\", result.stdout)

    def test_cities_validate_and_show(self):
        validate = run_cli(["cities", "validate"])
        show = run_cli(["cities", "show", "--city", "guan"])
        self.assertEqual(validate.returncode, 0, validate.stderr + validate.stdout)
        self.assertEqual(show.returncode, 0, show.stderr + show.stdout)
        data = json.loads(show.stdout)
        self.assertEqual(data["pipeline_profile"]["profile_id"], "standard-finance-pipeline")
        self.assertEqual(data["storage_namespace"], "guan")

    def test_storage_cli_init_and_validate(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            init = run_cli(["storage", "init", "--root", str(root)])
            validate = run_cli(["storage", "validate", "--root", str(root)])
        self.assertEqual(init.returncode, 0, init.stderr + init.stdout)
        self.assertEqual(validate.returncode, 0, validate.stderr + validate.stdout)


if __name__ == "__main__":
    unittest.main()
