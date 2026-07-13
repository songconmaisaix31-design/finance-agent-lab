from collections import defaultdict
from .models import BillingRow, CrowdCostRow, CapacityLineBreakdown


def match_crowd_costs(
    billing_rows: list[BillingRow],
    crowd_rows: list[CrowdCostRow],
    delivery_method: str,
    service_package: str,
    is_retail_filter: int,
) -> dict:
    """
    Match billing orders against crowd cost data for zhongbao delivery categories.
    Returns aggregated results by capacity line.
    """
    billing_order_ids: set[str] = set()
    for row in billing_rows:
        if row.delivery_method == delivery_method and row.service_package == service_package:
            if row.order_id:
                billing_order_ids.add(row.order_id)

    crowd_by_order: dict[str, list[CrowdCostRow]] = defaultdict(list)
    for cr in crowd_rows:
        if cr.is_retail == is_retail_filter and cr.order_id:
            crowd_by_order[cr.order_id].append(cr)

    matched_orders: dict[str, list[CrowdCostRow]] = {}
    unmatched_orders = set()
    duplicate_orders = set()

    for oid in billing_order_ids:
        if oid in crowd_by_order:
            matched = crowd_by_order[oid]
            matched_orders[oid] = matched
            if len(matched) > 1:
                duplicate_orders.add(oid)
        else:
            unmatched_orders.add(oid)

    empty_waybills = sum(
        1 for oid in billing_order_ids if not oid
    )

    capacity_costs: dict[str, float] = defaultdict(float)
    capacity_counts: dict[str, int] = defaultdict(int)

    for oid, matched_list in matched_orders.items():
        for cr in matched_list:
            cl = cr.capacity_line if cr.capacity_line else "未识别"
            capacity_costs[cl] += cr.total_cost
            capacity_counts[cl] += 1

    breakdown = []
    for cl in sorted(capacity_costs.keys()):
        cost = round(capacity_costs[cl], 2)
        cnt = capacity_counts[cl]
        avg = round(cost / cnt, 2) if cnt > 0 else 0.0
        breakdown.append(CapacityLineBreakdown(
            capacity_line=cl,
            order_count=cnt,
            total_cost=cost,
            avg_per_order=avg,
        ))

    total_matched_cost = round(sum(clb.total_cost for clb in breakdown), 2)

    return {
        "billing_order_count": len(billing_order_ids),
        "matched_count": len(matched_orders),
        "unmatched_count": len(unmatched_orders),
        "duplicate_count": len(duplicate_orders),
        "empty_waybill_count": empty_waybills,
        "total_cost": total_matched_cost,
        "breakdown": breakdown,
        "unmatched_order_ids": list(unmatched_orders),
        "duplicate_order_ids": list(duplicate_orders),
        "matched_details": matched_orders,
    }
