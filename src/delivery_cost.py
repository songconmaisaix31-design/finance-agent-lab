from .models import BillingRow, CrowdCostRow, DeliveryCostCategory
from .crowd_matcher import match_crowd_costs


def compute_delivery_costs(
    billing_rows: list[BillingRow],
    crowd_rows: list[CrowdCostRow],
    delivery_config: dict,
    is_retail_filter: int,
) -> tuple[list[DeliveryCostCategory], list[dict]]:
    categories = []
    anomalies = []

    for cat_key, cat_cfg in delivery_config.items():
        dm = cat_cfg["delivery_method"]
        sp = cat_cfg["service_package"]
        has_unit_cost = "unit_cost" in cat_cfg

        if has_unit_cost:
            order_ids = set()
            for row in billing_rows:
                if row.delivery_method == dm and row.service_package == sp and row.order_id:
                    order_ids.add(row.order_id)
            count = len(order_ids)
            uc = cat_cfg["unit_cost"]
            total = round(count * uc, 2)

            if count > 0 and any(not row.order_id for row in billing_rows
                               if row.delivery_method == dm and row.service_package == sp):
                empty_count = sum(
                    1 for row in billing_rows
                    if row.delivery_method == dm and row.service_package == sp and not row.order_id
                )
                anomalies.append({
                    "type": "empty_order_id_in_delivery",
                    "category": cat_key,
                    "delivery_method": dm,
                    "service_package": sp,
                    "count": empty_count,
                })

            categories.append(DeliveryCostCategory(
                category=cat_key,
                order_count=count,
                unit_cost=uc,
                total_cost=total,
            ))
        else:
            result = match_crowd_costs(
                billing_rows, crowd_rows, dm, sp, is_retail_filter,
            )

            categories.append(DeliveryCostCategory(
                category=cat_key,
                order_count=result["billing_order_count"],
                unit_cost=0.0,
                total_cost=result["total_cost"],
                crowd_breakdown=result["breakdown"],
                matched_count=result["matched_count"],
                unmatched_count=result["unmatched_count"],
                duplicate_count=result["duplicate_count"],
                empty_waybill_count=result["empty_waybill_count"],
            ))

            for uoid in result["unmatched_order_ids"]:
                anomalies.append({
                    "type": "crowd_cost_unmatched_order",
                    "category": cat_key,
                    "order_id": uoid,
                })

            for doid in result["duplicate_order_ids"]:
                anomalies.append({
                    "type": "crowd_cost_duplicate_order",
                    "category": cat_key,
                    "order_id": doid,
                })

    return categories, anomalies
