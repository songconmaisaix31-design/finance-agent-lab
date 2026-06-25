import csv
import json
from decimal import Decimal

from .crowd_cost_fast import (
    _detect_crowd_columns,
    load_crowd_cost_rows_fast,
    write_crowd_cost_csv_fast,
)


def extract_crowd_cost_buckets(cost_filepath: str, city_config: dict) -> dict:
    cc = city_config["crowd_cost"]
    detail_sheet = cc["detail_sheet"]
    check_sheet = cc["check_sheet"]
    filters = cc["filters"]
    field_names_list = list(cc["field_names"].values())
    category_mapping = cc["category_mapping"]

    col_map, header_row = _detect_crowd_columns(cost_filepath, detail_sheet, field_names_list)
    data_start = header_row + 1

    all_rows = load_crowd_cost_rows_fast(cost_filepath, detail_sheet, col_map, data_start)

    date_filter = str(filters["date"]).strip()
    status_filter = str(filters["delivery_status"]).strip()
    city_filter = str(filters["city_name"]).strip()

    filtered = []
    for r in all_rows:
        r_date = str(r["date"]).strip()
        r_status = str(r["delivery_status"]).strip()
        r_city = str(r["city"]).strip()
        if r_date.startswith(date_filter) and r_status == status_filter and r_city == city_filter:
            filtered.append(r)

    buckets = {
        "catering_normal": {"completed_orders": Decimal("0"), "total_cost": Decimal("0"), "rows": []},
        "catering_group": {"completed_orders": Decimal("0"), "total_cost": Decimal("0"), "rows": []},
        "retail_normal": {"completed_orders": Decimal("0"), "total_cost": Decimal("0"), "rows": []},
        "retail_group": {"completed_orders": Decimal("0"), "total_cost": Decimal("0"), "rows": []},
    }

    cm = category_mapping
    for r in filtered:
        is_retail = r["is_retail"]
        is_group = r["is_group_order"]
        for bucket_name, bucket_def in cm.items():
            if is_retail == bucket_def["is_retail"] and is_group == bucket_def["is_group_order"]:
                buckets[bucket_name]["completed_orders"] += r["completed_orders"]
                buckets[bucket_name]["total_cost"] += r["total_cost"]
                buckets[bucket_name]["rows"].append(r)
                break

    source_rows_all = []
    for bucket_name in buckets:
        b = buckets[bucket_name]
        count = b["completed_orders"]
        b["avg_cost_per_order"] = b["total_cost"] / count if count > 0 else Decimal("0")
        b["cost_table_completed_orders"] = b["completed_orders"]
        b["cost_table_total_cost"] = b["total_cost"]
        for r in b["rows"]:
            r["_bucket"] = bucket_name
        source_rows_all.extend(b["rows"])
        del b["rows"]

    return {
        "buckets": buckets,
        "source_rows": source_rows_all,
        "filtered_row_count": len(filtered),
        "all_row_count": len(all_rows),
        "source_sheet": detail_sheet,
        "check_sheet": check_sheet,
    }


def apply_crowd_cost_rate(buckets: dict, bill_crowd_counts: dict, per_order_rate: Decimal, business: str) -> dict:
    prefix = "catering" if business == "餐饮" else "retail"

    for order_type in ["normal", "group"]:
        crowd_key = f"{prefix}_{order_type}"
        bill_key = f"crowd_{order_type}"

        positive_count = Decimal(str(bill_crowd_counts[bill_key]["distinct_order_count"]))
        calculated_cost = positive_count * per_order_rate

        if crowd_key in buckets:
            buckets[crowd_key]["final_cost"] = calculated_cost
            buckets[crowd_key]["final_order_count"] = positive_count
            buckets[crowd_key]["per_order_rate"] = per_order_rate
            if positive_count > 0:
                buckets[crowd_key]["final_avg_cost"] = calculated_cost / positive_count
            else:
                buckets[crowd_key]["final_avg_cost"] = Decimal("0")

    return buckets


def load_check_sheet_rows(cost_filepath: str, check_sheet: str) -> list[dict]:
    import openpyxl
    wb = openpyxl.load_workbook(cost_filepath, read_only=True, data_only=True)
    ws = wb[check_sheet]

    rows = []
    for r_idx, row in enumerate(ws.iter_rows(values_only=True), start=1):
        rows.append({
            "source_row": r_idx,
            "values": [str(v) if v is not None else "" for v in row],
        })

    wb.close()
    return rows


