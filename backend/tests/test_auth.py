from fastapi.testclient import TestClient
from sqlalchemy import select

from app.auth import COOKIE, LIMIT, reset_password
from app.db import AuditEvent, LoginSession, Session
from app.main import app

PASSWORD = "test admin password"


def sign_in(client, password=PASSWORD):
    res = client.post("/api/v1/auth/login", json={"username": "admin", "password": password})
    assert res.status_code == 200
    assert all(flag in res.headers["set-cookie"].lower() for flag in ("secure", "httponly", "samesite=strict"))
    return {"X-CSRF-Token": res.json()["csrf_token"]}


def test_sessions_and_password_change():
    reset_password(PASSWORD)
    with TestClient(app, base_url="https://testserver") as browser:
        for method, path in [
            ("GET", "history"), ("POST", "predict"), ("PATCH", "candidates/unknown"),
            ("GET", "tasks/unknown/exports/recommendations"),
        ]:
            assert browser.request(method, f"/api/v1/{path}", json={}).status_code == 401
        headers = sign_in(browser)
        token = browser.cookies[COOKIE]
        with Session() as db:
            assert db.get(LoginSession, token) is None
        assert browser.get("/api/v1/auth/session").status_code == 200
        assert browser.post("/api/v1/auth/logout").status_code == 403
        assert browser.post("/api/v1/auth/logout", headers=headers).status_code == 200
        assert browser.get("/api/v1/history", headers={"Cookie": f"{COOKIE}={token}"}).status_code == 401
        headers = sign_in(browser)
        with TestClient(app, base_url="https://testserver") as other:
            sign_in(other)
            res = browser.post("/api/v1/auth/password", headers=headers, json={
                "current_password": PASSWORD, "new_password": "another admin password",
            })
            assert res.status_code == 200
            assert other.get("/api/v1/auth/session").status_code == 401
            sign_in(other, "another admin password")


def test_login_rate_limit():
    reset_password(PASSWORD)
    with TestClient(app, base_url="https://testserver") as browser:
        for _ in range(LIMIT):
            assert browser.post("/api/v1/auth/login", json={"username": "admin", "password": "bad"}).status_code == 401
        res = browser.post("/api/v1/auth/login", json={"username": "admin", "password": PASSWORD})
        assert res.status_code == 429
        assert int(res.headers["retry-after"]) > 0
    with Session() as db:
        assert "limited" in db.scalars(select(AuditEvent.outcome).where(AuditEvent.action == "login")).all()
