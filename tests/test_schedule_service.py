"""
Checks for the schedule API layer (src/scheduling/service.py) on the real plan data.

Run:
    .venv/Scripts/python.exe -m tests.test_schedule_service
"""
from src.scheduling import service
from src.scheduling.course_data import course_db


def test_catalog_shape():
    data = service.catalog()
    assert len(data["courses"]) == len(course_db)
    oop = next(c for c in data["courses"] if c.get("code") == "عال 1241")
    assert len(oop["sections"]) == 2
    assert oop["exam"] == {"date": "2026-12-20", "start": 480}
    assert oop["sections"][0]["meetings"][0]["day"] == 0  # Sunday


def test_generate_finds_clash_free_schedules():
    # OOP has two sections (ts1 / ts4); Discrete 1 sits on ts1, so OOP must take C6.
    res = service.generate(["عال 1241", "عال 1100"])
    assert res["errors"] == [] and res["schedules"]
    for sched in res["schedules"]:
        picks = {p["code"]: p["section"] for p in sched["picks"]}
        assert picks["عال 1241"] == "C6"


def test_exam_clash_is_a_hard_constraint():
    # OOP and Data Structures share the same final exam slot (20-12-2026 08:00).
    res = service.generate(["عال 1241", "عال 1242"])
    assert res["schedules"] == [] and res["failure_reason"]


def test_min_days_off():
    # Thursday-only course + Sun/Tue course = 3 days used, so 2 days off is fine, 3 is not.
    assert service.generate(["عال 1201", "عال 1111"], min_days_off=2)["schedules"]
    assert not service.generate(["عال 1201", "عال 1111"], min_days_off=3)["schedules"]


def test_prerequisites_only_checked_with_transcript():
    assert service.generate(["عال 1242"])["errors"] == []
    assert service.generate(["عال 1242"], completed_courses=[])["errors"]


def test_credit_limit():
    res = service.generate(["ريض 1112", "ريض 1113", "عال 1140"], max_credit_hours=10)
    assert res["errors"]


def test_unknown_code_rejected():
    try:
        service.generate(["XYZ 999"])
    except service.ScheduleRequestError:
        return
    raise AssertionError("unknown course code was accepted")


def test_suggestion_is_schedulable():
    suggested = service._suggest(set())
    assert suggested
    assert service.generate(suggested, completed_courses=[])["schedules"]


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