def reconcile_cost_tables(
    buckets: dict,
    check_rows: list[dict],
    city_name: str,
    amount_tolerance: Decimal,
) -> dict:
    check_city_name = str(city_name).strip()

    check_pintuan_count = Decimal("0")
    check_pintuan_cost = Decimal("0")
    check_nonpintuan_count = Decimal("0")
    check_nonpintuan_cost = Decimal("0")
    check_total_count = Decimal("0")
    check_total_cost = Decimal("0")
    found_city = False

    for row in check_rows:
        vals = row["values"]
        if len(vals) < 12:
            continue
        row_city = vals[0].strip() if len(vals) > 0 else ""

        if check_city_name != row_city:
            continue

        try:
            check_nonpintuan_cost = Decimal(vals[1]) if vals[1] else Decimal("0")
            check_nonpintuan_count = Decimal(vals[2]) if vals[2] else Decimal("0")
            check_pintuan_cost = Decimal(vals[5]) if vals[5] else Decimal("0")
            check_pintuan_count = Decimal(vals[6]) if vals[6] else Decimal("0")
            check_total_cost = Decimal(vals[9]) if vals[9] else Decimal("0")
            check_total_count = Decimal(vals[10]) if vals[10] else Decimal("0")
        except Exception:
            continue

        found_city = True
        break

    month_pintuan_count = buckets["catering_group"]["completed_orders"] + buckets["retail_group"]["completed_orders"]
    month_pintuan_cost = buckets["catering_group"]["total_cost"] + buckets["retail_group"]["total_cost"]
    month_nonpintuan_count = buckets["catering_normal"]["completed_orders"] + buckets["retail_normal"]["completed_orders"]
    month_nonpintuan_cost = buckets["catering_normal"]["total_cost"] + buckets["retail_normal"]["total_cost"]

    def d_diff(a, b):
        return abs(a - b)

    checks = []
    if found_city:
        checks.append({
            "check": "cost_table_nonpintuan_count",
            "passed": d_diff(month_nonpintuan_count, check_nonpintuan_count) <= Decimal("0"),
            "month_value": month_nonpintuan_count,
            "check_value": check_nonpintuan_count,
        })
        checks.append({
            "check": "cost_table_nonpintuan_cost",
            "passed": d_diff(month_nonpintuan_cost, check_nonpintuan_cost) <= amount_tolerance,
            "month_value": month_nonpintuan_cost,
            "check_value": check_nonpintuan_cost,
        })
        checks.append({
            "check": "cost_table_pintuan_count",
            "passed": d_diff(month_pintuan_count, check_pintuan_count) <= Decimal("0"),
            "month_value": month_pintuan_count,
            "check_value": check_pintuan_count,
        })
        checks.append({
            "check": "cost_table_pintuan_cost",
            "passed": d_diff(month_pintuan_cost, check_pintuan_cost) <= amount_tolerance,
            "month_value": month_pintuan_cost,
            "check_value": check_pintuan_cost,
        })
    else:
        checks.append({
            "check": "cost_table_city_not_found",
            "passed": False,
            "detail": f"City '{check_city_name}' not found in check sheet",
        })

    all_passed = all(c["passed"] for c in checks)
    return {
        "checks": checks,
        "all_passed": all_passed,
        "found_city": found_city,
        "month_nonpintuan_count": month_nonpintuan_count,
        "month_nonpintuan_cost": month_nonpintuan_cost,
        "month_pintuan_count": month_pintuan_count,
        "month_pintuan_cost": month_pintuan_cost,
        "month_total_count": month_pintuan_count + month_nonpintuan_count,
        "month_total_cost": month_pintuan_cost + month_nonpintuan_cost,
    }


def save_crowd_cost_summary(buckets: dict, output_path: str):
    out = {}
    for name, b in buckets.items():
        out[name] = {
            "cost_table_completed_orders": str(b.get("cost_table_completed_orders", "0")),
            "cost_table_total_cost": str(b.get("cost_table_total_cost", "0")),
            "cost_table_avg": str(b.get("avg_cost_per_order", "0")),
            "final_order_count": str(b.get("final_order_count", "0")),
            "final_cost": str(b.get("final_cost", "0")),
            "final_avg": str(b.get("final_avg_cost", "0")),
            "per_order_rate": str(b.get("per_order_rate", "")),
        }
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)


def save_crowd_cost_source_rows(result: dict, output_path: str):
    source_rows = result.get("source_rows", [])
    fieldnames = [
        "source_file", "source_sheet", "source_row",
        "date", "delivery_status", "is_retail", "city",
        "is_group_order", "completed_orders", "total_cost",
    ]
    with open(output_path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames + ["_bucket"], extrasaction="ignore")
        writer.writeheader()
        for r in source_rows:
            row_out = {k: r.get(k, "") for k in fieldnames}
            row_out["_bucket"] = r.get("_bucket", "")
            row_out["completed_orders"] = str(row_out["completed_orders"])
            row_out["total_cost"] = str(row_out["total_cost"])
            writer.writerow(row_out)
