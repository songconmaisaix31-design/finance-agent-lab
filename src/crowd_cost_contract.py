from decimal import Decimal
from pathlib import Path
from zipfile import BadZipFile

import openpyxl

from .crowd_cost import extract_crowd_cost_buckets


CROWD_BUCKET_ORDER = ["catering_normal", "catering_group", "retail_normal", "retail_group"]
CROWD_BUCKET_NAMES = {
    "catering_normal": "餐饮众包正常单",
    "catering_group": "餐饮众包拼团",
    "retail_normal": "零售众包正常单",
    "retail_group": "零售众包拼团",
}


class CrowdCostError(Exception):
    def __init__(self, error_code: str, stage: str, safe_message: str, count: int = 1):
        super().__init__(safe_message)
        self.error_code = error_code
        self.stage = stage
        self.safe_message = safe_message
        self.count = count

    def to_dict(self) -> dict:
        return {
            "error_code": self.error_code,
            "stage": self.stage,
            "safe_message": self.safe_message,
            "count": self.count,
        }


def build_crowd_cost_result(cost_path: str | Path, city_config: dict) -> dict:
    path = Path(cost_path)
    if not path.exists():
        raise CrowdCostError("CROWD_FILE_NOT_FOUND", "crowd_cost_input", "Crowd cost file was not found")

    try:
        raw = extract_crowd_cost_buckets(str(path), city_config)
    except KeyError as exc:
        if city_config["crowd_cost"]["detail_sheet"] in str(exc):
            raise CrowdCostError("CROWD_SHEET_MISSING", "crowd_cost_input", "Crowd cost detail sheet is missing") from exc
        raise CrowdCostError("CROWD_HEADER_INVALID", "crowd_cost_input", "Crowd cost configuration or fields are invalid") from exc
    except ValueError as exc:
        raise CrowdCostError("CROWD_HEADER_INVALID", "crowd_cost_input", "Crowd cost header is invalid") from exc
    except (BadZipFile, openpyxl.utils.exceptions.InvalidFileException) as exc:
        raise CrowdCostError("CROWD_FILE_INVALID", "crowd_cost_input", "Crowd cost file is not a valid Excel workbook") from exc

    buckets = []
    bucket_amounts = {}
    accepted_rows = 0
    total_amount = Decimal("0")
    warnings = []

    for bucket_id in CROWD_BUCKET_ORDER:
        bucket = raw["buckets"][bucket_id]
        amount = bucket["total_cost"]
        completed = bucket["completed_orders"]
        bucket_amounts[bucket_id] = amount
        total_amount += amount
        accepted_rows += int(completed)
        buckets.append({
            "id": bucket_id,
            "name": CROWD_BUCKET_NAMES[bucket_id],
            "amount": amount,
            "completed_orders": completed,
            "approval_status": "unverified",
            "rule_source": "code_existing",
        })
        if amount < 0 or completed < 0:
            warnings.append({
                "code": "CROWD_NEGATIVE_AMOUNT_UNVERIFIED",
                "bucket_id": bucket_id,
                "safe_message": "Negative crowd cost behavior is existing but business policy is unverified",
            })
        if amount == 0 and completed > 0:
            warnings.append({
                "code": "CROWD_ZERO_AMOUNT_UNVERIFIED",
                "bucket_id": bucket_id,
                "safe_message": "Zero crowd cost with completed orders is existing but business policy is unverified",
            })

    if raw.get("source_rows"):
        seen = set()
        duplicate_seen = False
        for row in raw["source_rows"]:
            key = (
                row.get("date"),
                row.get("delivery_status"),
                row.get("is_retail"),
                row.get("city"),
                row.get("is_group_order"),
                str(row.get("completed_orders")),
                str(row.get("total_cost")),
            )
            if key in seen:
                duplicate_seen = True
                break
            seen.add(key)
        if duplicate_seen:
            warnings.append({
                "code": "CROWD_DEDUP_POLICY_UNVERIFIED",
                "safe_message": "Duplicate crowd cost row behavior is additive; dedup policy is unverified",
            })

    rejected = sorted(raw.get("rejected_rows", []), key=lambda r: r.get("source_row", 0))
    unknown = sorted(raw.get("unknown_rows", []), key=lambda r: r.get("source_row", 0))
    status = "blocked" if rejected or unknown else "complete"

    return {
        "status": status,
        "source_rows": raw["filtered_row_count"],
        "accepted_rows": len(raw.get("source_rows", [])),
        "rejected_rows": rejected,
        "unknown_rows": unknown,
        "bucket_amounts": bucket_amounts,
        "buckets": buckets,
        "total_amount": total_amount,
        "warnings": warnings,
        "errors": rejected + unknown,
        "rule_approval_status": "unverified",
        "bucket_rule_source": "code_existing",
        "source_sheet": raw["source_sheet"],
        "raw_buckets": raw["buckets"],
    }


def crowd_result_for_summary(result: dict) -> dict:
    return {
        "status": result["status"],
        "currency": "CNY",
        "total": str(result["total_amount"]),
        "buckets": [
            {
                "id": bucket["id"],
                "name": bucket["name"],
                "amount": str(bucket["amount"]),
                "completed_orders": str(bucket["completed_orders"]),
                "approval_status": bucket["approval_status"],
            }
            for bucket in result["buckets"]
        ],
        "source_rows": result["source_rows"],
        "accepted_rows": result["accepted_rows"],
        "unknown_rows": len(result["unknown_rows"]),
        "rejected_rows": len(result["rejected_rows"]),
        "rule_approval_status": result["rule_approval_status"],
    }
