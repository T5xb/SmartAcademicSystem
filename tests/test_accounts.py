"""Sign-in, roles, saved chats, profiles, user management and source files."""

import os

import pytest

from src.accounts import documents, store
from src.accounts.security import hash_password, verify_password

STUDENT, STUDENT_2, ADVISOR, ADMIN = "441000001", "441000002", "advisor", "admin"


# ------------------------------------------------------------- passwords


def test_password_hash_verifies_and_is_salted():
    first, second = hash_password("test12345"), hash_password("test12345")
    assert first != second and "test12345" not in first
    assert verify_password("test12345", first)
    assert not verify_password("test1234", first)
    assert not verify_password("test12345", "not-a-hash")


# ---------------------------------------------------------------- sign-in


def test_preset_accounts_are_one_admin_one_advisor_three_students(sign_in):
    roles = [u["role"] for u in store.list_users()]
    assert sorted(roles) == ["admin", "advisor", "student", "student", "student"]
    # A restart doesn't create them again or reset a changed password.
    user = store.get_user_by_username(STUDENT)
    store.set_password(user["id"], "another-pass", must_change_password=False)
    assert store.seed_preset_accounts() == []
    assert verify_password("another-pass", store.get_user_by_username(STUDENT)["password_hash"])


def test_login_sets_a_cookie_scripts_cannot_read(sign_in):
    client = sign_in()
    r = client.post("/api/auth/login", json={"username": " 441000001 ", "password": "test12345"})
    assert r.status_code == 200
    assert r.json()["user"]["role"] == "student" and "password_hash" not in r.json()["user"]
    assert "httponly" in r.headers["set-cookie"].lower()
    assert client.get("/api/auth/me").json()["user"]["username"] == STUDENT


def test_wrong_password_and_unknown_account_get_the_same_answer(sign_in):
    client = sign_in()
    wrong = client.post("/api/auth/login", json={"username": STUDENT, "password": "nope-nope"})
    unknown = client.post("/api/auth/login", json={"username": "nobody", "password": "nope-nope"})
    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json() == unknown.json()
    assert client.get("/api/auth/me").status_code == 401


def test_repeated_wrong_passwords_are_paused(sign_in, monkeypatch):
    from src.accounts import api

    monkeypatch.setattr(api, "LOGIN_ATTEMPTS", 3)
    client = sign_in()
    for _ in range(3):
        assert client.post(
            "/api/auth/login", json={"username": STUDENT, "password": "wrong-pass"}
        ).status_code == 401
    r = client.post("/api/auth/login", json={"username": STUDENT, "password": "test12345"})
    assert r.status_code == 429


def test_logout_ends_the_session(sign_in):
    client = sign_in(STUDENT)
    assert client.post("/api/auth/logout").status_code == 200
    assert client.get("/api/auth/me").status_code == 401


def test_everything_but_the_public_routes_needs_a_session(sign_in):
    client = sign_in()
    assert client.get("/api/health").status_code == 200
    assert client.get("/api/starters").status_code == 200
    for method, path in [
        ("post", "/api/chat"), ("get", "/api/schedule/courses"), ("post", "/api/schedule/generate"),
        ("get", "/api/me/chats"), ("get", "/api/me/profile"), ("get", "/api/advisor/students"),
        ("get", "/api/admin/users"), ("get", "/api/admin/files"), ("post", "/api/admin/index/rebuild"),
    ]:
        assert getattr(client, method)(path).status_code == 401, path


# ------------------------------------------------------------------ roles


def test_each_role_only_opens_its_own_routes(sign_in):
    student, advisor, admin = sign_in(STUDENT), sign_in(ADVISOR), sign_in(ADMIN)

    assert student.get("/api/advisor/students").status_code == 403
    assert student.get("/api/admin/users").status_code == 403
    assert student.get("/api/admin/files").status_code == 403

    assert advisor.get("/api/advisor/students").status_code == 200
    assert advisor.get("/api/admin/users").status_code == 403
    assert advisor.post("/api/admin/index/rebuild").status_code == 403

    assert admin.get("/api/admin/users").status_code == 200
    assert admin.get("/api/advisor/students").status_code == 200


# ----------------------------------------------- student: chats, profile


def test_chats_come_back_after_signing_in_again_and_stay_private(sign_in):
    chat = {"id": "c1", "title": "الانسحاب", "messages": [{"role": "user", "text": "كيف أنسحب؟"}]}
    client = sign_in(STUDENT)
    assert client.put("/api/me/chats/c1", json={"chat": chat}).status_code == 200
    chat["messages"].append({"role": "bot", "text": "..."})
    assert client.put("/api/me/chats/c1", json={"chat": chat}).status_code == 200
    client.post("/api/auth/logout")

    again = sign_in(STUDENT)
    assert again.get("/api/me/chats").json()["chats"] == [chat]
    # Another student sees none of it, and can't delete it.
    other = sign_in(STUDENT_2)
    assert other.get("/api/me/chats").json()["chats"] == []
    other.delete("/api/me/chats/c1")
    assert len(again.get("/api/me/chats").json()["chats"]) == 1

    again.delete("/api/me/chats/c1")
    assert again.get("/api/me/chats").json()["chats"] == []


