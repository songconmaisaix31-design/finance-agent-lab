import hashlib
import json
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

import openpyxl

from src.config import load_city_config


HEADERS = ["日期", "配送状态", "是否零售", "合并区县名称", "is_group_order", "有效完成单", "总成本"]


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def write_crowd_workbook(path: Path, rows: list[dict], *, sheet_name="月", header_row=1, include_header=True):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = sheet_name
    for _ in range(header_row - 1):
        ws.append(["synthetic preface"])
    if include_header:
        ws.append(HEADERS)
    for row in rows:
        ws.append([row.get(h, "") for h in HEADERS])
    wb.save(path)


def bucket_rows():
    return [
        {"日期": "2026-06-23", "配送状态": "配送成功", "是否零售": 0, "合并区县名称": "固安", "is_group_order": 0, "有效完成单": "1", "总成本": "10.00"},
        {"日期": "2026-06-23", "配送状态": "配送成功", "是否零售": 0, "合并区县名称": "固安", "is_group_order": 1, "有效完成单": "2", "总成本": "20.00"},
        {"日期": "2026-06-23", "配送状态": "配送成功", "是否零售": 1, "合并区县名称": "固安", "is_group_order": 0, "有效完成单": "3", "总成本": "30.00"},
        {"日期": "2026-06-23", "配送状态": "配送成功", "是否零售": 1, "合并区县名称": "固安", "is_group_order": 1, "有效完成单": "4", "总成本": "40.00"},
    ]


