"""
Minimal verification tests for 固安 2026-06-23 accounting harness.
"""
import os
import sys
import tempfile
import unittest
from decimal import Decimal

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.config import load_city_config
from src.normalizer import parse_decimal, NormalizedBillingRow
from src.income_calc import compute_income
from src.fee_calc import compute_hq_fee, compute_team_delivery_cost
from src.manifest import sha256_file


class TestConfig(unittest.TestCase):

    def test_load_guan_config(self):
        cfg = load_city_config("guan")
        self.assertEqual(cfg["city_name"], "固安")
        self.assertEqual(cfg["agent_id"], "342")
        self.assertEqual(cfg["billing_date"], "2026-06-23")
        self.assertIn("food_income_whitelist", cfg)
        self.assertIn("retail_income_whitelist", cfg)
        self.assertEqual(len(cfg["food_income_whitelist"]), 7)
        self.assertEqual(len(cfg["retail_income_whitelist"]), 6)

    def test_decimal_conversion(self):
        self.assertEqual(cfg("_headquarters_fee_rate_d"), Decimal("0.01"))
        self.assertEqual(cfg("_team_group_unit_cost_d"), Decimal("4.60"))


class TestParseDecimal(unittest.TestCase):

    def test_valid_number(self):
        d, ok, err = parse_decimal("123.45")
        self.assertTrue(ok)
        self.assertEqual(d, Decimal("123.45"))

    def test_negative_number(self):
        d, ok, err = parse_decimal("-5.00")
        self.assertTrue(ok)
        self.assertEqual(d, Decimal("-5.00"))

    def test_empty(self):
        d, ok, err = parse_decimal("")
        self.assertFalse(ok)

    def test_none(self):
        d, ok, err = parse_decimal(None)
        self.assertFalse(ok)

    def test_invalid(self):
        d, ok, err = parse_decimal("not_a_number")
        self.assertFalse(ok)


class TestIncomeCalculation(unittest.TestCase):

    def setUp(self):
        self.whitelist = [
            {"service_package": "代理商E配送"},
            {"service_package": "城代拼团"},
        ]
        self.r1 = NormalizedBillingRow(
            source_file="test.xlsx", source_sheet="Sheet0", source_row=5,
            billing_date="2026-06-23", business_category="餐饮",
            order_id="12345", order_type="正常", delivery_type="蜂鸟团队",
            service_package_type="代理商E配送",
            settlement_amount=Decimal("10.00"),
            gross_transaction_amount=Decimal("50.00"),
            net_transaction_amount=Decimal("40.00"),
            merchant_id="M1", merchant_name="M1",
            completed_at="", remark="",
        )
        self.r2 = NormalizedBillingRow(
            source_file="test.xlsx", source_sheet="Sheet0", source_row=6,
            billing_date="2026-06-23", business_category="餐饮",
            order_id="12345", order_type="退款", delivery_type="蜂鸟团队",
            service_package_type="代理商E配送",
            settlement_amount=Decimal("-3.00"),
            gross_transaction_amount=Decimal("-15.00"),
            net_transaction_amount=Decimal("-12.00"),
            merchant_id="M1", merchant_name="M1",
            completed_at="", remark="",
        )
        self.r3 = NormalizedBillingRow(
            source_file="test.xlsx", source_sheet="Sheet0", source_row=7,
            billing_date="2026-06-23", business_category="餐饮",
            order_id="99999", order_type="正常", delivery_type="蜂鸟团队",
            service_package_type="城代选推高级KA",
            settlement_amount=Decimal("20.00"),
            gross_transaction_amount=Decimal("100.00"),
            net_transaction_amount=Decimal("80.00"),
            merchant_id="M2", merchant_name="M2",
            completed_at="", remark="",
        )

    def test_whitelist_income(self):
        result = compute_income([self.r1, self.r2, self.r3], self.whitelist)
        total = result["total_settlement"]
        self.assertEqual(total, Decimal("7.00"))

        self.assertEqual(len(result["categories"]), 2)

        cat1 = result["categories"][0]
        self.assertEqual(cat1["distinct_order_count"], 1)  # 12345 counted once

    def test_refund_preserved(self):
        result = compute_income([self.r1, self.r2], self.whitelist)
        self.assertEqual(result["total_settlement"], Decimal("7.00"))

    def test_unknown_type_reported(self):
        result = compute_income([self.r1, self.r3], self.whitelist)
        self.assertEqual(len(result["unknown_types"]), 1)
        self.assertIn("城代选推高级KA", [u["service_package"] for u in result["unknown_types"]])


