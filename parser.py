"""parser.py — читает groups-2.xlsx формата: группа | смена | предмет (преп.): часы, ..."""
import re
import pandas as pd
from collections import defaultdict


def _parse_lessons_cell(cell: str) -> list[dict]:
    """
    Разбирает строку вида:
    'Предмет (Преп. И.О.): 2, Другой предмет (Преп2 И.О.): 1'
    -> [{"subject": "Предмет", "teacher": "Преп. И.О.", "hours_per_week": 2}, ...]
    """
    results = []
    # Паттерн: Предмет (Преподаватель): число
    pattern = re.compile(r'(.+?)\s*\(([^)]+)\)\s*:\s*(\d+)', re.UNICODE)
    for m in pattern.finditer(cell):
        subject = m.group(1).strip()
        teacher = re.sub(r'\s+', ' ', m.group(2).strip())
        hours   = int(m.group(3))
        # Если несколько преподавателей через запятую внутри скобок — разбиваем
        teachers = re.split(r',\s*(?=[А-ЯЁA-Z])', teacher)
        if len(teachers) == 1:
            results.append({"subject": subject, "teacher": teacher, "hours_per_week": hours})
        else:
            for t in teachers:
                results.append({"subject": subject, "teacher": t.strip(), "hours_per_week": 1})
    return results


def parse_groups(filepath: str = "groups-2.xlsx") -> list[dict]:
    df = pd.read_excel(filepath, header=0)
    df.columns = [str(c).strip() for c in df.columns]

    col_group  = df.columns[0]
    col_shift  = df.columns[1]
    col_lessons = df.columns[2]

    grouped = defaultdict(lambda: {"shift": 0, "lessons": []})
    for _, row in df.iterrows():
        group = str(row[col_group]).strip()
        if not group or group == "nan":
            continue
        try:
            shift = int(row[col_shift])
        except Exception:
            shift = 0
        cell = str(row[col_lessons]).strip()
        lessons = _parse_lessons_cell(cell)

        grouped[group]["shift"] = shift
        grouped[group]["lessons"].extend(lessons)

    return [{"group": g, "shift": v["shift"], "lessons": v["lessons"]}
            for g, v in grouped.items()]


def print_parse_stats(raw: list[dict]):
    groups   = {r["group"] for r in raw}
    teachers = {l["teacher"] for r in raw for l in r["lessons"]}
    subjects = {l["subject"] for r in raw for l in r["lessons"]}
    total_h  = sum(l["hours_per_week"] for r in raw for l in r["lessons"])
    print(f"Групп: {len(groups)}")
    print(f"Уникальных преподавателей: {len(teachers)}")
    print(f"Уникальных предметов: {len(subjects)}")
    print(f"Всего уроков (записей): {sum(len(r['lessons']) for r in raw)}")
    print(f"Всего пар в неделю: {total_h}")
