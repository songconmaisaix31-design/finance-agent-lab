import json
import os
from datetime import datetime
from decimal import Decimal

import openpyxl
from openpyxl.styles import Font, Alignment, PatternFill, Border, Side, numbers
from openpyxl.utils import get_column_letter


HEADER_FILL = PatternFill(start_color="4472C4", end_color="4472C4", fill_type="solid")
HEADER_FONT = Font(name="Microsoft YaHei", size=10, bold=True, color="FFFFFF")
TITLE_FONT = Font(name="Microsoft YaHei", size=14, bold=True)
NORMAL_FONT = Font(name="Microsoft YaHei", size=10)
BOLD_FONT = Font(name="Microsoft YaHei", size=10, bold=True)
RED_FONT = Font(name="Microsoft YaHei", size=10, bold=True, color="FF0000")
WARNING_FILL = PatternFill(start_color="FFF2CC", end_color="FFF2CC", fill_type="solid")
THIN_BORDER = Border(
    left=Side(style="thin"),
    right=Side(style="thin"),
    top=Side(style="thin"),
    bottom=Side(style="thin"),
)


def _format_decimal(d, precision=2):
    if d is None:
        return ""
    return round(Decimal(str(d)), precision)


def _write_header(ws, row, headers):
    for col, h in enumerate(headers, 1):
        cell = ws.cell(row=row, column=col, value=h)
        cell.font = HEADER_FONT
        cell.fill = HEADER_FILL
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        cell.border = THIN_BORDER


def _write_row(ws, row, values, bold=False, red=False):
    for col, v in enumerate(values, 1):
        cell = ws.cell(row=row, column=col, value=v)
        cell.font = RED_FONT if red else (BOLD_FONT if bold else NORMAL_FONT)
        cell.alignment = Alignment(vertical="center")
        cell.border = THIN_BORDER
        if isinstance(v, (int, float, Decimal)):
            cell.alignment = Alignment(horizontal="right", vertical="center")


def _auto_width(ws):
    for col_cells in ws.columns:
        max_len = 0
        col_letter = get_column_letter(col_cells[0].column)
        for cell in col_cells:
            if cell.value:
                max_len = max(max_len, len(str(cell.value)))
        ws.column_dimensions[col_letter].width = min(max_len + 4, 40)


def generate_report(
    output_path: str,
    run_info: dict,
    food_income: dict,
    retail_income: dict,
    food_hq: dict,
    retail_hq: dict,
    food_team: dict,
    retail_team: dict,
    crowd_buckets: dict,
    bill_cost_comparisons: list,
    crowd_reconciliation: dict,
    food_unknown: list,
    retail_unknown: list,
    food_invalid: list,
    retail_invalid: list,
    unknown_delivery: list,
    recon_result: dict,
    flagged_subsidy_rows: list = None,
):
    wb = openpyxl.Workbook()

    _sheet_01_overview(wb, run_info, food_income, retail_income,
                       food_hq, retail_hq, food_team, retail_team,
                       crowd_buckets, recon_result)
    _sheet_02_food_income(wb, food_income)
    _sheet_03_retail_income(wb, retail_income)
    _sheet_04_food_expense(wb, food_hq, food_team, crowd_buckets, "catering")
    _sheet_05_retail_expense(wb, retail_hq, retail_team, crowd_buckets, "retail")
    _sheet_06_crowd_cost_detail(wb, crowd_buckets)
    _sheet_07_bill_cost_comparison(wb, bill_cost_comparisons)
    _sheet_08_cost_table_reconciliation(wb, crowd_reconciliation)
    _sheet_09_unknown_income(wb, food_unknown, retail_unknown)
    _sheet_10_unknown_delivery(wb, unknown_delivery)
    _sheet_11_anomalies(wb, food_invalid, retail_invalid, food_unknown, retail_unknown)
    _sheet_12_run_info(wb, run_info)
    _sheet_13_auto_recon(wb, recon_result)
    _sheet_14_no_subsidy(wb, flagged_subsidy_rows or [])

    if "Sheet" in wb.sheetnames:
        del wb["Sheet"]

    wb.save(output_path)