def test_chat_ids_and_sizes_are_checked(sign_in):
    client = sign_in(STUDENT)
    assert client.put("/api/me/chats/bad id!", json={"chat": {}}).status_code == 422
    huge = {"messages": [{"text": "x" * (store.MAX_CHAT_BYTES + 1)}]}
    assert client.put("/api/me/chats/c1", json={"chat": huge}).status_code == 413


def test_profile_and_planner_are_kept_and_the_advisor_sees_them(sign_in):
    client = sign_in(STUDENT)
    client.put("/api/me/profile", json={"major": "علوم الحاسب", "email": "a@example.com"})
    client.put("/api/me/planner", json={"planner": {"selected": ["CS 1301"]}})
    store.update_profile(
        store.get_user_by_username(STUDENT)["id"],
        {"transcript": {"gpa": 4.5, "earned_hours": 60, "completed": ["CS 1301", "CS 1302"]}},
    )
    client.post("/api/auth/logout")

    profile = sign_in(STUDENT).get("/api/me/profile").json()["profile"]
    assert profile["major"] == "علوم الحاسب" and profile["planner"] == {"selected": ["CS 1301"]}
    # Saving one part leaves the others.
    assert profile["transcript"]["gpa"] == 4.5

    advisor = sign_in(ADVISOR)
    listed = {s["username"]: s for s in advisor.get("/api/advisor/students").json()["students"]}
    assert set(listed) == {"441000001", "441000002", "441000003"}
    assert listed[STUDENT]["gpa"] == 4.5 and listed[STUDENT]["completed_count"] == 2
    assert listed[STUDENT_2]["has_transcript"] is False

    detail = advisor.get(f"/api/advisor/students/{listed[STUDENT]['id']}").json()
    assert detail["profile"]["transcript"]["completed"] == ["CS 1301", "CS 1302"]
    assert "password_hash" not in detail["user"]
    # Only students can be opened this way.
    admin_id = store.get_user_by_username(ADMIN)["id"]
    assert advisor.get(f"/api/advisor/students/{admin_id}").status_code == 404


# ---------------------------------------------------------- admin: users


def test_admin_adds_a_user_who_must_change_the_temporary_password(sign_in):
    admin = sign_in(ADMIN)
    r = admin.post("/api/admin/users", json={"username": "441000009", "name": "طالب جديد", "role": "student"})
    assert r.status_code == 201
    temporary = r.json()["temporary_password"]
    assert admin.post(
        "/api/admin/users", json={"username": "441000009", "name": "مكرر", "role": "student"}
    ).status_code == 409
    # The admin can't create another admin.
    assert admin.post(
        "/api/admin/users", json={"username": "admin2", "name": "x", "role": "admin"}
    ).status_code == 422

    new = sign_in()
    r = new.post("/api/auth/login", json={"username": "441000009", "password": temporary})
    assert r.json()["user"]["must_change_password"] is True
    assert new.get("/api/me/chats").status_code == 403
    assert new.post(
        "/api/auth/password", json={"current_password": "wrong-one", "new_password": "my-new-pass"}
    ).status_code == 400
    assert new.post(
        "/api/auth/password", json={"current_password": temporary, "new_password": "short"}
    ).status_code == 422
    assert new.post(
        "/api/auth/password", json={"current_password": temporary, "new_password": "my-new-pass"}
    ).status_code == 200
    assert new.get("/api/me/chats").status_code == 200


def test_disabling_an_account_signs_it_out_and_blocks_sign_in(sign_in):
    admin, student = sign_in(ADMIN), sign_in(STUDENT)
    student_id = store.get_user_by_username(STUDENT)["id"]
    assert admin.patch(f"/api/admin/users/{student_id}", json={"active": False}).status_code == 200
    assert student.get("/api/auth/me").status_code == 401
    r = sign_in().post("/api/auth/login", json={"username": STUDENT, "password": "test12345"})
    assert r.status_code == 403

    admin.patch(f"/api/admin/users/{student_id}", json={"active": True})
    assert sign_in(STUDENT).get("/api/auth/me").status_code == 200
    # An admin can't lock themselves out.
    admin_id = store.get_user_by_username(ADMIN)["id"]
    assert admin.patch(f"/api/admin/users/{admin_id}", json={"active": False}).status_code == 400


