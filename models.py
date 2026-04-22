from dataclasses import dataclass, field

@dataclass
class Teacher:
    name: str

@dataclass
class Subject:
    name: str

@dataclass
class Group:
    name: str
    shift: int  # 0, 1, 2

@dataclass
class Lesson:
    group: Group
    subject: Subject
    teacher: Teacher
    hours_per_week: int

# Re-export TimeSlot from slots (imported there to avoid circular)