def _sheet_01_overview(wb, run_info, food_income, retail_income,
                       food_hq, retail_hq, food_team, retail_team,
                       crowd_buckets, recon):
    ws = wb.active
    ws.title = "01_总览"

    r = 1
    ws.cell(row=r, column=1, value=f"固安 2026-06-23 收入成本核算总览").font = TITLE_FONT
    ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=4)
    r += 2

    headers = ["项目", "餐饮", "零售", "说明"]
    _write_header(ws, r, headers)
    r += 1

    food_income_total = food_income["total_settlement"]
    retail_income_total = retail_income["total_settlement"]

    food_gross = food_income["total_gross"]
    retail_gross = retail_income["total_gross"]

    food_hq_fee = food_hq["hq_fee"]
    retail_hq_fee = retail_hq["hq_fee"]

    food_team_group = food_team["team_group"]["total_cost"]
    food_team_normal = food_team["team_normal"]["total_cost"]
    retail_team_group = retail_team["team_group"]["total_cost"]
    retail_team_normal = retail_team["team_normal"]["total_cost"]

    food_team_total = food_team["total_team_cost"]
    retail_team_total = retail_team["total_team_cost"]

    def cc(key):
        b = crowd_buckets.get(key, {})
        return b.get("final_cost", b.get("cost_table_total_cost", Decimal("0")))

    food_crowd_normal = cc("catering_normal")
    food_crowd_group = cc("catering_group")
    retail_crowd_normal = cc("retail_normal")
    retail_crowd_group = cc("retail_group")

    food_total_expense = food_hq_fee + food_team_total + food_crowd_normal + food_crowd_group
    retail_total_expense = retail_hq_fee + retail_team_total + retail_crowd_normal + retail_crowd_group

    food_net = food_income_total - food_total_expense
    retail_net = retail_income_total - retail_total_expense

    rows_data = [
        ("收入", f2(food_income_total), f2(retail_income_total), "结算金额合计"),
        ("  去重订单量", food_income["total_distinct_orders"], retail_income["total_distinct_orders"], ""),
        ("毛交易额", f2(food_gross), f2(retail_gross), "收入白名单内"),
        ("总部抽点", f2(food_hq_fee), f2(retail_hq_fee), "毛交易额×1%"),
        ("专送拼团成本", f2(food_team_group), f2(retail_team_group), f"单均{food_team['team_group']['unit_cost']}元"),
        ("专送正常单成本", f2(food_team_normal), f2(retail_team_normal), f"单均{food_team['team_normal']['unit_cost']}元"),
        ("众包拼团成本", f2(food_crowd_group), f2(retail_crowd_group), "来自成本表"),
        ("众包正常单成本", f2(food_crowd_normal), f2(retail_crowd_normal), "来自成本表"),
        ("总支出", f2(food_total_expense), f2(retail_total_expense), ""),
        ("收入减支出", f2(food_net), f2(retail_net), ""),
    ]

    for label, fv, rv, note in rows_data:
        _write_row(ws, r, [label, fv, rv, note], bold=(label in ("收入", "总支出", "收入减支出")))
        r += 1

    _auto_width(ws)
    ws.freeze_panes = "A3"


def _sheet_02_food_income(wb, income):
    ws = wb.create_sheet("02_餐饮收入")
    r = 1
    ws.cell(row=r, column=1, value="餐饮收入明细").font = TITLE_FONT
    r += 2
    headers = ["服务包类型", "账单行数", "去重订单量", "结算金额", "毛交易额", "单均收入"]
    _write_header(ws, r, headers)
    r += 1

    for c in income["categories"]:
        _write_row(ws, r, [
            c["service_package"],
            c["row_count"],
            c["distinct_order_count"],
            f2(c["total_settlement"]),
            f2(c["total_gross"]),
            f2(c["avg_per_order"]),
        ])
        r += 1

    _write_row(ws, r, ["合计", sum(c["row_count"] for c in income["categories"]),
                       income["total_distinct_orders"],
                       f2(income["total_settlement"]),
                       f2(income["total_gross"]), ""], bold=True)
    _auto_width(ws)
    ws.freeze_panes = "A3"


