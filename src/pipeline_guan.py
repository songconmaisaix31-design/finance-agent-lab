import csv
import json
import os
import shutil
import sys
import tempfile
import zipfile
from datetime import datetime
from decimal import Decimal

from .config import load_city_config
from .crowd_cost import (
    extract_crowd_cost_buckets,
    apply_crowd_cost_rate,
    reconcile_cost_tables,
    save_crowd_cost_summary,
    save_crowd_cost_source_rows,
    load_check_sheet_rows,
)
from .fee_calc import (
    compute_bill_crowd_order_counts,
    compute_hq_fee,
    compute_team_delivery_cost,
    save_hq_fee_summary,
    save_team_cost_summary,
)
from .field_mapper import map_billing_sheet
from .income_calc import (
    compute_income,
    save_income_summary,
    save_unknown_income_types_csv,
)
from .manifest import create_manifest, file_info, verify_manifest
from .normalizer import (
    load_billing_rows,
    write_normalized_csv,
)
from .reconcile import (
    compare_bill_crowd_counts,
    run_all_checks,
    save_reconciliation,
)
from .report import generate_report
from .run_id import generate_run_id


BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INPUT_DIR = os.path.dirname(BASE_DIR)
RUNS_DIR = os.path.join(BASE_DIR, "runs")
CONFIG_DIR = os.path.join(BASE_DIR, "config")


