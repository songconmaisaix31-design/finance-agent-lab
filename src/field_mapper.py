import openpyxl
from dataclasses import dataclass, field


REQUIRED_BILL_FIELDS = [
    "账单日期", "结算金额", "订单号", "配送方式",
    "服务包类型", "毛交易额", "净交易额",
]

OPTIONAL_BILL_FIELDS = [
    "订单类型", "业务类型", "商户ID", "商户名称",
    "订单完成时间", "备注", "代理商配送费活动补贴",
]

REQUIRED_CROWD_FIELDS = [
    "日期", "配送状态", "是否零售", "合并区县名称",
    "is_group_order", "有效完成单", "总成本",
]


@dataclass
class FieldMapping:
    source_file: str
    source_sheet: str
    header_row: int
    data_start_row: int
    column_map: dict


def normalize_header_name(name):
    if name is None:
        return ""
    return str(name).strip().replace("\n", "").replace("\r", "")


def detect_header_row(ws, required_fields: list[str], search_range: int = 10) -> int:
    for row_idx in range(1, search_range + 1):
        row_vals = []
        for cell in list(ws.iter_rows(min_row=row_idx, max_row=row_idx))[0]:
            row_vals.append(normalize_header_name(cell.value))

        found = 0
        for rf in required_fields:
            if rf in row_vals:
                found += 1

        if found >= len(required_fields) - 1:
            return row_idx

    return -1


def build_field_mapping(ws, header_row: int, field_names: list[str]) -> dict:
    header_cells = list(ws.iter_rows(min_row=header_row, max_row=header_row))[0]
    header_vals = [normalize_header_name(cell.value) for cell in header_cells]

    col_map = {}
    missing = []

    for fn in field_names:
        found = False
        for idx, hv in enumerate(header_vals):
            if hv == fn:
                col_map[fn] = idx
                found = True
                break
        if not found:
            missing.append(fn)

    return col_map, missing


def map_billing_sheet(filepath: str, sheet_name: str = None) -> FieldMapping:
    wb = openpyxl.load_workbook(filepath, data_only=True)
    ws = wb[sheet_name] if sheet_name else wb.active
    sheet = ws.title

    header_row = detect_header_row(ws, REQUIRED_BILL_FIELDS)

    if header_row < 0:
        wb.close()
        raise ValueError(f"Could not detect bill header row in {filepath}")

    all_fields = REQUIRED_BILL_FIELDS + OPTIONAL_BILL_FIELDS
    col_map, missing = build_field_mapping(ws, header_row, all_fields)

    critical_missing = [m for m in missing if m in REQUIRED_BILL_FIELDS]
    if critical_missing:
        wb.close()
        raise ValueError(f"Missing required fields in {filepath}: {critical_missing}")

    wb.close()
    return FieldMapping(
        source_file=filepath,
        source_sheet=sheet,
        header_row=header_row,
        data_start_row=header_row + 1,
        column_map=col_map,
    )


def map_crowd_cost_sheet(filepath: str, sheet_name: str, field_names: list[str]) -> FieldMapping:
    wb = openpyxl.load_workbook(filepath, data_only=True)
    ws = wb[sheet_name]

    header_row = detect_header_row(ws, REQUIRED_CROWD_FIELDS)

    if header_row < 0:
        wb.close()
        raise ValueError(f"Could not detect crowd cost header in {filepath} sheet '{sheet_name}'")

    col_map, missing = build_field_mapping(ws, header_row, field_names)

    if missing:
        wb.close()
        raise ValueError(f"Missing required fields in crowd cost sheet '{sheet_name}': {missing}")

    wb.close()
    return FieldMapping(
        source_file=filepath,
        source_sheet=sheet_name,
        header_row=header_row,
        data_start_row=header_row + 1,
        column_map=col_map,
    )
