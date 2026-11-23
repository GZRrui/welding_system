import hashlib
import hmac
import os
import secrets
import time
from getpass import getpass

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import case, delete, update

from app.db import Admin, AuditEvent, LoginSession, Session

COOKIE = "welding_session"
SECURE = os.getenv("SESSION_SECURE", "true").lower() != "false"
IDLE = int(os.getenv("SESSION_IDLE_SECONDS", "1800"))
MAX_AGE = int(os.getenv("SESSION_MAX_SECONDS", "28800"))
LIMIT = int(os.getenv("LOGIN_FAILURE_LIMIT", "5"))
WINDOW = int(os.getenv("LOGIN_WINDOW_SECONDS", "60"))
if min(IDLE, MAX_AGE, LIMIT, WINDOW) < 1:
    raise ValueError("Session and login settings must be positive")

hasher = PasswordHasher()
router = APIRouter(prefix="/api/v1/auth")


class Login(BaseModel):
    username: str = Field(max_length=128)
    password: str = Field(max_length=1024)


class Password(BaseModel):
    current_password: str = Field(max_length=1024)
    new_password: str = Field(max_length=1024)


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def audit(db, action, outcome, request=None, resource=""):
    db.add(AuditEvent(
        created=int(time.time()), action=action, outcome=outcome,
        remote=request.client.host if request and request.client else "",
        resource=resource,
    ))


def locked_admin(db):
    # Acquire a write lock before reading. This also serializes SQLite writers.
    db.execute(update(Admin).where(Admin.id == 1).values(id=1))
    return db.get(Admin, 1)


def matches(encoded, password):
    try:
        return hasher.verify(encoded, password)
    except VerifyMismatchError:
        return False


def validate_password(password):
    if not 12 <= len(password) <= 1024:
        raise ValueError("密码长度须为 12 至 1024 个字符")


def reset_password(password):
    validate_password(password)
    encoded = hasher.hash(password)
    with Session.begin() as db:
        admin = locked_admin(db)
        if admin is None:
            db.add(Admin(id=1, password_hash=encoded, failures=0, window_start=0))
        else:
            admin.password_hash = encoded
            admin.failures = admin.window_start = 0
        db.execute(delete(LoginSession))
        audit(db, "cli_password_reset", "ok")


def require_session(request: Request):
    token = request.cookies.get(COOKIE)
    if not token:
        raise HTTPException(401, "请登录")
    now = int(time.time())
    with Session.begin() as db:
        session = db.get(LoginSession, digest(token))
        if not session or now >= session.created + MAX_AGE or now >= session.last_seen + IDLE:
            raise HTTPException(401, "会话已过期，请重新登录")
        if request.method not in {"GET", "HEAD", "OPTIONS"} and not hmac.compare_digest(
            request.headers.get("X-CSRF-Token", "").encode(), session.csrf.encode(),
        ):
            raise HTTPException(403, "CSRF 校验失败")
        changed = db.execute(
            update(LoginSession)
            .where(LoginSession.id == session.id, LoginSession.last_seen > now - IDLE)
            .values(last_seen=case((LoginSession.last_seen < now, now), else_=LoginSession.last_seen))
        ).rowcount
        if not changed:
            raise HTTPException(401, "会话已失效，请重新登录")
        return session


def clear_cookie(response):
    response.delete_cookie(COOKIE, secure=SECURE, httponly=True, samesite="strict")


@router.post("/login")
def login(body: Login, request: Request, response: Response):
    now = int(time.time())
    failure = None
    with Session.begin() as db:
        admin = locked_admin(db)
        if admin is None:
            audit(db, "login", "uninitialized", request)
            failure = HTTPException(503, "请在服务器上初始化管理员")
        else:
            if now >= admin.window_start + WINDOW:
                admin.window_start, admin.failures = now, 0
            if admin.failures >= LIMIT:
                audit(db, "login", "limited", request)
                failure = HTTPException(429, "尝试次数过多，请稍后再试", headers={
                    "Retry-After": str(admin.window_start + WINDOW - now),
                })
            elif not matches(admin.password_hash, body.password) or body.username != "admin":
                admin.failures += 1
                audit(db, "login", "denied", request)
                failure = HTTPException(401, "用户名或密码错误")
            else:
                admin.failures = 0
                db.execute(delete(LoginSession).where(
                    (LoginSession.created <= now - MAX_AGE) | (LoginSession.last_seen <= now - IDLE),
                ))
                old = request.cookies.get(COOKIE)
                if old:
                    db.execute(delete(LoginSession).where(LoginSession.id == digest(old)))
                token, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
                db.add(LoginSession(id=digest(token), csrf=csrf, created=now, last_seen=now))
                audit(db, "login", "ok", request)
    if failure:
        raise failure
    response.headers["Cache-Control"] = "no-store"
    response.set_cookie(COOKIE, token, max_age=MAX_AGE, secure=SECURE, httponly=True, samesite="strict")
    return {"username": "admin", "csrf_token": csrf}


@router.get("/session")
def current_session(response: Response, session: LoginSession = Depends(require_session)):
    response.headers["Cache-Control"] = "no-store"
    return {"username": "admin", "csrf_token": session.csrf}


@router.post("/logout")
def logout(request: Request, response: Response, session: LoginSession = Depends(require_session)):
    with Session.begin() as db:
        db.execute(delete(LoginSession).where(LoginSession.id == session.id))
        audit(db, "logout", "ok", request)
    clear_cookie(response)
    return {"status": "ok"}


@router.post("/password")
def change_password(
    body: Password, request: Request, response: Response, session: LoginSession = Depends(require_session),
):
    validate_password(body.new_password)
    failure = None
    with Session.begin() as db:
        admin = locked_admin(db)
        if not db.get(LoginSession, session.id):
            raise HTTPException(401, "会话已失效，请重新登录")
        if not matches(admin.password_hash, body.current_password):
            audit(db, "password_change", "denied", request)
            failure = HTTPException(400, "当前密码错误")
        else:
            admin.password_hash = hasher.hash(body.new_password)
            db.execute(delete(LoginSession))
            audit(db, "password_change", "ok", request)
    if failure:
        raise failure
    clear_cookie(response)
    return {"status": "ok"}


if __name__ == "__main__":
    first = getpass("Admin password: ")
    if first != getpass("Repeat password: "):
        raise SystemExit("Passwords do not match")
    try:
        reset_password(first)
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    print("Admin password updated. All sessions revoked.")
