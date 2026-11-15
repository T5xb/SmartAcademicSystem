"""Advising tickets: students open and chat, advisors answer and close."""

from src.accounts import tickets

STUDENT, OTHER, ADVISOR, ADMIN = "441000001", "441000002", "advisor", "admin"

NEW = {"full_name": "أحمد محمد الراشد", "university_id": "441000001", "title": "إضافة مقرر بعد الحذف والإضافة"}


def open_ticket(client, **extra):
    r = client.post("/api/tickets", json={**NEW, **extra})
    assert r.status_code == 201, r.text
    return r.json()["ticket"]


def test_student_opens_a_ticket_and_advisors_see_it_as_new(sign_in):
    student, advisor = sign_in(STUDENT), sign_in(ADVISOR)
    ticket = open_ticket(student, message="أبي أضيف مقرر CS301")
    assert ticket["status"] == "new" and ticket["code"] == "TK-4001"
    assert open_ticket(student)["code"] == "TK-4002"

    mine = student.get("/api/tickets").json()["tickets"]
    assert [t["code"] for t in mine] == ["TK-4002", "TK-4001"]

    overview = advisor.get("/api/advisor/tickets/overview").json()
    assert overview["counts"]["new"] == 2 and overview["counts"]["new_today"] == 2
    assert len(overview["recent"]["new"]) == 2
    thread = advisor.get(f"/api/advisor/tickets/{ticket['id']}").json()
    assert thread["messages"][0]["body"] == "أبي أضيف مقرر CS301"


def test_ticket_form_needs_a_three_part_name_a_numeric_id_and_a_title(sign_in):
    student = sign_in(STUDENT)
    assert student.post("/api/tickets", json={**NEW, "full_name": "أحمد الراشد"}).status_code == 422
    assert student.post("/api/tickets", json={**NEW, "university_id": "abc"}).status_code == 422
    assert student.post("/api/tickets", json={**NEW, "title": ""}).status_code == 422


def test_advisor_reply_moves_it_to_in_progress_and_the_student_sees_it_unread(sign_in):
    student, advisor = sign_in(STUDENT), sign_in(ADVISOR)
    ticket = open_ticket(student)
    r = advisor.post(f"/api/advisor/tickets/{ticket['id']}/messages", json={"body": "تم الاطلاع"})
    assert r.status_code == 201 and r.json()["ticket"]["status"] == "in_progress"

    listing = student.get("/api/tickets").json()
    assert listing["unread"] == 1
    thread = student.get(f"/api/tickets/{ticket['id']}").json()
    assert [m["sender_role"] for m in thread["messages"]] == ["advisor"]
    assert student.get("/api/tickets").json()["unread"] == 0   # opening it marks it read

    # A student reply keeps it in progress.
    student.post(f"/api/tickets/{ticket['id']}/messages", json={"body": "شكراً"})
    assert student.get(f"/api/tickets/{ticket['id']}").json()["ticket"]["status"] == "in_progress"


def test_closed_ticket_takes_no_more_messages_until_reopened(sign_in):
    student, advisor = sign_in(STUDENT), sign_in(ADVISOR)
    ticket = open_ticket(student)
    closed = advisor.post(f"/api/advisor/tickets/{ticket['id']}/close").json()["ticket"]
    assert closed["status"] == "closed" and closed["closed_by"]

    assert student.post(f"/api/tickets/{ticket['id']}/messages", json={"body": "؟"}).status_code == 409
    assert advisor.post(f"/api/advisor/tickets/{ticket['id']}/messages", json={"body": "x"}).status_code == 409

    reopened = advisor.post(f"/api/advisor/tickets/{ticket['id']}/reopen").json()["ticket"]
    assert reopened["status"] == "new"   # no advisor reply yet
    assert student.post(f"/api/tickets/{ticket['id']}/messages", json={"body": "ok"}).status_code == 201


def test_students_only_see_their_own_tickets(sign_in):
    student, other = sign_in(STUDENT), sign_in(OTHER)
    ticket = open_ticket(student)
    assert other.get(f"/api/tickets/{ticket['id']}").status_code == 404
    assert other.post(f"/api/tickets/{ticket['id']}/messages", json={"body": "x"}).status_code == 404
    assert other.get("/api/tickets").json()["tickets"] == []
    # Students can't use the advisor routes, advisors can't open student tickets.
    assert student.get("/api/advisor/tickets").status_code == 403
    assert sign_in(ADVISOR).post("/api/tickets", json=NEW).status_code == 403


def test_every_advisor_and_admin_shares_the_same_tickets(sign_in):
    student = sign_in(STUDENT)
    ticket = open_ticket(student)
    sign_in(ADVISOR).post(f"/api/advisor/tickets/{ticket['id']}/messages", json={"body": "من المرشد"})
    admin_view = sign_in(ADMIN).get(f"/api/advisor/tickets/{ticket['id']}").json()
    assert [m["body"] for m in admin_view["messages"]] == ["من المرشد"]


def test_search_and_status_filter(sign_in):
    student, advisor = sign_in(STUDENT), sign_in(ADVISOR)
    first = open_ticket(student, title="تعارض اختبارات")
    open_ticket(student, title="معادلة مقرر")
    advisor.post(f"/api/advisor/tickets/{first['id']}/close")

    by_title = advisor.get("/api/advisor/tickets", params={"q": "معادلة"}).json()["tickets"]
    assert [t["title"] for t in by_title] == ["معادلة مقرر"]
    by_number = advisor.get("/api/advisor/tickets", params={"q": "TK-4001"}).json()["tickets"]
    assert [t["code"] for t in by_number] == ["TK-4001"]
    closed = advisor.get("/api/advisor/tickets", params={"status": "closed"}).json()
    assert [t["code"] for t in closed["tickets"]] == ["TK-4001"]
    assert closed["counts"] == {"all": 2, "new": 1, "in_progress": 0, "closed": 1, "new_today": 2}


def test_open_ticket_limit_per_student(sign_in, monkeypatch):
    monkeypatch.setattr(tickets, "MAX_OPEN_PER_STUDENT", 2)
    student = sign_in(STUDENT)
    open_ticket(student)
    open_ticket(student)
    assert student.post("/api/tickets", json=NEW).status_code == 429
