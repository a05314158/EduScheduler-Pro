"""output.py — вывод расписания в трёх режимах."""
from ortools.sat.python import cp_model as _cp
from models import Lesson, Group, Teacher
from slots import DAY_NAMES_SHORT

DAYS_RU = ["Понедельник","Вторник","Среда","Четверг","Пятница","Суббота","Воскресенье"]
STATUS_NAMES = {_cp.OPTIMAL:"OPTIMAL",_cp.FEASIBLE:"FEASIBLE",
                _cp.INFEASIBLE:"INFEASIBLE",_cp.UNKNOWN:"UNKNOWN"}


def _cell(text, w):
    s = str(text)
    return s[:w].ljust(w)


def print_schedule(solver, assignments, room_map, lessons, slots,
                   groups, teachers, solve_time, status,
                   mode="all", filter_group=None, filter_teacher=None, filter_day=None):

    # room_map[(l_idx, s_idx)] -> room_id  (заполняется room_assigner)
    assigned = {}
    for (l_idx, s_idx), var in assignments.items():
        if solver.value(var) == 1:
            assigned[(l_idx, s_idx)] = room_map.get((l_idx, s_idx), "—")

    total_assigned = len(assigned)
    total_needed   = sum(l.hours_per_week for l in lessons)

    print(f"\n{'='*60}")
    print(f"РЕЗУЛЬТАТ  |  Статус: {STATUS_NAMES.get(status,'?')}  |  Время: {solve_time:.1f}s")
    print(f"Назначено: {total_assigned}/{total_needed} пар")
    print(f"{'='*60}")

    day_indices = sorted({slots[s_idx].day for (_,s_idx) in assigned})

    # Фильтр по дню
    if filter_day:
        short_map = {name:i for i,name in enumerate(DAY_NAMES_SHORT)}
        fd = short_map.get(filter_day)
        if fd is not None:
            day_indices = [d for d in day_indices if d == fd]

    def slot_label(slot):
        return f"{DAY_NAMES_SHORT[slot.day]} п{slot.period+1} ({slot.time_range})"

    # ── Режим: группы ────────────────────────────────────────────────────────
    if mode in ("groups","all"):
        target_groups = [g for g in groups if filter_group is None or g.name==filter_group]
        for group in sorted(target_groups, key=lambda g: g.name):
            rows = []
            for (l_idx, s_idx), room in assigned.items():
                les, slot = lessons[l_idx], slots[s_idx]
                if les.group.name == group.name and slot.day in day_indices:
                    rows.append((slot.day, slot.period, slot, les, room))
            if not rows:
                continue
            print(f"\n── Группа {group.name} (смена {group.shift}) ──")
            print(f"  {'День/пара':<18} {'Предмет':<28} {'Преподаватель':<22}")
            print(f"  {'-'*18} {'-'*28} {'-'*22}")
            for _,_,slot,les,room in sorted(rows):
                print(f"  {_cell(slot_label(slot),18)} {_cell(les.subject.name,28)} {_cell(les.teacher.name,22)}")

    # ── Режим: преподаватели ──────────────────────────────────────────────────
    if mode in ("teachers","all"):
        target_teachers = [t for t in teachers if filter_teacher is None or t.name==filter_teacher]
        for teacher in sorted(target_teachers, key=lambda t: t.name):
            rows = []
            for (l_idx, s_idx), room in assigned.items():
                les, slot = lessons[l_idx], slots[s_idx]
                if les.teacher.name == teacher.name and slot.day in day_indices:
                    rows.append((slot.day, slot.period, slot, les, room))
            if not rows:
                continue
            print(f"\n── Преп. {teacher.name} ──")
            print(f"  {'День/пара':<18} {'Группа':<10} {'Предмет':<28}")
            print(f"  {'-'*18} {'-'*10} {'-'*28}")
            for _,_,slot,les,room in sorted(rows):
                print(f"  {_cell(slot_label(slot),18)} {_cell(les.group.name,10)} {_cell(les.subject.name,28)}")

    # ── Режим: слоты (таблица аудиторий) ─────────────────────────────────────
    if mode in ("slots","all"):
        print(f"\n── Сводная таблица слотов ──")
        for day_idx in day_indices:
            day_slots = sorted([slots[s_idx] for (_,s_idx) in assigned
                                if slots[s_idx].day==day_idx], key=lambda s:(s.shift,s.period))
            if not day_slots:
                continue
            print(f"\n  {DAYS_RU[day_idx]}")
            for slot in day_slots:
                entries = [(lessons[l_idx], room) for (l_idx,s_idx),room in assigned.items()
                           if slots[s_idx] is slot or (slots[s_idx].day==slot.day and slots[s_idx].period==slot.period and slots[s_idx].shift==slot.shift)]
                if not entries:
                    continue
                print(f"    {slot.time_range} (см.{slot.shift}, п{slot.period+1}):")
                for les, room in sorted(entries, key=lambda x: x[0].group.name):
                    print(f"      {les.group.name:<10} {les.subject.name:<28} {les.teacher.name:<22}")

    # ── Итоговая статистика ───────────────────────────────────────────────────
    print(f"\n{'='*60}")
    print(f"Итог: {total_assigned}/{total_needed} назначений")
    hc2_ok = _check_hc2(assigned, lessons, slots)
    hc3_ok = _check_hc3(assigned, lessons, slots)
    print(f"HC-2 (преп. конфликты): {'OK' if hc2_ok==0 else hc2_ok+' нарушений'}")
    print(f"HC-3 (группа конфликты): {'OK' if hc3_ok==0 else str(hc3_ok)+' нарушений'}")


def _check_hc2(assigned, lessons, slots):
    from collections import defaultdict
    occ = defaultdict(list)
    for (l_idx, s_idx) in assigned:
        slot = slots[s_idx]
        occ[(lessons[l_idx].teacher.name, slot.day, slot.real_period)].append(l_idx)
    return sum(1 for v in occ.values() if len(v)>1)

def _check_hc3(assigned, lessons, slots):
    from collections import defaultdict
    occ = defaultdict(list)
    for (l_idx, s_idx) in assigned:
        occ[(lessons[l_idx].group.name, s_idx)].append(l_idx)
    return sum(1 for v in occ.values() if len(v)>1)
