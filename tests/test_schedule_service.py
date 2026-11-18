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
    # The plan's two sections come first; the built-in data adds more (2 to 4 per course).
    assert [s["id"] for s in oop["sections"][:2]] == ["C5", "C6"]
    assert all(2 <= len(c["sections"]) <= 4 for c in data["courses"])
    assert oop["exam"] == {"date": "2026-12-20", "start": 480}
    assert oop["sections"][0]["meetings"][0]["day"] == 0  # Sunday


def test_generate_finds_clash_free_schedules():
    # OOP's C5 and Discrete 1's C2 are both Sun/Tue 08:00, so with C2 pinned
    # OOP never gets C5.
    res = service.generate(["عال 1241", "عال 1100"], locks={"عال 1100": "C2"})
    assert res["errors"] == [] and res["schedules"]
    for sched in res["schedules"]:
        picks = {p["code"]: p["section"] for p in sched["picks"]}
        assert picks["عال 1100"] == "C2" and picks["عال 1241"] != "C5"


def test_exam_clash_is_a_hard_constraint():
    # OOP and Data Structures share the same final exam slot (20-12-2026 08:00).
    res = service.generate(["عال 1241", "عال 1242"])
    assert res["schedules"] == [] and res["failure_reason"]


def test_min_days_off():
    # Thursday-only section + Sun/Tue section = 3 days used, so 2 days off is fine, 3 is not.
    locks = {"عال 1201": "C7", "عال 1111": "C1"}
    assert service.generate(["عال 1201", "عال 1111"], locks=locks, min_days_off=2)["schedules"]
    assert not service.generate(["عال 1201", "عال 1111"], locks=locks, min_days_off=3)["schedules"]


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


def test_transcript_rows():
    from src.scheduling.code_mapping import map_transcript_codes
    from src.scheduling.transcript_parser import _parse_course_row

    # Normal row, with the extra empty title column some pages export.
    row = _parse_course_row(["CS 1141", "Object-Oriented Programming", None, "4", "12", "C"])
    assert row.code == "CS 1141" and row.credit_hours == 4 and row.passed
    assert not _parse_course_row(["PH 1104", "Applied Physics", None, "0", "0", "W"]).passed
    # Equivalency table: code | title | hours, no grade -> counted as passed.
    eq = _parse_course_row(["CS 114", "Discrete structures 1", "3"])
    assert eq.passed and eq.grade == "EQ"
    assert _parse_course_row(["Equivalent Credit Hours Sum:", None, "9"]) is None
    # Old and newer English codes both reach the plan's Arabic codes.
    mapped, unmapped = map_transcript_codes({"CS 252", "CS 1242", "CS 1141", "QUR 1001"})
    assert mapped == {"عال 1242", "عال 1241"} and unmapped == {"QUR 1001"}


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)


def test_each_problem_is_named_when_nothing_fits():
    """When no schedule fits, the page is told exactly what is wrong."""
    def kinds(res):
        assert res["schedules"] == []
        return [p["kind"] for p in res["problems"]]

    assert kinds(service.generate(["عال 1472"], completed_courses=[])) == ["prereq"]
    assert kinds(service.generate(["عال 1241"], time_from="20:00", time_to="24:00")) == ["outside_time"]
    assert kinds(service.generate(["عال 1241"], locks={"عال 1241": "C5"}, time_from="12:00")) == ["locked_time"]
    res = service.generate(["عال 1241", "عال 1100"], locks={"عال 1241": "C5", "عال 1100": "C2"})
    assert kinds(res) == ["time_clash"] and res["problems"][0]["locked"]
    assert kinds(service.generate(["عال 1241", "عال 1100", "عال 1111"], min_days_off=4)) == ["days_off"]
    # A schedule that fits has no problems.
    assert service.generate(["عال 1241"])["problems"] == []