def main():
    print("=" * 70)
    print("固安 2026-06-23 财务核算 Harness")
    print("=" * 70)

    print("\n[0] Loading configuration...")
    cfg = load_city_config("guan")

    run_id = generate_run_id(cfg["city_name"], cfg["billing_date"])
    run_dir = os.path.join(RUNS_DIR, run_id)
    os.makedirs(run_dir, exist_ok=True)
    print(f"    Run ID: {run_id}")
    print(f"    Run directory: {run_dir}")

    temp_dir = os.path.join(run_dir, "temp_extracted")
    os.makedirs(temp_dir, exist_ok=True)

    print("\n[1] Manifest: Recording input file hashes...")
    input_files = [
        os.path.join(INPUT_DIR, "342_2026-06-23~2026-06-23_餐饮_账单明细.zip"),
        os.path.join(INPUT_DIR, "342_2026-06-23~2026-06-23_零售_账单明细.zip"),
        os.path.join(INPUT_DIR, "6.23众包成本.xlsx"),
    ]
    for fp in input_files:
        if not os.path.exists(fp):
            print(f"    ERROR: Input file not found: {fp}")
            sys.exit(1)
        info = file_info(fp)
        print(f"    {info['name']}: size={info['size_bytes']}, sha256={info['sha256'][:16]}...")

    manifest = create_manifest(input_files, run_dir)
    config_snapshot_path = os.path.join(run_dir, "config_snapshot.yaml")
    shutil.copy(
        os.path.join(CONFIG_DIR, "cities", "guan.yaml"),
        config_snapshot_path,
    )

    print("\n[2] Extracting billing ZIP files...")
    catering_zip = input_files[0]
    retail_zip = input_files[1]

    with zipfile.ZipFile(catering_zip, "r") as zf:
        zf.extractall(temp_dir)
        catering_xlsx = None
        for name in zf.namelist():
            if name.endswith(".xlsx"):
                catering_xlsx = os.path.join(temp_dir, name)
                break
    print(f"    Catering extracted: {os.path.basename(catering_xlsx)}")

    with zipfile.ZipFile(retail_zip, "r") as zf:
        zf.extractall(temp_dir)
        retail_xlsx = None
        for name in zf.namelist():
            if name.endswith(".xlsx"):
                retail_xlsx = os.path.join(temp_dir, name)
                break
    print(f"    Retail extracted: {os.path.basename(retail_xlsx)}")

    print("\n[3] Field mapping and header detection...")
    catering_map = map_billing_sheet(catering_xlsx)
    retail_map = map_billing_sheet(retail_xlsx)
    print(f"    Catering: header row {catering_map.header_row}, sheet '{catering_map.source_sheet}'")
    print(f"    Retail: header row {retail_map.header_row}, sheet '{retail_map.source_sheet}'")

    field_mapping_out = {
        "catering": {
            "source_file": catering_map.source_file,
            "source_sheet": catering_map.source_sheet,
            "header_row": catering_map.header_row,
            "data_start_row": catering_map.data_start_row,
            "column_map": {k: v for k, v in catering_map.column_map.items()},
        },
        "retail": {
            "source_file": retail_map.source_file,
            "source_sheet": retail_map.source_sheet,
            "header_row": retail_map.header_row,
            "data_start_row": retail_map.data_start_row,
            "column_map": {k: v for k, v in retail_map.column_map.items()},
        },
    }
    with open(os.path.join(run_dir, "field_mapping.json"), "w", encoding="utf-8") as f:
        json.dump(field_mapping_out, f, ensure_ascii=False, indent=2)

    print("\n[4] Normalizing billing data...")
    food_rows = load_billing_rows(catering_xlsx, catering_map, "餐饮")
    retail_rows = load_billing_rows(retail_xlsx, retail_map, "零售")
    print(f"    Catering rows: {len(food_rows)}")
    print(f"    Retail rows: {len(retail_rows)}")

    write_normalized_csv(food_rows, os.path.join(run_dir, "normalized_catering.csv"))
    write_normalized_csv(retail_rows, os.path.join(run_dir, "normalized_retail.csv"))

    food_invalid = [{"source_file": r.source_file, "source_row": r.source_row, "order_id": r.order_id, "error": r.amount_error}
                    for r in food_rows if not r.amount_valid]
    retail_invalid = [{"source_file": r.source_file, "source_row": r.source_row, "order_id": r.order_id, "error": r.amount_error}
                      for r in retail_rows if not r.amount_valid]
    print(f"    Invalid amounts: catering={len(food_invalid)}, retail={len(retail_invalid)}")

    invalid_out = food_invalid + retail_invalid
    with open(os.path.join(run_dir, "invalid_amounts.csv"), "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["source_file", "source_row", "order_id", "error"])
        writer.writeheader()
        for inv in invalid_out:
            writer.writerow(inv)

    print("\n[5] Profiling inputs...")
    food_svc = set(r.service_package_type for r in food_rows if r.service_package_type)
    retail_svc = set(r.service_package_type for r in retail_rows if r.service_package_type)
    food_del = set(r.delivery_type for r in food_rows if r.delivery_type)
    retail_del = set(r.delivery_type for r in retail_rows if r.delivery_type)

    profile = {
        "catering_service_packages": sorted(food_svc),
        "retail_service_packages": sorted(retail_svc),
        "catering_delivery_types": sorted(food_del),
        "retail_delivery_types": sorted(retail_del),
        "catering_row_count": len(food_rows),
        "retail_row_count": len(retail_rows),
    }
    with open(os.path.join(run_dir, "input_profile.json"), "w", encoding="utf-8") as f:
        json.dump(profile, f, ensure_ascii=False, indent=2)
    print(f"    Catering service packages: {sorted(food_svc)}")
    print(f"    Retail service packages: {sorted(retail_svc)}")
    print(f"    Catering delivery types: {sorted(food_del)}")
    print(f"    Retail delivery types: {sorted(retail_del)}")

    unknown_delivery = []
    known_del = {"蜂鸟团队", "蜂鸟众包", ""}
    for d in sorted(food_del - known_del):
        if d:
            unknown_delivery.append({"business": "餐饮", "delivery_type": d, "count": sum(1 for r in food_rows if r.delivery_type == d)})
    for d in sorted(retail_del - known_del):
        if d:
            unknown_delivery.append({"business": "零售", "delivery_type": d, "count": sum(1 for r in retail_rows if r.delivery_type == d)})

    non_delivery_types = {"到店自取", "专送", "选推"}
    flagged_subsidy_rows = []
    for business, rows, label in [("餐饮", food_rows, "餐饮"), ("零售", retail_rows, "零售")]:
        for r in rows:
            if r.delivery_type not in non_delivery_types:
                continue
            subsidy = r.agent_delivery_subsidy
            if subsidy is not None and subsidy != Decimal("0"):
                flagged_subsidy_rows.append({
                    "business": label,
                    "delivery_type": r.delivery_type,
                    "service_package": r.service_package_type,
                    "order_id": r.order_id,
                    "subsidy": subsidy,
                    "settlement_amount": r.settlement_amount or Decimal("0"),
                    "source_row": r.source_row,
                    "source_file": r.source_file,
                })

    print("\n[6] Calculating income...")
    food_income = compute_income(food_rows, cfg["food_income_whitelist"])
    retail_income = compute_income(retail_rows, cfg["retail_income_whitelist"])

    save_income_summary(food_income, os.path.join(run_dir, "income_summary_food.json"))
    save_income_summary(retail_income, os.path.join(run_dir, "income_summary_retail.json"))
    save_unknown_income_types_csv(food_income["unknown_types"], os.path.join(run_dir, "unknown_income_types_food.csv"))
    save_unknown_income_types_csv(retail_income["unknown_types"], os.path.join(run_dir, "unknown_income_types_retail.csv"))

    print(f"    Food income: {food_income['total_settlement']}")
    print(f"    Retail income: {retail_income['total_settlement']}")
    print(f"    Food unknown types: {[u['service_package'] for u in food_income['unknown_types']]}")
    print(f"    Retail unknown types: {[u['service_package'] for u in retail_income['unknown_types']]}")

    print("\n[7] Calculating headquarters fees...")
    hq_rate = cfg["_headquarters_fee_rate_d"]
    food_hq = compute_hq_fee(food_income, hq_rate)
    retail_hq = compute_hq_fee(retail_income, hq_rate)
    save_hq_fee_summary(food_hq, os.path.join(run_dir, "headquarters_fee_food.json"))
    save_hq_fee_summary(retail_hq, os.path.join(run_dir, "headquarters_fee_retail.json"))
    print(f"    Food HQ fee: {food_hq['hq_fee']}")
    print(f"    Retail HQ fee: {retail_hq['hq_fee']}")

    print("\n[8] Calculating team delivery costs...")
    food_team = compute_team_delivery_cost(
        food_rows, cfg["food_delivery_categories"],
        cfg["_team_group_unit_cost_d"], cfg["_team_normal_unit_cost_d"],
    )
    retail_team = compute_team_delivery_cost(
        retail_rows, cfg["retail_delivery_categories"],
        cfg["_team_group_unit_cost_d"], cfg["_team_normal_unit_cost_d"],
    )
    save_team_cost_summary(food_team, os.path.join(run_dir, "team_delivery_cost_food.json"))
    save_team_cost_summary(retail_team, os.path.join(run_dir, "team_delivery_cost_retail.json"))
    print(f"    Food team group: {food_team['team_group']['distinct_order_count']} orders, {food_team['team_group']['total_cost']}")
    print(f"    Food team normal: {food_team['team_normal']['distinct_order_count']} orders, {food_team['team_normal']['total_cost']}")
    print(f"    Retail team group: {retail_team['team_group']['distinct_order_count']} orders, {retail_team['team_group']['total_cost']}")
    print(f"    Retail team normal: {retail_team['team_normal']['distinct_order_count']} orders, {retail_team['team_normal']['total_cost']}")

    print("\n[9] Computing bill-side crowd order counts (正向单 only)...")
    food_crowd_bill = compute_bill_crowd_order_counts(food_rows, cfg["food_delivery_categories"], positive_only=True)
    retail_crowd_bill = compute_bill_crowd_order_counts(retail_rows, cfg["retail_delivery_categories"], positive_only=True)
    print(f"    Food crowd group: {food_crowd_bill['crowd_group']['distinct_order_count']} orders")
    print(f"    Food crowd normal: {food_crowd_bill['crowd_normal']['distinct_order_count']} orders")
    print(f"    Retail crowd group: {retail_crowd_bill['crowd_group']['distinct_order_count']} orders")
    print(f"    Retail crowd normal: {retail_crowd_bill['crowd_normal']['distinct_order_count']} orders")

    print("\n[10] Extracting crowd cost from 月 sheet...")
    crowd_cost_file = input_files[2]
    crowd_result = extract_crowd_cost_buckets(crowd_cost_file, cfg)
    crowd_buckets = crowd_result["buckets"]

    print(f"    Filtered rows from 月: {crowd_result['filtered_row_count']} / {crowd_result['all_row_count']}")
    for name, b in crowd_buckets.items():
        print(f"    {name}: cost_table_orders={b['cost_table_completed_orders']}, cost_table_cost={b['cost_table_total_cost']}")

    crowd_cost_rate = cfg["_crowd_cost_per_order_rate_d"]
    print(f"\n    Applying crowd cost rate: {crowd_cost_rate} (from {cfg['crowd_cost']['rate_source']})")
    crowd_buckets = apply_crowd_cost_rate(crowd_buckets, food_crowd_bill, crowd_cost_rate, "餐饮")
    crowd_buckets = apply_crowd_cost_rate(crowd_buckets, retail_crowd_bill, crowd_cost_rate, "零售")

    for name, b in crowd_buckets.items():
        fc = b.get("final_cost", b.get("cost_table_total_cost", Decimal("0")))
        fo = b.get("final_order_count", b.get("cost_table_completed_orders", Decimal("0")))
        print(f"    {name}: positive_orders={fo}, final_cost={fc}")

    save_crowd_cost_summary(crowd_buckets, os.path.join(run_dir, "crowd_cost_summary.json"))
    save_crowd_cost_source_rows(crowd_result, os.path.join(run_dir, "crowd_cost_source_rows.csv"))

    print("\n[11] Comparing bill vs cost table order counts...")
    food_cmp = compare_bill_crowd_counts(food_crowd_bill, crowd_buckets, "餐饮")
    retail_cmp = compare_bill_crowd_counts(retail_crowd_bill, crowd_buckets, "零售")
    all_cmp = food_cmp + retail_cmp

    for c in all_cmp:
        print(f"    {c['category']}: bill={c['bill_positive_order_count']}, cost_table={c['cost_table_completed_orders']}, diff={c['count_difference']}, status={c['status']}")

    cmp_out_path = os.path.join(run_dir, "bill_cost_order_count_comparison.csv")
    with open(cmp_out_path, "w", encoding="utf-8-sig", newline="") as f:
        fieldnames = ["business", "category", "bill_positive_order_count", "cost_table_completed_orders",
                      "count_difference", "count_difference_rate", "crowd_cost_final",
                      "crowd_cost_avg", "status"]
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for c in all_cmp:
            writer.writerow(c)

    print("\n[12] Reconciling 月 sheet vs 整体 sheet...")
    check_sheet = cfg["crowd_cost"]["check_sheet"]
    check_rows = load_check_sheet_rows(crowd_cost_file, check_sheet)
    crowd_recon = reconcile_cost_tables(
        crowd_buckets, check_rows, cfg["crowd_cost"]["filters"]["city_name"],
        cfg["_amount_tolerance_d"],
    )
    print(f"    All checks passed: {crowd_recon['all_passed']}")
    for c in crowd_recon["checks"]:
        print(f"    {c['check']}: {'PASS' if c['passed'] else 'FAIL'}")

    print("\n[13] Running full reconciliation...")
    tolerance = cfg["_amount_tolerance_d"]
    recon_result = run_all_checks(
        food_income, retail_income,
        food_team, retail_team,
        food_crowd_bill, retail_crowd_bill,
        crowd_buckets, crowd_recon,
        {"all_unchanged": True},
        food_rows, retail_rows,
        tolerance,
    )
    save_reconciliation(recon_result, os.path.join(run_dir, "reconciliation.json"))

    print("\n[14] Generating Excel report...")
    output_xlsx = os.path.join(run_dir, f"固安{cfg['billing_date']}_收入成本核算结果.xlsx")

    run_info = {
        "run_id": run_id,
        "城市": cfg["city_name"],
        "代理商ID": cfg["agent_id"],
        "核算日期": cfg["billing_date"],
        "总部抽点比例": str(cfg["headquarters_fee_rate"]),
        "专送拼团单均成本": str(cfg["team_delivery"]["group_unit_cost"]),
        "专送正常单单均成本": str(cfg["team_delivery"]["normal_unit_cost"]),
        "开始时间": datetime.now().isoformat(),
    }

    generate_report(
        output_xlsx,
        run_info,
        food_income, retail_income,
        food_hq, retail_hq,
        food_team, retail_team,
        crowd_buckets,
        all_cmp,
        crowd_recon,
        food_income["unknown_types"], retail_income["unknown_types"],
        food_invalid, retail_invalid,
        unknown_delivery,
        recon_result,
        flagged_subsidy_rows,
    )
    print(f"    Excel report: {output_xlsx}")

    print("\n[15] Verifying input file integrity...")
    manifest_result = verify_manifest(os.path.join(run_dir, "manifest.json"))
    print(f"    All files unchanged: {manifest_result['all_unchanged']}")
    for v in manifest_result["verification"]:
        print(f"    {v['file']}: {'OK' if v['hash_unchanged'] else 'CHANGED!'}")

    if not manifest_result["all_unchanged"]:
        run_status = "FAILED_SOURCE_FILE_CHANGED"
    elif not crowd_recon["all_passed"]:
        run_status = "FAILED_CROWD_COST_TABLE_RECONCILIATION"
    elif any(c["status"] == "WARNING" for c in all_cmp):
        run_status = "WARNING_COST_ORDER_COUNT_MISMATCH"
    else:
        run_status = "SUCCESS"

    print("\n" + "=" * 70)
    print(f"RUN STATUS: {run_status}")
    print(f"Run ID: {run_id}")
    print(f"Run directory: {run_dir}")
    print(f"Result Excel: {output_xlsx}")
    print("=" * 70)

    return run_status, run_id, run_dir, output_xlsx


if __name__ == "__main__":
    main()