def test_reset_password_signs_the_user_out_and_gives_a_temporary_one(sign_in):
    admin, student = sign_in(ADMIN), sign_in(STUDENT)
    student_id = store.get_user_by_username(STUDENT)["id"]
    temporary = admin.post(f"/api/admin/users/{student_id}/reset-password").json()["temporary_password"]
    assert student.get("/api/auth/me").status_code == 401
    client = sign_in()
    assert client.post(
        "/api/auth/login", json={"username": STUDENT, "password": "test12345"}
    ).status_code == 401
    r = client.post("/api/auth/login", json={"username": STUDENT, "password": temporary})
    assert r.json()["user"]["must_change_password"] is True


# ---------------------------------------------------------- admin: files


@pytest.fixture
def docs(tmp_path, monkeypatch):
    root = tmp_path / "docs"
    (root / "calendar").mkdir(parents=True)
    (root / "calendar" / "التقويم_1448.txt").write_text("old calendar", encoding="utf-8")
    (tmp_path / "secret.txt").write_text("outside", encoding="utf-8")
    monkeypatch.setenv("DATA_DIR", str(root))
    monkeypatch.setenv("DOCS_BACKUP_DIR", str(tmp_path / "backup"))
    return root


def _backups(tmp_path) -> list[str]:
    return [
        os.path.join(folder, name).replace(os.sep, "/")
        for folder, _, names in os.walk(tmp_path / "backup") for name in names
    ]


def test_admin_lists_and_uploads_files(sign_in, docs):
    admin = sign_in(ADMIN)
    listing = admin.get("/api/admin/files").json()
    assert [f["path"] for f in listing["files"]] == ["calendar/التقويم_1448.txt"]
    assert listing["folders"] == ["", "calendar"] and listing["index"]["stale"] is False

    r = admin.post(
        "/api/admin/files", data={"folder": "calendar"},
        files={"file": ("متطلبات.md", "# المتطلبات".encode(), "text/markdown")},
    )
    assert r.status_code == 201 and r.json()["index"]["stale"] is True
    assert (docs / "calendar" / "متطلبات.md").read_text(encoding="utf-8") == "# المتطلبات"
    # The same name again is refused, not silently overwritten.
    r = admin.post(
        "/api/admin/files", data={"folder": "calendar"}, files={"file": ("متطلبات.md", b"x", "text/markdown")}
    )
    assert r.status_code == 409


def test_replace_puts_the_new_file_in_the_old_ones_place_and_keeps_a_backup(sign_in, docs, tmp_path):
    admin = sign_in(ADMIN)
    r = admin.post(
        "/api/admin/files/replace", data={"path": "calendar/التقويم_1448.txt"},
        files={"file": ("calendar-final.md", "new calendar".encode(), "text/markdown")},
    )
    assert r.status_code == 200
    # Same folder, same name, the new file's type; the old one is not indexed any more.
    assert r.json()["file"]["path"] == "calendar/التقويم_1448.md"
    assert sorted(os.listdir(docs / "calendar")) == ["التقويم_1448.md"]
    assert (docs / "calendar" / "التقويم_1448.md").read_text(encoding="utf-8") == "new calendar"
    backups = _backups(tmp_path)
    assert len(backups) == 1 and backups[0].endswith("calendar/التقويم_1448.txt")
    assert admin.get("/api/admin/index").json()["stale"] is True

    # With keep_name off, the new file keeps its own name.
    r = admin.post(
        "/api/admin/files/replace", data={"path": "calendar/التقويم_1448.md", "keep_name": "false"},
        files={"file": ("التقويم_1449.txt", b"next year", "text/plain")},
    )
    assert r.json()["file"]["path"] == "calendar/التقويم_1449.txt"
    assert sorted(os.listdir(docs / "calendar")) == ["التقويم_1449.txt"]


def test_file_routes_refuse_paths_outside_the_documents_and_other_types(sign_in, docs, tmp_path):
    admin = sign_in(ADMIN)
    upload = {"file": ("x.txt", b"x", "text/plain")}
    assert admin.post("/api/admin/files", data={"folder": ".."}, files=upload).status_code == 400
    assert admin.post(
        "/api/admin/files/replace", data={"path": "../secret.txt"}, files=upload
    ).status_code == 400
    assert admin.post("/api/admin/files/remove", json={"path": "../secret.txt"}).status_code == 400
    assert (tmp_path / "secret.txt").read_text(encoding="utf-8") == "outside"
    # A path hidden in the file name is dropped; only the name is used.
    r = admin.post("/api/admin/files", data={"folder": ""}, files={"file": ("../../evil.txt", b"x", "text/plain")})
    assert r.status_code == 201 and r.json()["file"]["path"] == "evil.txt"
    assert not (tmp_path / "evil.txt").exists()

    for name in ("run.exe", "page.html", ".env", "script.py"):
        r = admin.post("/api/admin/files", data={"folder": ""}, files={"file": (name, b"x", "text/plain")})
        assert r.status_code in (400, 415), name
    assert admin.post("/api/admin/files", data={"folder": ""}, files={"file": ("e.txt", b"", "text/plain")}).status_code == 400


