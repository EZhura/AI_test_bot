import json
import os
from datetime import datetime

USAGE_FILE = "usage_data.json"
CLIENT_ID = "beauty_ai_demo_bot"


def get_current_period() -> str:
    return datetime.utcnow().strftime("%Y-%m")


def load_usage_data() -> dict:
    if not os.path.exists(USAGE_FILE):
        return {}

    with open(USAGE_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def save_usage_data(data: dict) -> None:
    with open(USAGE_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def add_extra_limit(client_id: str, extra_requests: int) -> None:
    data = load_usage_data()
    current_period = get_current_period()

    if client_id not in data:
        data[client_id] = {
            "plan_name": "AI_manual",
            "monthly_ai_limit": 0,
            "ai_requests_used": 0,
            "period": current_period,
        }

    client = data[client_id]

    if client.get("period") != current_period:
        client["ai_requests_used"] = 0
        client["period"] = current_period

    client["monthly_ai_limit"] += extra_requests
    save_usage_data(data)


if __name__ == "__main__":
    add_extra_limit(CLIENT_ID, 500)
    print(f"Лимит для {CLIENT_ID} увеличен на 500")