from datetime import UTC, datetime

from sqlalchemy import JSON, ForeignKey, String, create_engine
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


engine = create_engine(DATABASE_URL)
Session = sessionmaker(engine, expire_on_commit=False)