def _sheet_03_retail_income(wb, income):
    ws = wb.create_sheet("03_零售收入")
    r = 1
    ws.cell(row=r, column=1, value="零售收入明细").font = TITLE_FONT
    r += 2
    headers = ["服务包类型", "账单行数", "去重订单量", "结算金额", "毛交易额", "单均收入"]
    _write_header(ws, r, headers)
    r += 1

    for c in income["categories"]:
        _write_row(ws, r, [
            c["service_package"],
            c["row_count"],
            c["distinct_order_count"],
            f2(c["total_settlement"]),
            f2(c["total_gross"]),
            f2(c["avg_per_order"]),
        ])
        r += 1

    _write_row(ws, r, ["合计", sum(c["row_count"] for c in income["categories"]),
                       income["total_distinct_orders"],
                       f2(income["total_settlement"]),
                       f2(income["total_gross"]), ""], bold=True)
    _auto_width(ws)
    ws.freeze_panes = "A3"


def _sheet_04_food_expense(wb, hq, team, buckets, prefix):
    ws = wb.create_sheet("04_餐饮支出")
    r = 1
    ws.cell(row=r, column=1, value="餐饮支出明细").font = TITLE_FONT
    r += 2
    headers = ["支出项目", "订单量/说明", "单均成本", "金额"]
    _write_header(ws, r, headers)
    r += 1

    _write_row(ws, r, ["总部抽点", f"毛交易额{f2(hq['total_gross_in_scope'])}", "1%", f2(hq["hq_fee"])])
    r += 1

    tg = team["team_group"]
    _write_row(ws, r, ["专送拼团", tg["distinct_order_count"], f2(tg["unit_cost"]), f2(tg["total_cost"])])
    r += 1

    tn = team["team_normal"]
    _write_row(ws, r, ["专送正常单", tn["distinct_order_count"], f2(tn["unit_cost"]), f2(tn["total_cost"])])
    r += 1

    cg = buckets.get(f"{prefix}_group", {})
    cn = buckets.get(f"{prefix}_normal", {})

    cg_cost = cg.get("final_cost", cg.get("cost_table_total_cost", Decimal("0")))
    cg_count = cg.get("final_order_count", cg.get("cost_table_completed_orders", Decimal("0")))
    cg_avg = cg.get("final_avg_cost", cg.get("avg_cost_per_order", Decimal("0")))
    cn_cost = cn.get("final_cost", cn.get("cost_table_total_cost", Decimal("0")))
    cn_count = cn.get("final_order_count", cn.get("cost_table_completed_orders", Decimal("0")))
    cn_avg = cn.get("final_avg_cost", cn.get("avg_cost_per_order", Decimal("0")))

    _write_row(ws, r, ["众包拼团", str(cg_count), f2(cg_avg), f2(cg_cost)])
    r += 1
    _write_row(ws, r, ["众包正常单", str(cn_count), f2(cn_avg), f2(cn_cost)])
    r += 1

    total = hq["hq_fee"] + team["total_team_cost"] + cg_cost + cn_cost
    _write_row(ws, r, ["合计", "", "", f2(total)], bold=True)
    _auto_width(ws)
    ws.freeze_panes = "A3"


