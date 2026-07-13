from .models import BillingRow


def compute_hq_fee(rows: list[BillingRow]) -> tuple[float, float, list[dict]]:
    total_gross = 0.0
    anomalies = []

    for row in rows:
        total_gross += row.gross_transaction

    hq_fee = round(total_gross * 0.01, 2)
    return round(total_gross, 2), hq_fee, anomalies
