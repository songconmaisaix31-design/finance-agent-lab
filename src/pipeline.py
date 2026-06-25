import sys
import os
import shutil
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.loader import (
    load_config, load_food_billing, load_retail_billing,
    load_crowd_cost, get_file_info,
)
from src.income import compute_income
from src.hq_fee import compute_hq_fee
from src.delivery_cost import compute_delivery_costs
from src.reconciliation import run_reconciliation
from src.reporter import generate_report
from src.models import RunSummary, RunInfo


def _legacy_main_unsafe():
    base_dir = Path(__file__).resolve().parent.parent
    config_dir = base_dir / "config"

    # File paths
    food_billing_path = r"C:\Users\DW\Desktop\623\永城2026-06-21_餐饮_账单明细_detail.xlsx"
    retail_billing_path = r"C:\Users\DW\Desktop\623\永城2026-06-21_零售_账单明细_detail.xlsx"
    crowd_cost_path = r"C:\Users\DW\Desktop\623\永城6.21D端-众包成本-单明细_20260623101319488.xlsx"

    start_time = datetime.now().isoformat()

    field_mapping = load_config(str(config_dir / "field_mapping.yaml"))
    income_rules = load_config(str(config_dir / "income_rules.yaml"))
    delivery_rules = load_config(str(config_dir / "delivery_rules.yaml"))

    food_rows = load_food_billing(food_billing_path, field_mapping)
    retail_rows = load_retail_billing(retail_billing_path, field_mapping)
    crowd_rows = load_crowd_cost(crowd_cost_path, field_mapping)

    all_anomalies = []

    food_income, food_anomalies = compute_income(food_rows, income_rules["food_income_types"])
    all_anomalies.extend(food_anomalies)

    retail_income, retail_anomalies = compute_income(retail_rows, income_rules["retail_income_types"])
    all_anomalies.extend(retail_anomalies)

    food_gross, food_hq_fee, _ = compute_hq_fee(food_rows)
    retail_gross, retail_hq_fee, _ = compute_hq_fee(retail_rows)

    food_delivery, food_del_anomalies = compute_delivery_costs(
        food_rows, crowd_rows,
        delivery_rules["food_delivery_categories"],
        delivery_rules["crowd_cost_matching"]["food_filter"]["is_retail"],
    )
    all_anomalies.extend(food_del_anomalies)

    retail_delivery, retail_del_anomalies = compute_delivery_costs(
        retail_rows, crowd_rows,
        delivery_rules["retail_delivery_categories"],
        delivery_rules["crowd_cost_matching"]["retail_filter"]["is_retail"],
    )
    all_anomalies.extend(retail_del_anomalies)

    food_delivery_total = sum(c.total_cost for c in food_delivery)
    retail_delivery_total = sum(c.total_cost for c in retail_delivery)

    food_income_total = sum(c.total_amount for c in food_income)
    retail_income_total = sum(c.total_amount for c in retail_income)

    food_total_expense = round(food_hq_fee + food_delivery_total, 2)
    retail_total_expense = round(retail_hq_fee + retail_delivery_total, 2)

    food_net = round(food_income_total - food_total_expense, 2)
    retail_net = round(retail_income_total - retail_total_expense, 2)

    reconciliation_checks = run_reconciliation(
        food_income, retail_income,
        food_delivery, retail_delivery,
        food_hq_fee, retail_hq_fee,
        food_rows, retail_rows, crowd_rows,
    )

    all_passed = all(c["passed"] for c in reconciliation_checks)
    has_anomalies = len(all_anomalies) > 0
    status = "SUCCESS" if all_passed and not has_anomalies else ("WARNING" if all_passed else "FAILED")

    run_info = RunInfo(
        run_id="2026-06-21",
        start_time=start_time,
        end_time=datetime.now().isoformat(),
        status=status,
        food_income_total=round(food_income_total, 2),
        retail_income_total=round(retail_income_total, 2),
        food_hq_fee=food_hq_fee,
        retail_hq_fee=retail_hq_fee,
        food_delivery_total=round(food_delivery_total, 2),
        retail_delivery_total=round(retail_delivery_total, 2),
        food_net=food_net,
        retail_net=retail_net,
    )

    file_info = {
        "餐饮账单": get_file_info(food_billing_path),
        "零售账单": get_file_info(retail_billing_path),
        "众包成本": get_file_info(crowd_cost_path),
    }

    summary = RunSummary(
        run_info=run_info,
        food_income_categories=food_income,
        retail_income_categories=retail_income,
        food_delivery_categories=food_delivery,
        retail_delivery_categories=retail_delivery,
        anomalies=all_anomalies,
        reconciliation_checks=reconciliation_checks,
        file_info=file_info,
        raw_row_counts={
            "food": {"raw": 13875, "valid": len(food_rows), "anomaly": 13875 - len(food_rows)},
            "retail": {"raw": 2146, "valid": len(retail_rows), "anomaly": 2146 - len(retail_rows)},
            "crowd": {"raw": 6736, "valid": len(crowd_rows), "anomaly": 6736 - len(crowd_rows)},
        },
    )

    output_dir = base_dir / "runs" / "2026-06-21"
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "永城2026-06-21_收入成本核算结果.xlsx"
    generate_report(summary, str(output_path))

    print(f"=== 运行完成 ===")
    print(f"状态: {status}")
    print(f"餐饮收入: {food_income_total:.2f}")
    print(f"零售收入: {retail_income_total:.2f}")
    print(f"餐饮总部抽点: {food_hq_fee:.2f}")
    print(f"零售总部抽点: {retail_hq_fee:.2f}")
    print(f"餐饮配送成本: {food_delivery_total:.2f}")
    print(f"零售配送成本: {retail_delivery_total:.2f}")
    print(f"餐饮净收入: {food_net:.2f}")
    print(f"零售净收入: {retail_net:.2f}")
    print(f"异常数: {len(all_anomalies)}")
    print(f"对账检查: {sum(1 for c in reconciliation_checks if c['passed'])}/{len(reconciliation_checks)} 通过")
    print(f"输出文件: {output_path}")


def main(argv=None):
    print(
        "DEPRECATED: src.pipeline is the legacy local script and will not run accounting by default.\n"
        "Use: python -m src.cli plan --city guan --input <input-directory> --output <output-directory>\n"
        "Use: python -m src.cli run --city guan --input <input-directory> --output <output-directory> --execute"
    )
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