def _sheet_05_retail_expense(wb, hq, team, buckets, prefix):
    ws = wb.create_sheet("05_零售支出")
    r = 1
    ws.cell(row=r, column=1, value="零售支出明细").font = TITLE_FONT
    r += 2
    headers = ["支出项目", "订单量/说明", "单均成本", "金额"]
    _write_header(ws, r, headers)
    r += 1

    _write_row(ws, r, ["总部抽点", f"毛交易额{f2(hq['total_gross_in_scope'])}", "1%", f2(hq["hq_fee"])])
    r += 1

    tg = team["team_group"]
    _write_row(ws, r, ["专送拼团", tg["distinct_order_count"], f2(tg["unit_cost"]), f2(tg["total_cost"])])
    r += 1

    tn = team["team_normal"]
    _write_row(ws, r, ["专送正常单", tn["distinct_order_count"], f2(tn["unit_cost"]), f2(tn["total_cost"])])
    r += 1

    cg = buckets.get(f"{prefix}_group", {})
    cn = buckets.get(f"{prefix}_normal", {})

    cg_cost = cg.get("final_cost", cg.get("cost_table_total_cost", Decimal("0")))
    cg_count = cg.get("final_order_count", cg.get("cost_table_completed_orders", Decimal("0")))
    cg_avg = cg.get("final_avg_cost", cg.get("avg_cost_per_order", Decimal("0")))
    cn_cost = cn.get("final_cost", cn.get("cost_table_total_cost", Decimal("0")))
    cn_count = cn.get("final_order_count", cn.get("cost_table_completed_orders", Decimal("0")))
    cn_avg = cn.get("final_avg_cost", cn.get("avg_cost_per_order", Decimal("0")))

    _write_row(ws, r, ["众包拼团", str(cg_count), f2(cg_avg), f2(cg_cost)])
    r += 1
    _write_row(ws, r, ["众包正常单", str(cn_count), f2(cn_avg), f2(cn_cost)])
    r += 1

    total = hq["hq_fee"] + team["total_team_cost"] + cg_cost + cn_cost
    _write_row(ws, r, ["合计", "", "", f2(total)], bold=True)
    _auto_width(ws)
    ws.freeze_panes = "A3"


def _sheet_06_crowd_cost_detail(wb, buckets):
    ws = wb.create_sheet("06_众包成本分层")
    r = 1
    ws.cell(row=r, column=1, value="众包成本分层明细").font = TITLE_FONT
    r += 2
    headers = ["业务板块", "成本类别", "是否零售", "是否拼团", "正向单量(账单)", "最终成本", "单均成本", "成本表参考单量", "成本表参考成本", "来源"]
    _write_header(ws, r, headers)
    r += 1

    data = [
        ("餐饮", "众包正常单", "0", "0", "catering_normal"),
        ("餐饮", "众包拼团", "0", "1", "catering_group"),
        ("零售", "众包正常单", "1", "0", "retail_normal"),
        ("零售", "众包拼团", "1", "1", "retail_group"),
    ]

    for biz, cat, is_retail, is_group, key in data:
        b = buckets.get(key, {})
        _write_row(ws, r, [
            biz, cat, is_retail, is_group,
            str(b.get("final_order_count", b.get("cost_table_completed_orders", "0"))),
            f2(b.get("final_cost", b.get("cost_table_total_cost", Decimal("0")))),
            f2(b.get("final_avg_cost", b.get("avg_cost_per_order", Decimal("0")))),
            str(b.get("cost_table_completed_orders", "0")),
            f2(b.get("cost_table_total_cost", "0")),
            "周对比(第二周单均3.76)",
        ])
        r += 1

    _auto_width(ws)
    ws.freeze_panes = "A3"


def _sheet_07_bill_cost_comparison(wb, comparisons):
    ws = wb.create_sheet("07_账单成本单量对账")
    r = 1
    ws.cell(row=r, column=1, value="账单与成本表单量对账").font = TITLE_FONT
    r += 2
    headers = ["业务板块", "成本类别", "账单正向去重订单量", "成本表有效完成单", "单量差异", "单量差异率", "最终众包成本", "单均成本", "对账状态", "说明"]
    _write_header(ws, r, headers)
    r += 1

    for c in comparisons:
        status = c.get("status", "")
        _write_row(ws, r, [
            c["business"],
            c["category"],
            c["bill_positive_order_count"],
            c["cost_table_completed_orders"],
            c["count_difference"],
            c["count_difference_rate"],
            c["crowd_cost_final"],
            c["crowd_cost_avg"],
            status,
            "单量不一致，请人工确认" if status == "WARNING" else "一致",
        ], red=(status == "WARNING"))
        r += 1

    _auto_width(ws)
    ws.freeze_panes = "A3"


