from .models import BillingRow, IncomeCategory


def compute_income(
    rows: list[BillingRow],
    income_types: list[dict],
) -> tuple[list[IncomeCategory], list[dict]]:
    categories = []
    anomalies = []

    svc_config = {it["service_package"]: it["standard_name"] for it in income_types}
    config_names = set(svc_config.keys())

    info: dict[str, dict] = {}
    for name in svc_config.values():
        info[name] = {"total": 0.0, "orders": set()}

    seen_svc_types = set()
    for row in rows:
        svc = row.service_package
        seen_svc_types.add(svc)

        if not row.order_id:
            anomalies.append({
                "type": "empty_order_id",
                "source": row.source,
                "row_number": row.row_number,
                "order_id": row.order_id,
                "service_package": svc,
                "amount": row.settlement_amount,
            })

        if svc not in svc_config:
            continue

        std_name = svc_config[svc]
        info[std_name]["total"] += row.settlement_amount
        if row.order_id:
            info[std_name]["orders"].add(row.order_id)

    for it in income_types:
        std_name = it["standard_name"]
        d = info[std_name]
        count = len(d["orders"])
        total = d["total"]
        avg = round(total / count, 2) if count > 0 else 0.0
        categories.append(IncomeCategory(
            standard_name=std_name,
            total_amount=round(total, 2),
            distinct_order_count=count,
            avg_per_order=avg,
        ))

    unmatched = seen_svc_types - config_names - {""}
    for u in unmatched:
        anomalies.append({
            "type": "unmatched_service_package",
            "service_package": u,
        })

    return categories, anomalies
