"""slots.py — генерация временных слотов."""
import json
import pandas as pd
from dataclasses import dataclass

DAY_NAMES_SHORT = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]
DAY_NAME_TO_IDX = {
    "Понедельник": 0, "Вторник": 1, "Среда": 2,
    "Четверг": 3, "Пятница": 4, "Суббота": 5, "Воскресенье": 6,
}
WEEKEND_NAMES = {"Суббота", "Воскресенье"}


@dataclass
class TimeSlot:
    day: int
    day_name: str
    period: int         # 0-based внутри смены
    time_range: str
    shift: int
    rooms: list
    real_period: int    # индекс пары в реальном расписании дня (для HC-4)


def parse_slots(filepath: str = "weekdays.xlsx", config: dict = None) -> list[TimeSlot]:
    if config is None:
        config = {}
    use_weekends     = config.get("use_weekends", False)
    shift_period_map = {int(k): v for k, v in config.get("shift_period_map", {
        0: [0, 1], 1: [0, 1, 2, 3, 4], 2: [2, 3, 4]
    }).items()}

    df = pd.read_excel(filepath, sheet_name=0)
    col_day, col_times, col_rooms = df.columns[0], df.columns[1], df.columns[2]

    day_data = {}
    for _, row in df.iterrows():
        dname = str(row[col_day]).strip()
        if dname not in DAY_NAME_TO_IDX:
            continue
        if not use_weekends and dname in WEEKEND_NAMES:
            continue
        didx = DAY_NAME_TO_IDX[dname]
        try:
            times = json.loads(str(row[col_times]))
        except Exception:
            times = []
        try:
            rooms = json.loads(str(row[col_rooms]))
        except Exception:
            rooms = []
        day_data[didx] = (dname, times, rooms)

    slots = []
    for day_idx in sorted(day_data):
        dname, times, rooms = day_data[day_idx]
        for shift, real_period_indices in sorted(shift_period_map.items()):
            for period_in_shift, real_period in enumerate(real_period_indices):
                time_range = times[real_period] if real_period < len(times) else f"пара {real_period}"
                slots.append(TimeSlot(
                    day=day_idx, day_name=dname,
                    period=period_in_shift, time_range=time_range,
                    shift=shift, rooms=rooms, real_period=real_period,
                ))
    return slots
