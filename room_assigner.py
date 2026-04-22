"""room_assigner.py — жадное назначение аудиторий после CP-SAT."""
import logging
from collections import defaultdict

logger = logging.getLogger(__name__)


def assign_rooms(solver, assignments, lessons, slots) -> dict:
    """
    Назначает аудитории жадно после того, как solver нашёл расписание.

    Возвращает room_map: dict[(l_idx, s_idx)] -> room_id | "—"
    """
    # Собираем назначенные пары: (day, real_period) -> список (l_idx, s_idx)
    time_to_lessons: dict = defaultdict(list)
    for (l_idx, s_idx), var in assignments.items():
        if solver.value(var) == 1:
            slot = slots[s_idx]
            time_to_lessons[(slot.day, slot.real_period)].append((l_idx, s_idx))

    room_map: dict = {}   # (l_idx, s_idx) -> room_id
    warnings: list = []

    for (day, rp), pairs in sorted(time_to_lessons.items()):
        # Список аудиторий берём из слота первой пары (все слоты одного real_period
        # имеют одинаковый список аудиторий)
        s_idx_first = pairs[0][1]
        available = list(slots[s_idx_first].rooms)
        used: set = set()

        for l_idx, s_idx in pairs:
            free = [r for r in available if r not in used]
            if free:
                room = free[0]
                used.add(room)
            else:
                room = "—"
                lesson = lessons[l_idx]
                slot   = slots[s_idx]
                msg = (f"WARNING: нет свободной аудитории — "
                       f"группа {lesson.group.name}, "
                       f"{slot.time_range} (день {day+1}, период {rp})")
                warnings.append(msg)

            room_map[(l_idx, s_idx)] = room

    if warnings:
        print(f"\n[ROOM_ASSIGNER] {len(warnings)} конфликт(ов) аудиторий:")
        for w in warnings:
            print(f"  {w}")
    else:
        n = len(room_map)
        n_rooms = len(slots[0].rooms) if slots else 0
        print(f"[ROOM_ASSIGNER] {n} пар назначено без конфликтов "
              f"(аудиторий в пуле: {n_rooms})")

    return room_map
