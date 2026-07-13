import csv
import json
import os
from decimal import Decimal, InvalidOperation

import openpyxl


REQUIRED_CROWD_FIELDS = [
    "日期", "配送状态", "是否零售", "合并区县名称",
    "is_group_order", "有效完成单", "总成本",
]


def _normalize(v):
    if v is None:
        return ""
    return str(v).strip()


def _detect_crowd_columns(filepath: str, sheet_name: str, field_names: list[str]) -> dict:
    """Detect header row and return column index map using read_only streaming."""
    wb = openpyxl.load_workbook(filepath, read_only=True, data_only=True)
    try:
        ws = wb[sheet_name]
    except KeyError:
        wb.close()
        raise

    header_row = -1
    col_map = {}

    for row_idx, row in enumerate(ws.iter_rows(max_row=15, values_only=False), start=1):
        if row_idx > 15:
            break
        row_vals = [_normalize(cell.value) for cell in row]
        found = sum(1 for f in REQUIRED_CROWD_FIELDS if f in row_vals)
        if found >= len(REQUIRED_CROWD_FIELDS) - 1:
            header_row = row_idx
            for fn in field_names:
                for ci, hv in enumerate(row_vals):
                    if hv == fn:
                        col_map[fn] = ci
                        break
            break

    wb.close()

    if header_row < 0:
        raise ValueError(f"Could not detect header in {filepath} sheet '{sheet_name}'")

    missing = [fn for fn in field_names if fn not in col_map]
    if missing:
        raise ValueError(f"Missing fields in '{sheet_name}': {missing}")

    return col_map, header_row


def _parse_int_flag(value, field_name: str) -> tuple[int | None, str | None]:
    if value is None or str(value).strip() == "":
        return None, f"{field_name}:empty"
    try:
        return int(float(str(value))), None
    except (ValueError, TypeError):
        return None, f"{field_name}:invalid_integer"


def _parse_decimal(value, field_name: str) -> tuple[Decimal | None, str | None]:
    if value is None or str(value).strip() == "":
        return None, f"{field_name}:empty"
    try:
        return Decimal(str(value)), None
    except (InvalidOperation, ValueError):
        return None, f"{field_name}:invalid_decimal"


def load_crowd_cost_rows_fast(filepath: str, sheet_name: str, col_map: dict, data_start_row: int) -> list[dict]:
    """Load crowd cost rows using read_only streaming with max_col optimization."""
    wb = openpyxl.load_workbook(filepath, read_only=True, data_only=True)
    try:
        ws = wb[sheet_name]
    except KeyError:
        wb.close()
        raise

    col_date = col_map["日期"]
    col_status = col_map["配送状态"]
    col_retail = col_map["是否零售"]
    col_city = col_map["合并区县名称"]
    col_group = col_map["is_group_order"]
    col_completed = col_map["有效完成单"]
    col_cost = col_map["总成本"]

    max_col_needed = max(col_date, col_status, col_retail, col_city,
                         col_group, col_completed, col_cost) + 1

    rows = []
    for r_idx, row_vals in enumerate(
        ws.iter_rows(min_row=data_start_row, max_col=max_col_needed, values_only=True),
        start=data_start_row,
    ):
        if all(v is None or str(v).strip() == "" for v in row_vals[:5]):
            continue

        date_val = _normalize(row_vals[col_date] if len(row_vals) > col_date else None)

        parse_errors = []
        is_retail, err = _parse_int_flag(row_vals[col_retail] if len(row_vals) > col_retail else None, "is_retail")
        if err:
            parse_errors.append(err)

        is_group, err = _parse_int_flag(row_vals[col_group] if len(row_vals) > col_group else None, "is_group_order")
        if err:
            parse_errors.append(err)

        completed, err = _parse_decimal(row_vals[col_completed] if len(row_vals) > col_completed else None, "completed_orders")
        if err:
            parse_errors.append(err)

        total_cost, err = _parse_decimal(row_vals[col_cost] if len(row_vals) > col_cost else None, "total_cost")
        if err:
            parse_errors.append(err)

        rows.append({
            "source_file": os.path.basename(filepath),
            "source_sheet": sheet_name,
            "source_row": r_idx,
            "date": date_val,
            "delivery_status": _normalize(row_vals[col_status] if len(row_vals) > col_status else None),
            "is_retail": is_retail,
            "city": _normalize(row_vals[col_city] if len(row_vals) > col_city else None),
            "is_group_order": is_group,
            "completed_orders": completed,
            "total_cost": total_cost,
            "parse_errors": parse_errors,
        })

    wb.close()
    return rows


def write_crowd_cost_csv_fast(rows: list[dict], output_path: str):
    fieldnames = [
        "source_file", "source_sheet", "source_row",
        "date", "delivery_status", "is_retail", "city",
        "is_group_order", "completed_orders", "total_cost",
    ]
    with open(output_path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for r in rows:
            r_out = {k: r.get(k, "") for k in fieldnames}
            r_out["completed_orders"] = str(r_out["completed_orders"])
            r_out["total_cost"] = str(r_out["total_cost"])
            writer.writerow(r_out)
