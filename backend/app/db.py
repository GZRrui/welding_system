from datetime import UTC, datetime

from sqlalchemy import JSON, BigInteger, CheckConstraint, ForeignKey, String, create_engine, event
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

from app.core import DATABASE_URL


class Base(DeclarativeBase):
    pass


class ModelVersion(Base):
    __tablename__ = "model_versions"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    metadata_json: Mapped[dict] = mapped_column(JSON)


class Tolerance(Base):
    __tablename__ = "tolerances"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    config: Mapped[dict] = mapped_column(JSON)


class Batch(Base):
    __tablename__ = "batches"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    metadata_json: Mapped[dict] = mapped_column(JSON)


class Record(Base):
    __tablename__ = "records"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    kind: Mapped[str] = mapped_column(String)
    model_id: Mapped[str] = mapped_column(ForeignKey("model_versions.id"))
    tolerance_id: Mapped[str] = mapped_column(ForeignKey("tolerances.id"))
    status: Mapped[str] = mapped_column(String)
    request: Mapped[dict] = mapped_column(JSON)
    result: Mapped[dict] = mapped_column(JSON, default=dict)
    created: Mapped[str] = mapped_column(String, default=lambda: datetime.now(UTC).isoformat())


class Candidate(Base):
    __tablename__ = "candidates"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    task_id: Mapped[str] = mapped_column(ForeignKey("records.id"))
    data: Mapped[dict] = mapped_column(JSON)
    review_status: Mapped[str] = mapped_column(String, default="pending")
    notes: Mapped[str] = mapped_column(String, default="")


class Admin(Base):
    __tablename__ = "admin"
    __table_args__ = (CheckConstraint("id = 1", name="only_admin"),)
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=False)
    password_hash: Mapped[str]
    failures: Mapped[int]
    window_start: Mapped[int] = mapped_column(BigInteger)


class LoginSession(Base):
    __tablename__ = "login_sessions"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    csrf: Mapped[str]
    created: Mapped[int] = mapped_column(BigInteger)
    last_seen: Mapped[int] = mapped_column(BigInteger)


class AuditEvent(Base):
    __tablename__ = "audit_events"
    id: Mapped[int] = mapped_column(primary_key=True)
    created: Mapped[int] = mapped_column(BigInteger)
    action: Mapped[str]
    outcome: Mapped[str]
    remote: Mapped[str]
    resource: Mapped[str]


engine = create_engine(DATABASE_URL)
if engine.dialect.name == "sqlite":
    @event.listens_for(engine, "connect")
    def enable_sqlite_foreign_keys(connection, _):
        connection.execute("PRAGMA foreign_keys=ON")


Session = sessionmaker(engine, expire_on_commit=False)
