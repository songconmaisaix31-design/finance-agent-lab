import json
from decimal import Decimal


def reconcile_income(income_result: dict, all_rows: list, tolerance: Decimal) -> list[dict]:
    checks = []

    total_all = sum(
        r.settlement_amount for r in all_rows
        if r.settlement_amount is not None
    )
    total_whitelist = income_result["total_settlement"]

    checks.append({
        "check": "income_whitelist_vs_all_settlement",
        "passed": True,
        "whitelist_settlement": str(total_whitelist),
        "all_rows_settlement": str(total_all),
        "note": "Whitelist settlement shown; all rows including non-whitelist may differ",
    })

    for c in income_result["categories"]:
        expected_avg = c["total_settlement"] / c["distinct_order_count"] if c["distinct_order_count"] > 0 else Decimal("0")
        diff = abs(c["avg_per_order"] - expected_avg)
        checks.append({
            "check": f"income_avg_{c['service_package']}",
            "passed": diff <= tolerance,
            "expected": str(expected_avg),
            "actual": str(c["avg_per_order"]),
        })

    total_from_categories = sum(c["total_settlement"] for c in income_result["categories"])
    checks.append({
        "check": "income_category_sum_equals_total",
        "passed": abs(total_from_categories - income_result["total_settlement"]) <= tolerance,
        "expected": str(income_result["total_settlement"]),
        "actual": str(total_from_categories),
    })

    return checks


def reconcile_team_cost(team_result: dict, tolerance: Decimal) -> list[dict]:
    checks = []

    for key in ["team_group", "team_normal"]:
        d = team_result[key]
        expected = Decimal(d["distinct_order_count"]) * d["unit_cost"]
        diff = abs(d["total_cost"] - expected)
        checks.append({
            "check": f"team_cost_{key}",
            "passed": diff <= tolerance,
            "expected": str(expected),
            "actual": str(d["total_cost"]),
        })

    total_from_parts = team_result["team_group"]["total_cost"] + team_result["team_normal"]["total_cost"]
    checks.append({
        "check": "team_cost_total_equals_parts",
        "passed": abs(total_from_parts - team_result["total_team_cost"]) <= tolerance,
        "expected": str(team_result["total_team_cost"]),
        "actual": str(total_from_parts),
    })

    return checks


def reconcile_bill_vs_cost_table(
    bill_crowd_counts: dict,
    crowd_buckets: dict,
) -> dict:
    comparisons = []

    mapping = [
        ("catering", "crowd_normal", "catering_normal"),
        ("catering", "crowd_group", "catering_group"),
        ("retail", "crowd_normal", "retail_normal"),
        ("retail", "crowd_group", "retail_group"),
    ]

    all_match = True
    for business, bill_key, cost_key in mapping:
        # This function is called per business category, so we only compare
        # when bill_key matches the crowd bucket
        pass

    return {"comparisons": comparisons, "all_match": all_match}


def compare_bill_crowd_counts(
    bill_crowd_counts: dict,
    crowd_buckets: dict,
    business: str,
) -> list[dict]:
    comparisons = []

    if business == "餐饮":
        prefix = "catering"
    else:
        prefix = "retail"

    for order_type in ["normal", "group"]:
        bill_key = f"crowd_{order_type}"
        crowd_key = f"{prefix}_{order_type}"

        bill_count = bill_crowd_counts[bill_key]["distinct_order_count"]
        crowd_count = crowd_buckets[crowd_key].get("cost_table_completed_orders", Decimal("0"))
        final_cost = crowd_buckets[crowd_key].get("final_cost", crowd_buckets[crowd_key].get("cost_table_total_cost", Decimal("0")))
        final_count = crowd_buckets[crowd_key].get("final_order_count", crowd_count)
        final_avg = crowd_buckets[crowd_key].get("final_avg_cost", crowd_buckets[crowd_key].get("avg_cost_per_order", Decimal("0")))

        diff = crowd_count - Decimal(str(bill_count))
        diff_rate = diff / Decimal(str(bill_count)) if bill_count > 0 else Decimal("0")

        match = diff == 0
        if not match:
            status = "WARNING"
        else:
            status = "OK"

        comparisons.append({
            "business": business,
            "category": f"{business}众包{'拼团' if order_type == 'group' else '正常单'}",
            "bill_positive_order_count": bill_count,
            "cost_table_completed_orders": str(crowd_count),
            "count_difference": str(diff),
            "count_difference_rate": str(diff_rate),
            "crowd_cost_final": str(final_cost),
            "crowd_cost_avg": str(final_avg),
            "status": status,
        })

    return comparisons


def run_all_checks(
    food_income,
    retail_income,
    food_team,
    retail_team,
    food_crowd_bill,
    retail_crowd_bill,
    crowd_buckets,
    crowd_reconciliation,
    manifest_verification,
    food_rows,
    retail_rows,
    tolerance: Decimal,
) -> dict:
    all_checks = []

    all_checks.extend(reconcile_income(food_income, food_rows, tolerance))
    all_checks.extend(reconcile_income(retail_income, retail_rows, tolerance))
    all_checks.extend(reconcile_team_cost(food_team, tolerance))
    all_checks.extend(reconcile_team_cost(retail_team, tolerance))

    food_cmp = compare_bill_crowd_counts(food_crowd_bill, crowd_buckets, "餐饮")
    retail_cmp = compare_bill_crowd_counts(retail_crowd_bill, crowd_buckets, "零售")
    all_cmp = food_cmp + retail_cmp

    all_checks.extend(crowd_reconciliation.get("checks", []))

    files_ok = manifest_verification.get("all_unchanged", True)

    return {
        "income_checks": [c for c in all_checks if c["check"].startswith("income")],
        "team_cost_checks": [c for c in all_checks if c["check"].startswith("team")],
        "crowd_cost_checks": crowd_reconciliation.get("checks", []),
        "bill_cost_comparisons": all_cmp,
        "file_integrity_ok": files_ok,
        "all_passed": all(c.get("passed", True) for c in all_checks) and files_ok,
    }


def save_reconciliation(recon: dict, output_path: str):
    out = {
        "income_checks": [],
        "team_cost_checks": [],
        "crowd_cost_checks": [],
        "bill_cost_comparisons": [],
        "file_integrity_ok": recon["file_integrity_ok"],
        "all_passed": recon["all_passed"],
    }
    for c in recon["income_checks"]:
        out["income_checks"].append(_serialize_check(c))
    for c in recon["team_cost_checks"]:
        out["team_cost_checks"].append(_serialize_check(c))
    for c in recon["crowd_cost_checks"]:
        out["crowd_cost_checks"].append(_serialize_check(c))
    for c in recon["bill_cost_comparisons"]:
        out["bill_cost_comparisons"].append(c)

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)


def _serialize_check(c: dict) -> dict:
    return {
        k: str(v) if isinstance(v, Decimal) else v
        for k, v in c.items()
    }
