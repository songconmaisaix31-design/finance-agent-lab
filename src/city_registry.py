from dataclasses import dataclass
from pathlib import Path

from .config import load_city_config
from .manifest import sha256_file


class CityRegistryError(ValueError):
    error_code = "UNKNOWN_CITY"


@dataclass(frozen=True)
class CityProfile:
    city_id: str
    display_name: str
    schema_version: int
    rule_approval_status: str
    config_path: Path
    config_sha256: str
    config: dict


REPO_ROOT = Path(__file__).resolve().parents[1]
CITY_CONFIGS = {
    "guan": REPO_ROOT / "config" / "cities" / "guan.yaml",
}


def get_city_profile(city_id: str) -> CityProfile:
    if not city_id or city_id not in CITY_CONFIGS:
        raise CityRegistryError(f"Unknown city_id: {city_id}")

    config_path = CITY_CONFIGS[city_id]
    if not config_path.exists():
        raise CityRegistryError(f"City config missing for city_id: {city_id}")

    config = load_city_config(city_id)
    required = ["city_id", "display_name", "schema_version", "rule_approval_status"]
    missing = [key for key in required if key not in config]
    if missing:
        raise CityRegistryError(f"City config missing metadata: {missing}")

    return CityProfile(
        city_id=str(config["city_id"]),
        display_name=str(config["display_name"]),
        schema_version=int(config["schema_version"]),
        rule_approval_status=str(config["rule_approval_status"]),
        config_path=config_path,
        config_sha256=sha256_file(str(config_path)),
        config=config,
    )