def test_remove_moves_the_file_to_the_backup(sign_in, docs, tmp_path):
    admin = sign_in(ADMIN)
    assert admin.post("/api/admin/files/remove", json={"path": "calendar/التقويم_1448.txt"}).status_code == 200
    assert admin.get("/api/admin/files").json()["files"] == []
    assert len(_backups(tmp_path)) == 1
    assert admin.post("/api/admin/files/remove", json={"path": "calendar/التقويم_1448.txt"}).status_code == 404


def test_rebuild_reloads_the_chatbot_and_clears_the_stale_mark(sign_in, docs, monkeypatch):
    import time

    reloaded = []
    monkeypatch.setattr(documents, "_run_process", lambda args: None)
    monkeypatch.setattr(documents, "on_index_rebuilt", lambda: reloaded.append(True))
    monkeypatch.setattr(documents, "job", documents._Job())
    admin = sign_in(ADMIN)
    admin.post("/api/admin/files", data={"folder": ""}, files={"file": ("n.txt", b"x", "text/plain")})
    assert admin.get("/api/admin/index").json()["stale"] is True

    assert admin.post("/api/admin/index/rebuild").status_code == 202
    for _ in range(100):
        status = admin.get("/api/admin/index").json()
        if status["job"]["status"] != "running":
            break
        time.sleep(0.05)
    assert status["job"]["status"] == "done" and status["stale"] is False and status["built_at"]
    assert reloaded == [True]


def test_a_failed_rebuild_is_reported_and_only_one_job_runs(sign_in, docs, monkeypatch):
    import threading
    import time

    release = threading.Event()

    def fail(args):
        release.wait(5)
        raise RuntimeError("The embedding model did not answer")

    monkeypatch.setattr(documents, "_run_process", fail)
    monkeypatch.setattr(documents, "job", documents._Job())
    admin = sign_in(ADMIN)
    assert admin.post("/api/admin/index/rebuild").status_code == 202
    assert admin.post("/api/admin/index/rebuild").status_code == 409
    release.set()
    for _ in range(100):
        job = admin.get("/api/admin/index").json()["job"]
        if job["status"] != "running":
            break
        time.sleep(0.05)
    assert job["status"] == "error" and "embedding model" in job["message"]


def test_admin_previews_and_downloads_a_file(sign_in, docs):
    admin = sign_in(ADMIN)
    path = "calendar/التقويم_1448.txt"
    r = admin.get("/api/admin/files/preview", params={"path": path})
    assert r.json() == {"kind": "text", "text": "old calendar", "truncated": False}

    inline = admin.get("/api/admin/files/content", params={"path": path})
    assert inline.text == "old calendar"
    assert inline.headers["content-type"].startswith("text/plain")
    assert inline.headers["content-disposition"].startswith("inline")
    saved = admin.get("/api/admin/files/content", params={"path": path, "download": "true"})
    assert saved.headers["content-disposition"].startswith("attachment")
    assert "filename*=utf-8''" in saved.headers["content-disposition"]

    (docs / "plan.pdf").write_bytes(b"%PDF-1.4 test")
    assert admin.get("/api/admin/files/preview", params={"path": "plan.pdf"}).json() == {"kind": "pdf"}
    assert admin.get("/api/admin/files/content", params={"path": "plan.pdf"}).headers[
        "content-type"] == "application/pdf"

    # Only the admin, and only files inside the documents folder.
    assert admin.get("/api/admin/files/content", params={"path": "../secret.txt"}).status_code == 400
    assert admin.get("/api/admin/files/preview", params={"path": "missing.txt"}).status_code == 404
    student = sign_in(STUDENT)
    assert student.get("/api/admin/files/content", params={"path": path}).status_code == 403
    assert student.get("/api/admin/files/preview", params={"path": path}).status_code == 403


def test_preview_reads_the_text_of_a_word_file(sign_in, docs):
    import zipfile

    body = (
        '<?xml version="1.0" encoding="UTF-8"?><w:document xmlns:w="http://schemas.openxmlformats.org/'
        'wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>شروط القبول</w:t></w:r></w:p></w:body></w:document>'
    )
    with zipfile.ZipFile(docs / "rules.docx", "w") as z:
        z.writestr("word/document.xml", body)
    r = sign_in(ADMIN).get("/api/admin/files/preview", params={"path": "rules.docx"})
    assert r.json()["kind"] == "text" and "شروط القبول" in r.json()["text"]
