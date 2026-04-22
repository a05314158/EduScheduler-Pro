"""solver.py — CP-SAT модель расписания (итерация 3, rev3)."""
import json
import math
from collections import defaultdict
from ortools.sat.python import cp_model
from models import Lesson, Teacher, Group


def get_group_load(group_name, lessons):
    return sum(l.hours_per_week for l in lessons if l.group.name == group_name)

def get_teacher_load(teacher_name, lessons):
    return sum(l.hours_per_week for l in lessons if l.teacher.name == teacher_name)

def load_teacher_availability(path="teachers_availability.json"):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return {}


# ── Адаптивный таймаут ────────────────────────────────────────────────────────

def calculate_time_limit(lessons_count: int, groups_count: int,
                         base: int = 120, ceiling: int = 1800) -> int:
    """
    Базовый таймаут 120 сек масштабируется пропорционально размеру задачи.
    Формула: base * sqrt(lessons * groups / (284 * 74))
    Потолок: 1800 сек (30 мин).
    """
    reference = 284 * 74          # размер «стандартной» задачи из данных
    scale = math.sqrt((lessons_count * groups_count) / reference)
    limit = int(base * max(1.0, scale))
    return min(limit, ceiling)


# ── Greedy hint ───────────────────────────────────────────────────────────────

def compute_greedy_hint(lessons, slots, assignments, availability):
    hint = {var: 0 for var in assignments.values()}
    teacher_busy = defaultdict(set)
    group_busy   = defaultdict(set)

    lesson_order = sorted(range(len(lessons)), key=lambda i: -lessons[i].hours_per_week)

    for l_idx in lesson_order:
        lesson = lessons[l_idx]
        tname, gname = lesson.teacher.name, lesson.group.name
        avail = availability.get(tname, {})
        f_days    = set(avail.get("forbidden", {}).get("days", []))
        f_periods = set(avail.get("forbidden", {}).get("periods", []))

        candidates = sorted(
            [(s_idx, s) for s_idx, s in enumerate(slots)
             if (l_idx, s_idx) in assignments
             and s.day not in f_days and s.period not in f_periods],
            key=lambda x: (x[1].day, x[1].period)
        )

        placed, used = 0, set()
        for s_idx, slot in candidates:
            if placed >= lesson.hours_per_week:
                break
            rp = (slot.day, slot.real_period)
            if s_idx in used or tname in teacher_busy[rp] or gname in group_busy[rp]:
                continue
            hint[assignments[(l_idx, s_idx)]] = 1
            teacher_busy[rp].add(tname)
            group_busy[rp].add(gname)
            used.add(s_idx)
            placed += 1

    placed_total = sum(v for v in hint.values())
    total_needed = sum(l.hours_per_week for l in lessons)
    print(f"  Greedy hint: {placed_total}/{total_needed} назначений")
    return hint


# ── Трёхуровневая доступность ─────────────────────────────────────────────────

def apply_teacher_availability(model, assignments, lessons, slots, availability):
    unwanted_vars, preferred_vars = [], []
    for l_idx, lesson in enumerate(lessons):
        tname = lesson.teacher.name
        avail = availability.get(tname, {})
        f_days    = set(avail.get("forbidden", {}).get("days",    []))
        f_periods = set(avail.get("forbidden", {}).get("periods", []))
        u_days    = set(avail.get("unwanted",  {}).get("days",    []))
        u_periods = set(avail.get("unwanted",  {}).get("periods", []))
        u_weight  =     avail.get("unwanted",  {}).get("penalty_weight", 10)
        p_days    = set(avail.get("preferred", {}).get("days",    []))
        p_periods = set(avail.get("preferred", {}).get("periods", []))
        p_weight  =     avail.get("preferred", {}).get("bonus_weight", 0)

        # Пропускаем преподавателей без каких-либо ограничений — не добавляем лишних vars
        if not f_days and not f_periods and not u_days and not u_periods and p_weight == 0:
            continue

        for s_idx, slot in enumerate(slots):
            if (l_idx, s_idx) not in assignments:
                continue
            var = assignments[(l_idx, s_idx)]
            # Жёсткий запрет
            if slot.day in f_days or slot.period in f_periods:
                model.add(var == 0)
                continue
            # Нежелательное время — штраф
            if slot.day in u_days or slot.period in u_periods:
                pv = model.new_bool_var(f"unwanted_{l_idx}_{s_idx}")
                model.add_implication(var, pv)
                model.add_implication(pv.negated(), var.negated())
                unwanted_vars.append((pv, u_weight))
            # Предпочтительное время — бонус
            if p_weight > 0:
                day_ok    = (not p_days)    or slot.day    in p_days
                period_ok = (not p_periods) or slot.period in p_periods
                if day_ok and period_ok:
                    bv = model.new_bool_var(f"preferred_{l_idx}_{s_idx}")
                    model.add_implication(var, bv)
                    preferred_vars.append((bv, p_weight))
    return unwanted_vars, preferred_vars


