from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .config import load_city_config, load_yaml
from .manifest import sha256_file


class CityRegistryError(ValueError):
    error_code = "UNKNOWN_CITY"


class CityProfileInvalidError(CityRegistryError):
    error_code = "CITY_PROFILE_INVALID"


class CityRuleSetMissingError(CityRegistryError):
    error_code = "CITY_RULE_SET_MISSING"


@dataclass(frozen=True)
class PipelineProfile:
    profile_id: str
    version: int
    stages: tuple[str, ...]
    path: Path
    sha256: str


@dataclass(frozen=True)
class CityProfile:
    city_id: str
    display_name: str
    schema_version: int
    rule_approval_status: str
    config_path: Path
    config_sha256: str
    config: dict[str, Any]
    city_profile_path: Path
    pipeline_profile: PipelineProfile
    storage_namespace: str
    rule_set_id: str
    rule_status: str
    rule_version: int | None
    capabilities: dict[str, str]
    production_ready: bool


REPO_ROOT = Path(__file__).resolve().parents[1]
CITY_PROFILE_DIR = REPO_ROOT / "config" / "city_profiles"
PIPELINE_PROFILE_DIR = REPO_ROOT / "config" / "pipeline_profiles"
CITY_CONFIGS = {
    "guan": REPO_ROOT / "config" / "cities" / "guan.yaml",
}
CITY_ORDER = ("guan", "xianghe", "yicheng", "yongcheng", "queshan", "biyang")


def list_city_ids() -> tuple[str, ...]:
    return CITY_ORDER


def list_city_profiles() -> list[CityProfile]:
    return [get_city_profile(city_id) for city_id in CITY_ORDER]


def get_city_profile(city_id: str) -> CityProfile:
    if not city_id or city_id not in CITY_ORDER:
        raise CityRegistryError(f"Unknown city_id: {city_id}")

    profile_path = CITY_PROFILE_DIR / f"{city_id}.yaml"
    if not profile_path.exists():
        raise CityProfileInvalidError(f"City profile missing for city_id: {city_id}")

    raw = load_yaml(str(profile_path)) or {}
    _validate_city_profile_shape(city_id, raw)
    pipeline = _load_pipeline_profile(raw["pipeline"]["profile_id"], raw["pipeline"]["version"])

    rule_status = str(raw["rules"]["status"])
    config_path = CITY_CONFIGS.get(city_id, profile_path)
    if city_id == "guan":
        config = load_city_config("guan")
        config_sha256 = sha256_file(str(config_path))
        rule_approval_status = str(config.get("rule_approval_status", rule_status))
        schema_version = int(config.get("schema_version", raw["schema_version"]))
    else:
        config = {}
        config_sha256 = sha256_file(str(profile_path))
        rule_approval_status = rule_status
        schema_version = int(raw["schema_version"])

    return CityProfile(
        city_id=str(raw["city"]["id"]),
        display_name=str(raw["city"]["display_name"]),
        schema_version=schema_version,
        rule_approval_status=rule_approval_status,
        config_path=config_path,
        config_sha256=config_sha256,
        config=config,
        city_profile_path=profile_path,
        pipeline_profile=pipeline,
        storage_namespace=str(raw["storage"]["namespace"]),
        rule_set_id=str(raw["rules"]["rule_set_id"]),
        rule_status=rule_status,
        rule_version=raw["rules"].get("version"),
        capabilities={str(k): str(v) for k, v in raw["capabilities"].items()},
        production_ready=bool(raw.get("approval_summary", {}).get("production_ready", False)),
    )


def validate_city_profiles() -> list[dict[str, Any]]:
    profiles = list_city_profiles()
    seen = set()
    issues = []
    pipeline_keys = {(p.pipeline_profile.profile_id, p.pipeline_profile.version) for p in profiles}
    for profile in profiles:
        if profile.city_id in seen:
            issues.append({"city_id": profile.city_id, "error_code": "CITY_PROFILE_DUPLICATE"})
        seen.add(profile.city_id)
        if profile.city_id != profile.storage_namespace:
            issues.append({"city_id": profile.city_id, "error_code": "CITY_STORAGE_NAMESPACE_MISMATCH"})
        if profile.rule_status == "missing" and profile.city_id == "guan":
            issues.append({"city_id": profile.city_id, "error_code": "CITY_RULE_SET_MISSING"})
    if len(pipeline_keys) != 1:
        issues.append({"city_id": "*", "error_code": "CITY_PIPELINE_PROFILE_MISMATCH"})
    return issues


def city_catalog_items() -> list[dict[str, Any]]:
    items = []
    for profile in list_city_profiles():
        items.append({
            "city_id": profile.city_id,
            "display_name": profile.display_name,
            "pipeline_profile": {
                "profile_id": profile.pipeline_profile.profile_id,
                "version": profile.pipeline_profile.version,
            },
            "rule_status": profile.rule_status,
            "storage_namespace": profile.storage_namespace,
            "capabilities": profile.capabilities,
            "production_ready": profile.production_ready,
            "latest_successful_run_id": None,
        })
    return items


def _load_pipeline_profile(profile_id: str, version: int) -> PipelineProfile:
    path = PIPELINE_PROFILE_DIR / f"{profile_id}.yaml"
    if not path.exists():
        raise CityProfileInvalidError(f"Pipeline profile missing: {profile_id}")
    raw = load_yaml(str(path)) or {}
    if raw.get("profile_id") != profile_id or int(raw.get("version", -1)) != int(version):
        raise CityProfileInvalidError(f"Pipeline profile mismatch: {profile_id}")
    stages = raw.get("stages")
    if not isinstance(stages, list) or not all(isinstance(stage, str) and stage for stage in stages):
        raise CityProfileInvalidError(f"Pipeline profile stages invalid: {profile_id}")
    return PipelineProfile(
        profile_id=profile_id,
        version=int(version),
        stages=tuple(stages),
        path=path,
        sha256=sha256_file(str(path)),
    )


def _validate_city_profile_shape(expected_city_id: str, raw: dict[str, Any]):
    required_sections = ["schema_version", "city", "pipeline", "storage", "rules", "capabilities", "approval_summary"]
    missing = [key for key in required_sections if key not in raw]
    if missing:
        raise CityProfileInvalidError(f"City profile missing sections: {missing}")

    city = raw["city"]
    storage = raw["storage"]
    rules = raw["rules"]
    pipeline = raw["pipeline"]
    if city.get("id") != expected_city_id:
        raise CityProfileInvalidError(f"City profile id mismatch: {expected_city_id}")
    if storage.get("namespace") != expected_city_id:
        raise CityProfileInvalidError(f"City storage namespace mismatch: {expected_city_id}")
    if storage.get("root_env") != "FINANCE_DATA_ROOT":
        raise CityProfileInvalidError(f"City storage root_env invalid: {expected_city_id}")
    if pipeline.get("profile_id") != "standard-finance-pipeline":
        raise CityProfileInvalidError(f"City pipeline profile invalid: {expected_city_id}")
    if rules.get("status") not in {"unverified", "missing", "approved"}:
        raise CityProfileInvalidError(f"City rule status invalid: {expected_city_id}")
