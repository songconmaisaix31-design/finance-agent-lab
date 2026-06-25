from datetime import datetime


def generate_run_id(city_name: str, billing_date: str) -> str:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_date = billing_date.replace("-", "")
    safe_city = city_name
    return f"{safe_city}_{safe_date}_{ts}"