# ── Построение модели ─────────────────────────────────────────────────────────

def build_model(lessons, slots, teachers, groups, config,
                disable_hc5=False,
                disable_sc=False, sc_gap=False, sc_biggap=False, sc_empty=False):
    model = cp_model.CpModel()
    max_per_day      = config.get("max_lessons_per_day_per_group", 3)
    max_gap          = config.get("max_gap_periods", 1)
    shift_overflow   = config.get("shift_overflow_allowed", False)
    shift_overflow_w = config.get("shift_overflow_penalty_weight", 50)
    shift_allowed_map = {int(k): v for k, v in
                         config.get("shift_allowed_periods", {}).items()}

    assignments: dict = {}
    shift_violation_vars: list = []

    for l_idx, lesson in enumerate(lessons):
        g_shift = lesson.group.shift
        for s_idx, slot in enumerate(slots):
            if shift_overflow:
                neighbor = {max(0, g_shift-1), g_shift, min(2, g_shift+1)}
                if slot.shift not in neighbor:
                    continue
                var = model.new_bool_var(f"x_{l_idx}_{s_idx}")
                assignments[(l_idx, s_idx)] = var
                allowed_rp = shift_allowed_map.get(g_shift, [])
                if allowed_rp and slot.real_period not in allowed_rp:
                    sv = model.new_bool_var(f"sv_{l_idx}_{s_idx}")
                    model.add_implication(var, sv)
                    model.add_implication(sv.negated(), var.negated())
                    shift_violation_vars.append(sv)
            else:
                if slot.shift == g_shift:
                    assignments[(l_idx, s_idx)] = model.new_bool_var(f"x_{l_idx}_{s_idx}")

    # Аудитории назначаются постфактум через room_assigner.py (вне CP-SAT)
    room_assignments: dict = {}

    real_time_to_slots = defaultdict(list)
    for s_idx, slot in enumerate(slots):
        real_time_to_slots[(slot.day, slot.real_period)].append(s_idx)

    # HC-1
    for l_idx, lesson in enumerate(lessons):
        valid = [s for s in range(len(slots)) if (l_idx, s) in assignments]
        if valid:
            model.add(sum(assignments[(l_idx, s)] for s in valid) == lesson.hours_per_week)

    # HC-2: преподаватель не в двух местах одновременно
    for (day, rp), s_list in real_time_to_slots.items():
        for teacher in teachers:
            tvars = [assignments[(l, s)] for s in s_list for l, les in enumerate(lessons)
                     if les.teacher.name == teacher.name and (l, s) in assignments]
            if len(tvars) > 1:
                model.add(sum(tvars) <= 1)

    # HC-3: группа — не две пары в один слот
    for s_idx in range(len(slots)):
        for group in groups:
            gvars = [assignments[(l, s_idx)] for l, les in enumerate(lessons)
                     if les.group.name == group.name and (l, s_idx) in assignments]
            if len(gvars) > 1:
                model.add(sum(gvars) <= 1)


    # HC-5: трёхуровневая доступность
    teacher_unwanted_vars, teacher_preferred_vars = [], []
    if not disable_hc5:
        availability = load_teacher_availability()
        teacher_unwanted_vars, teacher_preferred_vars = apply_teacher_availability(
            model, assignments, lessons, slots, availability)

    # Greedy hint
    avail_hint = load_teacher_availability() if not disable_hc5 else {}
    hint = compute_greedy_hint(lessons, slots, assignments, avail_hint)
    for var, val in hint.items():
        model.add_hint(var, val)

    # Soft constraints
    gap_vars, empty_vars, biggap_vars = [], [], []
    terms_day_excess = []

    for group in groups:
        g_lessons = [l for l, les in enumerate(lessons) if les.group.name == group.name]
        total_h   = sum(lessons[l].hours_per_week for l in g_lessons)
        gap_w     = max(5, min(20, total_h * 2))

        day_slots = {}
        for s_idx, slot in enumerate(slots):
            if any((l, s_idx) in assignments for l in g_lessons):
                day_slots.setdefault(slot.day, []).append((slot.period, s_idx))
        for d in day_slots:
            day_slots[d].sort()

        for day, ds in day_slots.items():
            periods, sidxs = [p for p,_ in ds], [s for _,s in ds]
            dvars = [assignments[(l, s)] for l in g_lessons for s in sidxs if (l,s) in assignments]

            if dvars:
                # SC-day: мягкое ограничение на число пар в день
                excess = model.new_int_var(0, len(dvars), f"exc_{group.name}_{day}")
                model.add(sum(dvars) - max_per_day <= excess)
                model.add(excess >= 0)
                if not disable_sc:
                    terms_day_excess.append(excess)

            if len(periods) >= 3:
                for i in range(len(periods)-2):
                    s1,s2,s3 = sidxs[i],sidxs[i+1],sidxs[i+2]
                    p1v=[assignments[(l,s1)] for l in g_lessons if (l,s1) in assignments]
                    p2v=[assignments[(l,s2)] for l in g_lessons if (l,s2) in assignments]
                    p3v=[assignments[(l,s3)] for l in g_lessons if (l,s3) in assignments]
                    if not (p1v and p2v and p3v):
                        continue
                    hp1=model.new_bool_var(f"hp1_{group.name}_{day}_{i}")
                    hp3=model.new_bool_var(f"hp3_{group.name}_{day}_{i}")
                    np2=model.new_bool_var(f"np2_{group.name}_{day}_{i}")
                    pen=model.new_bool_var(f"pen_{group.name}_{day}_{i}")
                    model.add_max_equality(hp1,p1v)
                    model.add_max_equality(hp3,p3v)
                    model.add_bool_and([v.negated() for v in p2v]).only_enforce_if(np2)
                    model.add_bool_or(p2v).only_enforce_if(np2.negated())
                    model.add_bool_and([hp1,np2,hp3]).only_enforce_if(pen)
                    model.add_bool_or([hp1.negated(),np2.negated(),hp3.negated()]).only_enforce_if(pen.negated())
                    if not disable_sc and sc_gap:
                        gap_vars.append((pen, gap_w))

            if total_h > 3 and day < 5 and dvars:
                ht=model.new_bool_var(f"ht_{group.name}_{day}")
                ep=model.new_bool_var(f"ep_{group.name}_{day}")
                model.add_max_equality(ht,dvars)
                model.add_bool_and([ht.negated()]).only_enforce_if(ep)
                model.add_bool_or([ht]).only_enforce_if(ep.negated())
                if not disable_sc and sc_empty:
                    empty_vars.append(ep)

            if len(periods) >= 2:
                sbp={p:s for p,s in zip(periods,sidxs)}
                for i in range(len(periods)):
                    for j in range(i+2,len(periods)):
                        if periods[j]-periods[i]>max_gap:
                            ev=[assignments[(l,sbp[periods[i]])] for l in g_lessons if (l,sbp[periods[i]]) in assignments]
                            lv=[assignments[(l,sbp[periods[j]])] for l in g_lessons if (l,sbp[periods[j]]) in assignments]
                            if ev and lv:
                                he=model.new_bool_var(f"he_{group.name}_{day}_{i}_{j}")
                                hl=model.new_bool_var(f"hl_{group.name}_{day}_{i}_{j}")
                                gp=model.new_bool_var(f"gp_{group.name}_{day}_{i}_{j}")
                                model.add_max_equality(he,ev)
                                model.add_max_equality(hl,lv)
                                model.add_bool_and([he,hl]).only_enforce_if(gp)
                                model.add_bool_or([he.negated(),hl.negated()]).only_enforce_if(gp.negated())
                                if not disable_sc and sc_biggap:
                                    biggap_vars.append(gp)

    terms = []
    for exc in terms_day_excess: terms.append(200 * exc)
    for v,w in gap_vars:       terms.append(w*v)
    for v in empty_vars:       terms.append(5*v)
    for v in biggap_vars:      terms.append(8*v)
    for v in shift_violation_vars: terms.append(shift_overflow_w*v)
    for v,w in teacher_unwanted_vars:  terms.append(w*v)
    for v,w in teacher_preferred_vars: terms.append(-w*v)
    if terms:
        model.minimize(sum(terms))

    return model, assignments, room_assignments


def solve(model, time_limit=120.0):
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = time_limit
    solver.parameters.log_search_progress = True
    solver.parameters.num_search_workers  = 8
    status = solver.solve(model)
    status_name = solver.status_name(status)
    if status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        print(f"\nРешение найдено! Статус: {status_name}")
        print(f"Взвешенный штраф: {int(solver.objective_value)}")
    else:
        print(f"\nРешение не найдено. Статус: {status_name}")
    return status, solver
