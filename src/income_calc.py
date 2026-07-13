import json
from collections import defaultdict
from decimal import Decimal

from .normalizer import NormalizedBillingRow


def compute_income(
    rows: list[NormalizedBillingRow],
    whitelist: list[dict],
) -> dict:
    whitelist_svcs = {item["service_package"] for item in whitelist}

    category_data: dict[str, dict] = {}
    for item in whitelist:
        category_data[item["service_package"]] = {
            "service_package": item["service_package"],
            "total_settlement": Decimal("0"),
            "total_gross": Decimal("0"),
            "order_ids": set(),
            "positive_order_ids": set(),
            "partial_refund_order_ids": set(),
            "full_refund_order_ids": set(),
            "row_count": 0,
        }

    unknown_types: dict[str, dict] = {}
    all_svc_types = set()

    for row in rows:
        svc = row.service_package_type
        all_svc_types.add(svc)

        if svc in whitelist_svcs:
            data = category_data[svc]
            data["row_count"] += 1
            if row.settlement_amount is not None:
                data["total_settlement"] += row.settlement_amount
            if row.gross_transaction_amount is not None:
                data["total_gross"] += row.gross_transaction_amount
            if row.order_id:
                data["order_ids"].add(row.order_id)
        elif svc and svc not in whitelist_svcs:
            if svc not in unknown_types:
                unknown_types[svc] = {
                    "service_package": svc,
                    "row_count": 0,
                    "total_settlement": Decimal("0"),
                    "total_gross": Decimal("0"),
                    "order_ids": set(),
                }
            ud = unknown_types[svc]
            ud["row_count"] += 1
            if row.settlement_amount is not None:
                ud["total_settlement"] += row.settlement_amount
            if row.gross_transaction_amount is not None:
                ud["total_gross"] += row.gross_transaction_amount
            if row.order_id:
                ud["order_ids"].add(row.order_id)

    income_categories = []
    for item in whitelist:
        svc = item["service_package"]
        d = category_data[svc]
        order_count = len(d["order_ids"])
        avg = d["total_settlement"] / order_count if order_count > 0 else Decimal("0")
        income_categories.append({
            "service_package": svc,
            "row_count": d["row_count"],
            "distinct_order_count": order_count,
            "positive_order_count": 0,
            "partial_refund_count": 0,
            "full_refund_count": 0,
            "total_settlement": d["total_settlement"],
            "total_gross": d["total_gross"],
            "avg_per_order": avg,
        })

    unknown_list = []
    for svc in sorted(unknown_types.keys()):
        d = unknown_types[svc]
        order_count = len(d["order_ids"])
        unknown_list.append({
            "service_package": svc,
            "row_count": d["row_count"],
            "distinct_order_count": order_count,
            "total_settlement": d["total_settlement"],
            "total_gross": d["total_gross"],
        })

    total_settlement = sum(c["total_settlement"] for c in income_categories)
    total_gross = sum(c["total_gross"] for c in income_categories)
    total_distinct_orders = sum(c["distinct_order_count"] for c in income_categories)

    return {
        "categories": income_categories,
        "unknown_types": unknown_list,
        "total_settlement": total_settlement,
        "total_gross": total_gross,
        "total_distinct_orders": total_distinct_orders,
    }


def analyze_refund_types(
    rows: list[NormalizedBillingRow],
    whitelist: list[dict],
) -> dict:
    whitelist_svcs = {item["service_package"] for item in whitelist}
    order_settlements: dict[str, Decimal] = defaultdict(lambda: Decimal("0"))
    order_svc: dict[str, str] = {}

    for row in rows:
        if row.service_package_type not in whitelist_svcs:
            continue
        if not row.order_id:
            continue
        if row.settlement_amount is not None:
            order_settlements[row.order_id] += row.settlement_amount
        if row.order_id:
            order_svc[row.order_id] = row.service_package_type

    positive = set()
    partial_refund = set()
    full_refund = set()

    for oid, total in order_settlements.items():
        if total > 0:
            positive.add(oid)
        elif total == 0:
            full_refund.add(oid)
        else:
            partial_refund.add(oid)

    return {
        "positive_order_ids": positive,
        "partial_refund_order_ids": partial_refund,
        "full_refund_order_ids": full_refund,
    }


def save_income_summary(result: dict, output_path: str):
    def _d(v):
        if isinstance(v, Decimal):
            return str(v)
        return v

    out = {
        "categories": [],
        "unknown_types": [
            {
                "service_package": u["service_package"],
                "row_count": u["row_count"],
                "distinct_order_count": u["distinct_order_count"],
                "total_settlement": _d(u["total_settlement"]),
                "total_gross": _d(u["total_gross"]),
            }
            for u in result["unknown_types"]
        ],
        "total_settlement": _d(result["total_settlement"]),
        "total_gross": _d(result["total_gross"]),
        "total_distinct_orders": result["total_distinct_orders"],
    }
    for c in result["categories"]:
        out["categories"].append({
            "service_package": c["service_package"],
            "row_count": c["row_count"],
            "distinct_order_count": c["distinct_order_count"],
            "positive_order_count": c["positive_order_count"],
            "partial_refund_count": c["partial_refund_count"],
            "full_refund_count": c["full_refund_count"],
            "total_settlement": _d(c["total_settlement"]),
            "total_gross": _d(c["total_gross"]),
            "avg_per_order": _d(c["avg_per_order"]),
        })
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)


def save_unknown_income_types_csv(unknown: list[dict], output_path: str):
    import csv
    with open(output_path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=[
            "service_package", "row_count", "distinct_order_count",
            "total_settlement", "total_gross",
        ])
        writer.writeheader()
        for u in unknown:
            writer.writerow({
                "service_package": u["service_package"],
                "row_count": u["row_count"],
                "distinct_order_count": u["distinct_order_count"],
                "total_settlement": str(u["total_settlement"]),
                "total_gross": str(u["total_gross"]),
            })
