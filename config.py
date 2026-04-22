import json

def load_config(path: str = "institution_config.json") -> dict:
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        # Нормализуем ключи shift_period_map и shift_allowed_periods в int
        for key in ("shift_period_map", "shift_allowed_periods"):
            if key in data:
                data[key] = {int(k): v for k, v in data[key].items()}
        return data
    except FileNotFoundError:
        return {}
