import os
import yaml
from decimal import Decimal


def load_yaml(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_city_config(city: str) -> dict:
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    path = os.path.join(base_dir, "config", "cities", f"{city}.yaml")
    if not os.path.exists(path):
        raise FileNotFoundError(f"City config not found: {path}")
    cfg = load_yaml(path)

    cfg["_headquarters_fee_rate_d"] = Decimal(str(cfg["headquarters_fee_rate"]))
    cfg["_team_group_unit_cost_d"] = Decimal(str(cfg["team_delivery"]["group_unit_cost"]))
    cfg["_team_normal_unit_cost_d"] = Decimal(str(cfg["team_delivery"]["normal_unit_cost"]))
    cfg["_amount_tolerance_d"] = Decimal(str(cfg["reconciliation"]["amount_tolerance"]))
    cfg["_order_count_tolerance"] = int(cfg["reconciliation"]["order_count_tolerance"])
    cfg["_crowd_cost_per_order_rate_d"] = Decimal(str(cfg["crowd_cost"]["per_order_rate"]))

    return cfg


def as_decimal(value: str) -> Decimal:
    return Decimal(str(value))
