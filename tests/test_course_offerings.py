"""The admin's Excel file of offered courses, sections, times, CRNs and seats."""
import io

import pytest
from openpyxl import load_workbook

from src.scheduling import offerings, service

XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


@pytest.fixture(autouse=True)
def built_in_data():
    service.use_defaults()
    yield
    service.use_defaults()


def _sheet(data: bytes):
    wb = load_workbook(io.BytesIO(data))
    return wb, wb[offerings.SHEET_NAME]


def _save(wb) -> bytes:
    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()


def _column(ws, header):
    return next(c.column for c in ws[1] if c.value == header)


def _row_of(ws, code, section=None):
    code_col, sec_col = _column(ws, "رمز المقرر"), _column(ws, "الشعبة")
    for row in range(2, ws.max_row + 1):
        if ws.cell(row, code_col).value == code and (section is None or ws.cell(row, sec_col).value == section):
            return row
    raise AssertionError(f"{code} {section} not in the sheet")


def _upload(client, data: bytes, name="courses.xlsx"):
    return client.post("/api/admin/courses/excel", files={"file": (name, data, XLSX)})


def test_built_in_data_has_crns_and_open_seats():
    data = service.catalog()["courses"]
    sections = [s for c in data for s in c["sections"]]
    crns = [s["crn"] for s in sections]
    assert len(set(crns)) == len(crns) and all(c.isdigit() for c in crns)
    assert all(s["capacity"] and 0 <= s["enrolled"] < s["capacity"] for s in sections)


def test_the_excel_file_round_trips_unchanged():
    data = offerings.to_excel(service.current_offerings())
    courses, problems = offerings.parse_excel(data)
    assert problems == [] and courses == service.current_offerings()


def test_only_the_admin_can_use_the_file(sign_in):
    assert sign_in("441000001").get("/api/admin/courses/excel").status_code == 403
    assert sign_in("advisor").get("/api/admin/courses").status_code == 403


def test_closing_a_section_in_excel_closes_it_on_the_schedule_page(sign_in):
    admin = sign_in("admin")
    r = admin.get("/api/admin/courses/excel")
    assert r.status_code == 200 and r.headers["content-type"].startswith(XLSX)
    wb, ws = _sheet(r.content)

    # OOP's sections include C5 and C6: fill C5 and give C6 a new CRN, doctor and time.
    c5, c6 = _row_of(ws, "عال 1241", "C5"), _row_of(ws, "عال 1241", "C6")
    ws.cell(c5, _column(ws, "المقاعد المأخوذة")).value = ws.cell(c5, _column(ws, "عدد المقاعد")).value
    ws.cell(c6, _column(ws, "الرقم المرجعي (CRN)")).value = "99001"
    ws.cell(c6, _column(ws, "اسم الدكتور")).value = "د. تجربة"
    ws.cell(c6, _column(ws, "الأيام")).value = "الاثنين/الأربعاء"
    ws.cell(c6, _column(ws, "من")).value = "13:00"
    ws.cell(c6, _column(ws, "إلى")).value = "14:15"
    r = _upload(admin, _save(wb))
    assert r.status_code == 200 and r.json()["saved"], r.text
    assert r.json()["custom"] and r.json()["closed"] == 1

    student = sign_in("441000001")
    oop = next(c for c in student.get("/api/schedule/courses").json()["courses"] if c["code"] == "عال 1241")
    by_id = {s["id"]: s for s in oop["sections"]}
    c5_json, c6_json = by_id["C5"], by_id["C6"]
    assert c5_json["enrolled"] == c5_json["capacity"]          # shown as full
    assert c6_json["crn"] == "99001" and c6_json["instructor"] == "د. تجربة"
    assert [(m["day"], m["start"]) for m in c6_json["meetings"]] == [(1, 780), (3, 780)]

    # The generator never picks the full section, unless closed ones are allowed.
    picks = {p["section"] for s in student.post("/api/schedule/generate", json={"courses": ["عال 1241"]}).json()["schedules"]
             for p in s["picks"]}
    assert "C5" not in picks and "C6" in picks
    picks = {p["section"] for s in student.post("/api/schedule/generate",
                                                json={"courses": ["عال 1241"], "include_closed": True}).json()["schedules"]
             for p in s["picks"]}
    assert {"C5", "C6"} <= picks

    # Back to the built-in data.
    assert admin.post("/api/admin/courses/reset").json()["custom"] is False
    oop = next(c for c in student.get("/api/schedule/courses").json()["courses"] if c["code"] == "عال 1241")
    assert {s["id"]: s for s in oop["sections"]}["C6"]["crn"] != "99001"


