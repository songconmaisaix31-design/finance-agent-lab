from .models import BillingRow, CrowdCostRow, IncomeCategory, DeliveryCostCategory


def run_reconciliation(
    food_income: list[IncomeCategory],
    retail_income: list[IncomeCategory],
    food_delivery: list[DeliveryCostCategory],
    retail_delivery: list[DeliveryCostCategory],
    food_hq_fee: float,
    retail_hq_fee: float,
    food_rows: list[BillingRow],
    retail_rows: list[BillingRow],
    crowd_rows: list[CrowdCostRow],
) -> list[dict]:
    checks = []

    # 1. Income: category sum equals total
    food_total = sum(row.settlement_amount for row in food_rows)
    food_cat_sum = sum(c.total_amount for c in food_income)
    checks.append({
        "check": "food_income_sum",
        "passed": abs(food_total - food_cat_sum) < 0.02,
        "expected": round(food_total, 2),
        "actual": round(food_cat_sum, 2),
    })

    retail_total = sum(row.settlement_amount for row in retail_rows)
    retail_cat_sum = sum(c.total_amount for c in retail_income)
    checks.append({
        "check": "retail_income_sum",
        "passed": abs(retail_total - retail_cat_sum) < 0.02,
        "expected": round(retail_total, 2),
        "actual": round(retail_cat_sum, 2),
    })

    # 2. Income: avg = amount / count
    for c in food_income:
        expected_avg = round(c.total_amount / c.distinct_order_count, 2) if c.distinct_order_count > 0 else 0.0
        checks.append({
            "check": f"food_income_avg_{c.standard_name}",
            "passed": abs(c.avg_per_order - expected_avg) < 0.02,
            "expected": expected_avg,
            "actual": c.avg_per_order,
        })

    for c in retail_income:
        expected_avg = round(c.total_amount / c.distinct_order_count, 2) if c.distinct_order_count > 0 else 0.0
        checks.append({
            "check": f"retail_income_avg_{c.standard_name}",
            "passed": abs(c.avg_per_order - expected_avg) < 0.02,
            "expected": expected_avg,
            "actual": c.avg_per_order,
        })

    # 3. Delivery: zhuansong total = count * unit_cost
    for c in food_delivery + retail_delivery:
        if c.unit_cost > 0:
            expected = round(c.order_count * c.unit_cost, 2)
            checks.append({
                "check": f"delivery_fixed_{c.category}",
                "passed": abs(c.total_cost - expected) < 0.02,
                "expected": expected,
                "actual": c.total_cost,
            })

    # 4. Zhongbao: matched + unmatched + empty = billing order count
    for c in food_delivery + retail_delivery:
        if c.unit_cost == 0:
            sum_parts = c.matched_count + c.unmatched_count
            checks.append({
                "check": f"zhongbao_order_count_{c.category}",
                "passed": sum_parts + c.empty_waybill_count == c.order_count,
                "expected": c.order_count,
                "actual": sum_parts,
                "detail": f"matched={c.matched_count} unmatched={c.unmatched_count} empty={c.empty_waybill_count}",
            })

            breakdown_sum = sum(b.total_cost for b in c.crowd_breakdown)
            checks.append({
                "check": f"zhongbao_cost_breakdown_sum_{c.category}",
                "passed": abs(breakdown_sum - c.total_cost) < 0.02,
                "expected": round(c.total_cost, 2),
                "actual": round(breakdown_sum, 2),
            })

    # 5. Crowd cost data integrity
    total_waybills = len(crowd_rows)
    distinct_waybills = len(set(cr.waybill_id for cr in crowd_rows if cr.waybill_id))
    checks.append({
        "check": "crowd_cost_no_duplicate_waybills",
        "passed": total_waybills == distinct_waybills,
        "expected": total_waybills,
        "actual": distinct_waybills,
    })

    return checks