def _sheet_08_cost_table_reconciliation(wb, recon):
    ws = wb.create_sheet("08_成本表内部对账")
    r = 1
    ws.cell(row=r, column=1, value="成本表内部对账（月 vs 整体）").font = TITLE_FONT
    r += 2
    headers = ["检查项", "是否通过", "月表值", "整体表值"]
    _write_header(ws, r, headers)
    r += 1

    for c in recon.get("checks", []):
        passed = "通过" if c.get("passed") else "失败"
        _write_row(ws, r, [
            c.get("check", ""),
            passed,
            str(c.get("month_value", "")),
            str(c.get("check_value", "")),
        ], red=(not c.get("passed")))
        r += 1

    _write_row(ws, r, [
        "内部对账结果",
        "通过" if recon.get("all_passed") else "失败",
        "", "",
    ], bold=True, red=(not recon.get("all_passed")))
    _auto_width(ws)
    ws.freeze_panes = "A3"


def _sheet_09_unknown_income(wb, food_unknown, retail_unknown):
    ws = wb.create_sheet("09_未配置收入类型")
    r = 1
    ws.cell(row=r, column=1, value="未配置收入类型").font = TITLE_FONT
    r += 2
    headers = ["业务板块", "服务包类型", "账单行数", "去重订单量", "结算金额", "毛交易额"]
    _write_header(ws, r, headers)
    r += 1

    for u in food_unknown:
        _write_row(ws, r, ["餐饮", u["service_package"], u["row_count"], u["distinct_order_count"], f2(u["total_settlement"]), f2(u["total_gross"])])
        r += 1
    for u in retail_unknown:
        _write_row(ws, r, ["零售", u["service_package"], u["row_count"], u["distinct_order_count"], f2(u["total_settlement"]), f2(u["total_gross"])])
        r += 1

    if not food_unknown and not retail_unknown:
        _write_row(ws, r, ["无", "", "", "", "", ""])
    _auto_width(ws)
    ws.freeze_panes = "A3"


def _sheet_10_unknown_delivery(wb, unknown_delivery):
    ws = wb.create_sheet("10_未识别配送类型")
    r = 1
    ws.cell(row=r, column=1, value="未识别配送类型").font = TITLE_FONT
    r += 2
    headers = ["业务板块", "配送方式", "出现次数"]
    _write_header(ws, r, headers)
    r += 1

    for u in unknown_delivery:
        _write_row(ws, r, [u["business"], u["delivery_type"], u["count"]])
        r += 1

    if not unknown_delivery:
        _write_row(ws, r, ["无", "", ""])
    _auto_width(ws)
    ws.freeze_panes = "A3"


def _sheet_11_anomalies(wb, food_invalid, retail_invalid, food_unknown, retail_unknown):
    ws = wb.create_sheet("11_异常数据")
    r = 1
    ws.cell(row=r, column=1, value="异常数据汇总").font = TITLE_FONT
    r += 2

    headers = ["类型", "来源文件", "行号", "订单号", "详细信息"]
    _write_header(ws, r, headers)
    r += 1

    for inv in food_invalid:
        _write_row(ws, r, ["无效金额", inv.get("source_file", ""), inv.get("source_row", ""), inv.get("order_id", ""), inv.get("error", "")])
        r += 1

    for inv in retail_invalid:
        _write_row(ws, r, ["无效金额", inv.get("source_file", ""), inv.get("source_row", ""), inv.get("order_id", ""), inv.get("error", "")])
        r += 1

    for u in food_unknown:
        _write_row(ws, r, ["未配置收入类型(餐饮)", "", "", "", u["service_package"]])
        r += 1

    for u in retail_unknown:
        _write_row(ws, r, ["未配置收入类型(零售)", "", "", "", u["service_package"]])
        r += 1

    if not food_invalid and not retail_invalid and not food_unknown and not retail_unknown:
        _write_row(ws, r, ["无异常", "", "", "", ""])

    _auto_width(ws)
    ws.freeze_panes = "A3"


