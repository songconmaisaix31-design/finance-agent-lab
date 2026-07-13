import json
from decimal import Decimal

from .normalizer import NormalizedBillingRow


def compute_hq_fee(income_result: dict, fee_rate: Decimal) -> dict:
    total_gross = income_result["total_gross"]
    hq_fee = total_gross * fee_rate
    return {
        "total_gross_in_scope": total_gross,
        "fee_rate": str(fee_rate),
        "hq_fee": hq_fee,
    }


def compute_team_delivery_cost(
    rows: list[NormalizedBillingRow],
    delivery_config: dict,
    unit_cost_group: Decimal,
    unit_cost_normal: Decimal,
) -> dict:
    team_group_svcs = set(delivery_config["team_group"]["service_packages"])
    team_normal_svcs = set(delivery_config["team_normal"]["service_packages"])

    group_order_ids = set()
    normal_order_ids = set()

    for row in rows:
        if row.delivery_type != "蜂鸟团队":
            continue
        if not row.order_id:
            continue
        if row.service_package_type in team_group_svcs:
            group_order_ids.add(row.order_id)
        elif row.service_package_type in team_normal_svcs:
            normal_order_ids.add(row.order_id)

    group_count = len(group_order_ids)
    normal_count = len(normal_order_ids)
    group_cost = Decimal(group_count) * unit_cost_group
    normal_cost = Decimal(normal_count) * unit_cost_normal

    return {
        "team_group": {
            "distinct_order_count": group_count,
            "unit_cost": unit_cost_group,
            "total_cost": group_cost,
        },
        "team_normal": {
            "distinct_order_count": normal_count,
            "unit_cost": unit_cost_normal,
            "total_cost": normal_cost,
        },
        "total_team_cost": group_cost + normal_cost,
    }


def compute_bill_crowd_order_counts(
    rows: list[NormalizedBillingRow],
    delivery_config: dict,
    positive_only: bool = True,
) -> dict:
    crowd_group_svcs = set(delivery_config["crowd_group"]["service_packages"])
    crowd_normal_svcs = set(delivery_config["crowd_normal"]["service_packages"])

    group_order_ids = set()
    normal_order_ids = set()

    for row in rows:
        if row.delivery_type != "蜂鸟众包":
            continue
        if not row.order_id:
            continue
        if positive_only and row.order_type != "正向单":
            continue
        if row.service_package_type in crowd_group_svcs:
            group_order_ids.add(row.order_id)
        elif row.service_package_type in crowd_normal_svcs:
            normal_order_ids.add(row.order_id)

    return {
        "crowd_group": {
            "distinct_order_count": len(group_order_ids),
        },
        "crowd_normal": {
            "distinct_order_count": len(normal_order_ids),
        },
    }


def save_hq_fee_summary(result: dict, output_path: str):
    out = {
        "total_gross_in_scope": str(result["total_gross_in_scope"]),
        "fee_rate": result["fee_rate"],
        "hq_fee": str(result["hq_fee"]),
    }
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)


def save_team_cost_summary(result: dict, output_path: str):
    out = {
        "team_group": {
            "distinct_order_count": result["team_group"]["distinct_order_count"],
            "unit_cost": str(result["team_group"]["unit_cost"]),
            "total_cost": str(result["team_group"]["total_cost"]),
        },
        "team_normal": {
            "distinct_order_count": result["team_normal"]["distinct_order_count"],
            "unit_cost": str(result["team_normal"]["unit_cost"]),
            "total_cost": str(result["team_normal"]["total_cost"]),
        },
        "total_team_cost": str(result["total_team_cost"]),
    }
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
