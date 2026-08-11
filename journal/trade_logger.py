import json
from datetime import datetime


def log_trade(data: dict):
    log_entry = {
        "timestamp": datetime.now().isoformat(),
        **data
    }

    with open("journal/trades.jsonl", "a", encoding="utf-8") as file:
        file.write(json.dumps(log_entry) + "\n")