class TestCrowdCostContract(unittest.TestCase):

    def setUp(self):
        self.cfg = load_city_config("guan")

    def test_extracts_all_existing_buckets_with_decimal_totals(self):
        from src.crowd_cost_contract import CROWD_BUCKET_ORDER, build_crowd_cost_result

        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "crowd_cost.xlsx"
            write_crowd_workbook(path, bucket_rows())
            before = sha256_file(path)
            result = build_crowd_cost_result(path, self.cfg)
            after = sha256_file(path)

        self.assertEqual(before, after)
        self.assertEqual(result["status"], "complete")
        self.assertEqual([b["id"] for b in result["buckets"]], CROWD_BUCKET_ORDER)
        self.assertEqual([b["amount"] for b in result["buckets"]], [Decimal("10.00"), Decimal("20.00"), Decimal("30.00"), Decimal("40.00")])
        self.assertEqual(result["total_amount"], Decimal("100.00"))
        self.assertEqual(result["source_rows"], 4)
        self.assertEqual(result["accepted_rows"], 4)
        self.assertEqual(result["unknown_rows"], [])
        self.assertEqual(result["rejected_rows"], [])

    def test_unknown_rows_are_collected_and_not_bucketed(self):
        from src.crowd_cost_contract import build_crowd_cost_result

        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "crowd_cost.xlsx"
            rows = bucket_rows() + [
                {"日期": "2026-06-23", "配送状态": "配送成功", "是否零售": 9, "合并区县名称": "固安", "is_group_order": 9, "有效完成单": "5", "总成本": "50.00"}
            ]
            write_crowd_workbook(path, rows)
            result = build_crowd_cost_result(path, self.cfg)

        self.assertEqual(result["status"], "blocked")
        self.assertEqual(result["total_amount"], Decimal("100.00"))
        self.assertEqual(len(result["unknown_rows"]), 1)
        self.assertEqual(result["unknown_rows"][0]["error_code"], "CROWD_UNKNOWN_TYPE")
        self.assertNotIn("50.00", json.dumps(result["unknown_rows"], ensure_ascii=False))

    def test_invalid_empty_negative_zero_and_large_amounts_are_characterized(self):
        from src.crowd_cost_contract import build_crowd_cost_result

        large = "999999999999999999999.99"
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "crowd_cost.xlsx"
            rows = [
                {"日期": "2026-06-23", "配送状态": "配送成功", "是否零售": 0, "合并区县名称": "固安", "is_group_order": 0, "有效完成单": "1", "总成本": large},
                {"日期": "2026-06-23", "配送状态": "配送成功", "是否零售": 0, "合并区县名称": "固安", "is_group_order": 1, "有效完成单": "1", "总成本": "-5.50"},
                {"日期": "2026-06-23", "配送状态": "配送成功", "是否零售": 1, "合并区县名称": "固安", "is_group_order": 0, "有效完成单": "1", "总成本": "0"},
                {"日期": "2026-06-23", "配送状态": "配送成功", "是否零售": 1, "合并区县名称": "固安", "is_group_order": 1, "有效完成单": "1", "总成本": "not-money"},
                {"日期": "2026-06-23", "配送状态": "配送成功", "是否零售": 1, "合并区县名称": "固安", "is_group_order": 1, "有效完成单": "1", "总成本": ""},
            ]
            write_crowd_workbook(path, rows)
            result = build_crowd_cost_result(path, self.cfg)

        self.assertEqual(result["status"], "blocked")
        self.assertEqual(result["accepted_rows"], 3)
        self.assertEqual(result["total_amount"], Decimal(large) + Decimal("-5.50") + Decimal("0"))
        self.assertEqual([r["error_code"] for r in result["rejected_rows"]], ["CROWD_AMOUNT_INVALID", "CROWD_AMOUNT_INVALID"])
        self.assertTrue(any(w["code"] == "CROWD_NEGATIVE_AMOUNT_UNVERIFIED" for w in result["warnings"]))
        self.assertTrue(any(w["code"] == "CROWD_ZERO_AMOUNT_UNVERIFIED" for w in result["warnings"]))

    def test_header_can_move_within_detection_range(self):
        from src.crowd_cost_contract import build_crowd_cost_result

        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "crowd_cost.xlsx"
            write_crowd_workbook(path, bucket_rows(), header_row=5)
            result = build_crowd_cost_result(path, self.cfg)

        self.assertEqual(result["status"], "complete")
        self.assertEqual(result["accepted_rows"], 4)

    def test_missing_file_sheet_header_and_empty_tables_have_stable_errors(self):
        from src.crowd_cost_contract import CrowdCostError, build_crowd_cost_result

        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            with self.assertRaises(CrowdCostError) as missing:
                build_crowd_cost_result(base / "missing.xlsx", self.cfg)
            self.assertEqual(missing.exception.error_code, "CROWD_FILE_NOT_FOUND")

            wrong_sheet = base / "wrong_sheet.xlsx"
            write_crowd_workbook(wrong_sheet, bucket_rows(), sheet_name="not_month")
            with self.assertRaises(CrowdCostError) as sheet:
                build_crowd_cost_result(wrong_sheet, self.cfg)
            self.assertEqual(sheet.exception.error_code, "CROWD_SHEET_MISSING")

            no_header = base / "no_header.xlsx"
            write_crowd_workbook(no_header, bucket_rows(), include_header=False)
            with self.assertRaises(CrowdCostError) as header:
                build_crowd_cost_result(no_header, self.cfg)
            self.assertEqual(header.exception.error_code, "CROWD_HEADER_INVALID")

            header_only = base / "header_only.xlsx"
            write_crowd_workbook(header_only, [])
            empty = build_crowd_cost_result(header_only, self.cfg)
            self.assertEqual(empty["status"], "complete")
            self.assertEqual(empty["source_rows"], 0)

    def test_missing_required_field_is_header_invalid(self):
        from src.crowd_cost_contract import CrowdCostError, build_crowd_cost_result

        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "missing_field.xlsx"
            wb = openpyxl.Workbook()
            ws = wb.active
            ws.title = "月"
            ws.append(["日期", "配送状态", "是否零售", "合并区县名称", "is_group_order", "有效完成单"])
            wb.save(path)
            with self.assertRaises(CrowdCostError) as ctx:
                build_crowd_cost_result(path, self.cfg)
        self.assertEqual(ctx.exception.error_code, "CROWD_HEADER_INVALID")

    def test_corrupted_workbook_has_stable_error(self):
        from src.crowd_cost_contract import CrowdCostError, build_crowd_cost_result

        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "corrupted.xlsx"
            path.write_text("not an excel workbook", encoding="utf-8")
            with self.assertRaises(CrowdCostError) as ctx:
                build_crowd_cost_result(path, self.cfg)
        self.assertEqual(ctx.exception.error_code, "CROWD_FILE_INVALID")

    def test_repeated_rows_are_not_deduplicated_current_behavior(self):
        from src.crowd_cost_contract import build_crowd_cost_result

        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "crowd_cost.xlsx"
            write_crowd_workbook(path, [bucket_rows()[0], bucket_rows()[0]])
            result = build_crowd_cost_result(path, self.cfg)

        bucket = result["buckets"][0]
        self.assertEqual(bucket["id"], "catering_normal")
        self.assertEqual(bucket["amount"], Decimal("20.00"))
        self.assertEqual(bucket["completed_orders"], Decimal("2"))
        self.assertTrue(any(w["code"] == "CROWD_DEDUP_POLICY_UNVERIFIED" for w in result["warnings"]))


if __name__ == "__main__":
    unittest.main()
