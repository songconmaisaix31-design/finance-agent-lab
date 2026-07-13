from dataclasses import dataclass, field
from typing import Optional


@dataclass
class BillingRow:
    source: str
    row_number: int
    order_id: str
    settlement_amount: float
    delivery_method: str
    service_package: str
    gross_transaction: float
    business_type: str
    order_type: str


@dataclass
class CrowdCostRow:
    row_number: int
    waybill_id: str
    order_id: str
    capacity_line: str
    total_cost: float
    is_retail: int
    is_pintuan: int
    delivery_status: str
    date: str = ""


@dataclass
class IncomeCategory:
    standard_name: str
    total_amount: float
    distinct_order_count: int
    avg_per_order: float


@dataclass
class CapacityLineBreakdown:
    capacity_line: str
    order_count: int
    total_cost: float
    avg_per_order: float


@dataclass
class DeliveryCostCategory:
    category: str
    order_count: int
    unit_cost: float
    total_cost: float
    crowd_breakdown: list[CapacityLineBreakdown] = field(default_factory=list)
    matched_count: int = 0
    unmatched_count: int = 0
    duplicate_count: int = 0
    empty_waybill_count: int = 0


@dataclass
class RunInfo:
    run_id: str
    start_time: str
    end_time: str
    status: str
    food_income_total: float
    retail_income_total: float
    food_hq_fee: float
    retail_hq_fee: float
    food_delivery_total: float
    retail_delivery_total: float
    food_net: float
    retail_net: float


@dataclass
class RunSummary:
    run_info: RunInfo
    food_income_categories: list[IncomeCategory] = field(default_factory=list)
    retail_income_categories: list[IncomeCategory] = field(default_factory=list)
    food_delivery_categories: list[DeliveryCostCategory] = field(default_factory=list)
    retail_delivery_categories: list[DeliveryCostCategory] = field(default_factory=list)
    anomalies: list[dict] = field(default_factory=list)
    reconciliation_checks: list[dict] = field(default_factory=list)
    file_info: dict = field(default_factory=dict)
    raw_row_counts: dict = field(default_factory=dict)
    valid_row_counts: dict = field(default_factory=dict)