def _sheet_12_run_info(wb, run_info):
    ws = wb.create_sheet("12_运行信息")
    r = 1
    ws.cell(row=r, column=1, value="运行信息").font = TITLE_FONT
    r += 2
    headers = ["参数", "值"]
    _write_header(ws, r, headers)
    r += 1

    for k, v in run_info.items():
        _write_row(ws, r, [str(k), str(v)])
        r += 1

    _auto_width(ws)
    ws.freeze_panes = "A3"


def _sheet_13_auto_recon(wb, recon):
    ws = wb.create_sheet("13_自动对账结果")
    r = 1
    ws.cell(row=r, column=1, value="自动对账结果").font = TITLE_FONT
    r += 2
    headers = ["检查项", "是否通过", "期望值", "实际值"]
    _write_header(ws, r, headers)
    r += 1

    all_checks = (
        recon.get("income_checks", []) +
        recon.get("team_cost_checks", []) +
        recon.get("crowd_cost_checks", [])
    )

    for c in all_checks:
        passed = "通过" if c.get("passed") else "失败"
        _write_row(ws, r, [
            c.get("check", ""),
            passed,
            str(c.get("expected", "")),
            str(c.get("actual", "")),
        ], red=(not c.get("passed")))
        r += 1

    for cmp in recon.get("bill_cost_comparisons", []):
        _write_row(ws, r, [
            f"单量对账_{cmp.get('category', '')}",
            cmp.get("status", ""),
            str(cmp.get("bill_distinct_order_count", "")),
            cmp.get("cost_table_completed_orders", ""),
        ], red=(cmp.get("status") == "WARNING"))
        r += 1

    _write_row(ws, r, [
        "文件完整性", "通过" if recon.get("file_integrity_ok") else "失败", "", "",
    ], bold=True, red=(not recon.get("file_integrity_ok")))
    r += 1
    _write_row(ws, r, [
        "总体对账", "通过" if recon.get("all_passed") else "存在差异", "", "",
    ], bold=True, red=(not recon.get("all_passed")))

    _auto_width(ws)
    ws.freeze_panes = "A3"


def _sheet_14_no_subsidy(wb, flagged_rows):
    ws = wb.create_sheet("14_自配送到店自取三方代补警告")
    r = 1
    ws.cell(row=r, column=1, value="代理商配送费活动补贴异常（到店自取/专送/选推不应有三方代补）").font = TITLE_FONT
    r += 2
    headers = ["业务板块", "配送方式", "服务包类型", "订单号", "代理商配送费活动补贴", "结算金额", "原始行号", "来源文件"]
    _write_header(ws, r, headers)
    r += 1

    if not flagged_rows:
        _write_row(ws, r, ["无异常", "", "", "", "", "", "", "以上配送方式均无代理商配送费活动补贴"])
        _auto_width(ws)
        ws.freeze_panes = "A3"
        return

    total_subsidy = Decimal("0")
    for row in flagged_rows:
        subsidy = row.get("subsidy", Decimal("0"))
        total_subsidy += subsidy
        _write_row(ws, r, [
            row["business"],
            row["delivery_type"],
            row["service_package"],
            row["order_id"],
            f2(subsidy),
            f2(row.get("settlement_amount", Decimal("0"))),
            row["source_row"],
            row["source_file"],
        ], red=True)
        r += 1

    _write_row(ws, r, [
        "合计", "", "", "",
        f2(total_subsidy), "", "", f"共{len(flagged_rows)}笔异常",
    ], bold=True, red=True)

    _auto_width(ws)
    ws.freeze_panes = "A3"


def f2(d):
    if d is None:
        return ""
    return float(round(Decimal(str(d)), 2))