def test_a_file_with_mistakes_is_not_saved_and_each_row_is_reported(sign_in):
    admin = sign_in("admin")
    wb, ws = _sheet(admin.get("/api/admin/courses/excel").content)
    row = _row_of(ws, "عال 1140")
    ws.cell(row, _column(ws, "من")).value = "25:00"
    ws.cell(row + 1, _column(ws, "الأيام")).value = "الجمعة"
    ws.cell(row + 2, _column(ws, "المقاعد المأخوذة")).value = 999
    ws.cell(row + 3, _column(ws, "الرقم المرجعي (CRN)")).value = ws.cell(row, _column(ws, "الرقم المرجعي (CRN)")).value
    r = _upload(admin, _save(wb))
    body = r.json()
    assert r.status_code == 200 and body["saved"] is False
    found = {(p["row"], p["code"]) for p in body["problems"]}
    assert {(row, "bad_time"), (row + 1, "bad_days"), (row + 2, "over_capacity"), (row + 3, "duplicate_crn")} <= found
    assert admin.get("/api/admin/courses").json()["custom"] is False   # nothing was saved


def test_overlapping_times_clash_even_in_different_slots(sign_in):
    admin = sign_in("admin")
    wb, ws = _sheet(admin.get("/api/admin/courses/excel").content)
    # Discrete 1 (Sun/Tue 08:00-09:15) and Computing Ethics moved to Sun/Tue 09:00-10:15.
    row = _row_of(ws, "عال 1111")
    ws.cell(row, _column(ws, "الأيام")).value = "الأحد/الثلاثاء"
    ws.cell(row, _column(ws, "من")).value = "09:00"
    ws.cell(row, _column(ws, "إلى")).value = "10:15"
    assert _upload(admin, _save(wb)).json()["saved"]
    res = service.generate(["عال 1100", "عال 1111"], locks={"عال 1100": "C2", "عال 1111": "C1"})
    assert res["schedules"] == [] and res["failure_reason"]


def test_wrong_files_are_refused(sign_in):
    admin = sign_in("admin")
    assert _upload(admin, b"not excel", "courses.pdf").status_code == 415
    assert _upload(admin, b"not excel").status_code == 422
    from openpyxl import Workbook
    wb = Workbook()
    wb.active.append(["رمز المقرر", "اسم المقرر"])
    r = _upload(admin, _save(wb))
    assert r.status_code == 422 and "missing these columns" in r.json()["detail"]


def test_excel_times_and_days_in_other_forms():
    from datetime import time
    assert offerings._time(time(8, 0)) == "08:00"
    assert offerings._time(0.5) == "12:00"
    assert offerings._time("1:30 PM") == "13:30"
    assert offerings._days("الثلاثاء والأحد") == ["الأحد", "الثلاثاء"]
    assert offerings._days("Mon, Wed") == ["الاثنين", "الأربعاء"]
    assert offerings._exam("5-1-2027 8:00 am") == "05-01-2027 08:00 AM"


def test_the_project_keeps_a_file_for_the_built_in_data():
    # If course_data.py changes, rebuild it:
    #   open(offerings.DEFAULT_FILE, "wb").write(offerings.to_excel(offerings.default_offerings()))
    courses, problems = offerings.parse_excel(offerings.DEFAULT_FILE.read_bytes())
    assert problems == [] and courses == offerings.default_offerings()


def test_everyone_downloads_the_last_uploaded_file_as_it_was(sign_in):
    admin = sign_in("admin")
    first = admin.get("/api/admin/courses/excel").content
    assert first == offerings.DEFAULT_FILE.read_bytes()       # nothing uploaded yet

    wb, ws = _sheet(first)
    ws.cell(_row_of(ws, "عال 1241", "C5"), _column(ws, "اسم الدكتور")).value = "د. ملف مرفوع"
    ws["P1"] = "ملاحظة من المدير"                               # kept, even though the site ignores it
    uploaded = _save(wb)
    assert _upload(admin, uploaded, "مقررات الترم.xlsx").json()["saved"]

    # Another admin gets the very same file, not a new one made from the data.
    other = sign_in("admin")
    r = other.get("/api/admin/courses/excel")
    assert r.content == uploaded
    assert "filename*=UTF-8''" in r.headers["content-disposition"]

    # Back to the built-in data: the project's file again.
    admin.post("/api/admin/courses/reset")
    assert admin.get("/api/admin/courses/excel").content == offerings.DEFAULT_FILE.read_bytes()
