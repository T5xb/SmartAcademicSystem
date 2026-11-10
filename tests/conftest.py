"""Shared fixtures: every test gets its own empty accounts database."""

import pytest


@pytest.fixture(autouse=True)
def accounts_db(monkeypatch, tmp_path):
    from src.accounts import api, db, deps

    monkeypatch.setenv("ACCOUNTS_DB_URL", f"sqlite:///{(tmp_path / 'accounts.db').as_posix()}")
    db.reset_engine()
    deps.forget_sessions()
    api._failures.clear()
    yield
    db.reset_engine()
    deps.forget_sessions()


PASSWORD = "test12345"


@pytest.fixture
def sign_in():
    """sign_in(username) -> a TestClient signed in as that preset account."""
    from fastapi.testclient import TestClient

    import fastapi_app
    from src.accounts import store

    store.seed_preset_accounts()

    def make(username: str | None = None) -> TestClient:
        client = TestClient(fastapi_app.app)  # no lifespan: the real index isn't loaded
        if username:
            r = client.post("/api/auth/login", json={"username": username, "password": PASSWORD})
            assert r.status_code == 200, r.text
        return client

    return make
