import os
import argparse
import time
from collections import defaultdict
from ortools.sat.python import cp_model

from config import load_config
from parser import parse_groups, print_parse_stats
from models import Teacher, Group, Subject, Lesson
from slots import parse_slots
from solver import (
    build_model, solve,
    calculate_time_limit,
    get_group_load, get_teacher_load,
    load_teacher_availability,
)
from output import print_schedule
from room_assigner import assign_rooms
from export_excel import export_excel


# ... run_diagnose как есть ...


def run_scheduler(
    config_path: str = "institution_config.json",
    groups_file: str = "groups-2.xlsx",
    weekdays_file: str = "weekdays.xlsx",
    mode: str = "all",
    filter_group: str | None = None,
    filter_teacher: str | None = None,
    filter_day: str | None = None,
    diagnose: bool = False,
    no_hc5: bool = False,
    no_sc: bool = False,
    sc_gap: bool = False,
    sc_biggap: bool = False,
    sc_empty: bool = False,
    api_mode: bool = False,
):
    """
    Общая функция: считает расписание и (если не api_mode) печатает его и сохраняет Excel.
    Возвращает dict с ключевой информацией для API.
    """
    config = load_config(config_path)

    if not api_mode:
        print("=" * 60)
        print("ПАРСИНГ ДАННЫХ")
        print("=" * 60)

    raw = parse_groups(groups_file)
    if not api_mode:
        print_parse_stats(raw)

    teacher_map, group_map, subject_map = {}, {}, {}
    lessons: list[Lesson] = []
    for g in raw:
        if g["group"] not in group_map:
            group_map[g["group"]] = Group(name=g["group"], shift=g["shift"])
        for l in g["lessons"]:
            if l["teacher"] not in teacher_map:
                teacher_map[l["teacher"]] = Teacher(name=l["teacher"])
            if l["subject"] not in subject_map:
                subject_map[l["subject"]] = Subject(name=l["subject"])
            lessons.append(Lesson(
                group=group_map[g["group"]],
                subject=subject_map[l["subject"]],
                teacher=teacher_map[l["teacher"]],
                hours_per_week=l["hours_per_week"],
            ))

    teachers = list(teacher_map.values())
    groups   = list(group_map.values())
    slots    = parse_slots(weekdays_file, config)

    time_limit = calculate_time_limit(len(lessons), len(groups))
    if not api_mode:
        print(f"\nТаймаут: {time_limit} сек (расчётный для {len(lessons)} уроков / {len(groups)} групп)")
        print(f"Объектов: {len(groups)} групп, {len(teachers)} преп., {len(lessons)} уроков, {len(slots)} слотов")

    if diagnose and not api_mode:
        run_diagnose(groups, teachers, lessons, slots, config)
        return {"status": "DIAGNOSE_ONLY"}

    if not api_mode:
        print("\nПостроение модели CP-SAT...")
    t_build = time.time()
    model, assignments, room_assignments = build_model(
        lessons, slots, teachers, groups, config,
        disable_hc5=no_hc5,
        disable_sc=no_sc,
        sc_gap=sc_gap,
        sc_biggap=sc_biggap,
        sc_empty=sc_empty,
    )
    n_lesson = len(assignments)
    if not api_mode:
        print(f"  lesson_vars={n_lesson:,}")
        print(f"  Построение модели: {time.time()-t_build:.1f}s")

    if not api_mode:
        print(f"\nЗапуск решателя (лимит {time_limit} сек, 8 workers)...")
    t0 = time.time()
    status, solver = solve(model, time_limit=time_limit)
    solve_time = time.time() - t0

    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        if not api_mode:
            print(f"\nРешение не найдено за {solve_time:.1f} сек.")
            print("Подсказка: запустите с --no-hc5 для диагностики.")
        return {
            "status": "INFEASIBLE",
            "solve_time": solve_time,
            "assigned": 0,
            "total_lessons": len(lessons),
        }

    # Назначение аудиторий + печать (если не API)
    if not api_mode:
        print("\nНазначение аудиторий...")
    room_map = assign_rooms(solver, assignments, lessons, slots)

    if not api_mode:
        print_schedule(
            solver=solver,
            assignments=assignments,
            room_map=room_map,
            lessons=lessons,
            slots=slots,
            groups=groups,
            teachers=teachers,
            solve_time=solve_time,
            status=status,
            mode=mode,
            filter_group=filter_group,
            filter_teacher=filter_teacher,
            filter_day=filter_day,
        )

    # Экспорт в Excel
    out_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "schedule.xlsx")
    export_excel(
        solver, assignments, lessons, slots,
        groups=groups, teachers=teachers,
        output_path=out_path,
    )

    # Минимальная структура для API
    return {
        "status": "OPTIMAL" if status == cp_model.OPTIMAL else "FEASIBLE",
        "solve_time": solve_time,
        "assigned": len(assignments),
        "total_lessons": len(lessons),
        "groups": len(groups),
        "teachers": len(teachers),
        "slots": len(slots),
        "schedule_xlsx": out_path,
    }


def main():
    ap = argparse.ArgumentParser(description="Scheduler v3 — расписание")
    ap.add_argument("--mode",          choices=["groups","teachers","slots","all"], default="all")
    ap.add_argument("--group",         type=str,  default=None)
    ap.add_argument("--teacher",       type=str,  default=None)
    ap.add_argument("--day",           type=str,  default=None)
    ap.add_argument("--config",        type=str,  default="institution_config.json")
    ap.add_argument("--groups-file",   type=str,  default="groups-2.xlsx")
    ap.add_argument("--weekdays-file", type=str,  default="weekdays.xlsx")
    ap.add_argument("--diagnose",      action="store_true")
    ap.add_argument("--no-hc5",        action="store_true")
    ap.add_argument("--no-sc",         action="store_true", help="отключить все SC")
    ap.add_argument("--sc-gap",        action="store_true", help="включить SC: окна")
    ap.add_argument("--sc-biggap",     action="store_true", help="включить SC: большие разрывы")
    ap.add_argument("--sc-empty",      action="store_true", help="включить SC: пустые дни")
    args = ap.parse_args()

    run_scheduler(
        config_path=args.config,
        groups_file=args.groups_file,
        weekdays_file=args.weekdays_file,
        mode=args.mode,
        filter_group=args.group,
        filter_teacher=args.teacher,
        filter_day=args.day,
        diagnose=args.diagnose,
        no_hc5=args.no_hc5,
        no_sc=args.no_sc,
        sc_gap=args.sc_gap,
        sc_biggap=args.sc_biggap,
        sc_empty=args.sc_empty,
        api_mode=False,
    )


if __name__ == "__main__":
    main()