class TestHQFee(unittest.TestCase):

    def test_1_percent_fee(self):
        income_result = {
            "total_gross": Decimal("5000.00"),
        }
        result = compute_hq_fee(income_result, Decimal("0.01"))
        self.assertEqual(result["hq_fee"], Decimal("50.00"))


class TestTeamDeliveryCost(unittest.TestCase):

    def test_team_cost_46(self):
        delivery_config = {
            "team_group": {
                "delivery_method": "蜂鸟团队",
                "service_packages": ["城代拼团"],
            },
            "team_normal": {
                "delivery_method": "蜂鸟团队",
                "service_packages": ["代理商E配送"],
            },
            "crowd_group": {
                "delivery_method": "蜂鸟众包",
                "service_packages": ["城代拼团"],
            },
            "crowd_normal": {
                "delivery_method": "蜂鸟众包",
                "service_packages": ["代理商E配送"],
            },
        }
        r1 = NormalizedBillingRow(
            source_file="test.xlsx", source_sheet="S0", source_row=5,
            billing_date="2026-06-23", business_category="餐饮",
            order_id="1", order_type="", delivery_type="蜂鸟团队",
            service_package_type="城代拼团",
            settlement_amount=Decimal("0"), gross_transaction_amount=Decimal("0"),
            net_transaction_amount=Decimal("0"),
            merchant_id="", merchant_name="", completed_at="", remark="",
        )
        r2 = NormalizedBillingRow(
            source_file="test.xlsx", source_sheet="S0", source_row=6,
            billing_date="2026-06-23", business_category="餐饮",
            order_id="2", order_type="", delivery_type="蜂鸟团队",
            service_package_type="代理商E配送",
            settlement_amount=Decimal("0"), gross_transaction_amount=Decimal("0"),
            net_transaction_amount=Decimal("0"),
            merchant_id="", merchant_name="", completed_at="", remark="",
        )
        result = compute_team_delivery_cost(
            [r1, r2], delivery_config,
            Decimal("4.60"), Decimal("4.60"),
        )
        self.assertEqual(result["team_group"]["distinct_order_count"], 1)
        self.assertEqual(result["team_group"]["total_cost"], Decimal("4.60"))
        self.assertEqual(result["team_normal"]["distinct_order_count"], 1)
        self.assertEqual(result["team_normal"]["total_cost"], Decimal("4.60"))


class TestFileIntegrity(unittest.TestCase):

    def test_sha256(self):
        with tempfile.NamedTemporaryFile(delete=False, mode="w", suffix=".txt") as f:
            f.write("test content")
            f.flush()
            h = sha256_file(f.name)
        os.unlink(f.name)
        self.assertEqual(len(h), 64)
        self.assertTrue(all(c in "0123456789abcdef" for c in h))


class TestOrderIDString(unittest.TestCase):

    def test_order_id_as_string(self):
        r = NormalizedBillingRow(
            source_file="t", source_sheet="s", source_row=1,
            billing_date="2026-06-23", business_category="餐饮",
            order_id="8051866177242893765", order_type="正常",
            delivery_type="蜂鸟团队", service_package_type="代理商E配送",
            settlement_amount=Decimal("10.00"),
            gross_transaction_amount=Decimal("50.00"),
            net_transaction_amount=Decimal("40.00"),
            merchant_id="", merchant_name="", completed_at="", remark="",
        )
        self.assertIsInstance(r.order_id, str)
        self.assertEqual(r.order_id, "8051866177242893765")

    def test_distinct_order_counting(self):
        rows = [
            NormalizedBillingRow("t", "s", i, "2026-06-23", "餐饮", "123", "正常",
                                "蜂鸟团队", "代理商E配送", Decimal("5.00"), Decimal("10.00"),
                                Decimal("10.00"), "", "", "", "")
            for i in range(5, 8)
        ]
        whitelist = [{"service_package": "代理商E配送"}]
        result = compute_income(rows, whitelist)
        self.assertEqual(result["total_distinct_orders"], 1)


def cfg(key):
    c = load_city_config("guan")
    return c.get(key, c.get(f"_{key}_d"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
