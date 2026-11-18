"""Students creating their own account from the sign-in page."""

import pytest

from src.accounts import api, store

NEW = {"username": "443000123", "name": "Faisal Saad Alharbi", "password": "my-pass-123"}


@pytest.fixture(autouse=True)
def fresh_limits():
    api._signups.clear()
    yield
    api._signups.clear()


def test_a_student_signs_up_and_is_signed_in_as_a_student(sign_in):
    client = sign_in()
    r = client.post("/api/auth/register", json=NEW)
    assert r.status_code == 201, r.text
    user = r.json()["user"]
    assert user["role"] == "student" and user["username"] == "443000123" and not user["must_change_password"]
    assert "password_hash" not in user
    # Signed in right away, and can sign in again with the chosen password.
    assert client.get("/api/auth/me").json()["user"]["id"] == user["id"]
    assert sign_in().post("/api/auth/login", json={"username": "443000123", "password": "my-pass-123"}).status_code == 200
    # Gets a sample academic record like the other students.
    assert store.get_profile(user["id"]).get("transcript")


def test_sign_up_can_only_make_students(sign_in):
    r = sign_in().post("/api/auth/register", json={**NEW, "role": "admin"})
    assert r.status_code == 201 and r.json()["user"]["role"] == "student"


def test_sign_up_checks_its_fields(sign_in):
    client = sign_in()
    assert client.post("/api/auth/register", json={**NEW, "username": "admin2"}).status_code == 422
    assert client.post("/api/auth/register", json={**NEW, "name": "Faisal"}).status_code == 422
    assert client.post("/api/auth/register", json={**NEW, "password": "short"}).status_code == 422


def test_an_existing_university_id_cannot_sign_up_again(sign_in):
    r = sign_in().post("/api/auth/register", json={**NEW, "username": "441000001"})
    assert r.status_code == 409


def test_sign_up_can_be_turned_off_and_is_rate_limited(sign_in, monkeypatch):
    monkeypatch.setattr(api, "ALLOW_SIGNUP", False)
    assert sign_in().post("/api/auth/register", json=NEW).status_code == 403

    monkeypatch.setattr(api, "ALLOW_SIGNUP", True)
    monkeypatch.setattr(api, "SIGNUPS_PER_HOUR", 2)
    client = sign_in()
    for i in range(2):
        assert client.post("/api/auth/register", json={**NEW, "username": f"44300099{i}"}).status_code == 201
    assert client.post("/api/auth/register", json={**NEW, "username": "443000999"}).status_code == 429
