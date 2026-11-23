import os
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text

from app import db
from app.import_history import import_history


def test_upgrade_v1_and_import(tmp_path, monkeypatch):
    root = Path(__file__).resolve().parents[1]
    config = Config(root / "alembic.ini")
    config.set_main_option("script_location", str(root / "migrations"))
    source = tmp_path / "legacy.db"
    sqlite = create_engine("sqlite:///" + source.as_posix())
    monkeypatch.setattr(db, "engine", sqlite)
    command.upgrade(config, "001")
    assert "admin" not in inspect(sqlite).get_table_names()
    with sqlite.begin() as connection:
        connection.execute(text("INSERT INTO model_versions VALUES ('model-v1', '{}')"))
        connection.execute(text("INSERT INTO tolerances VALUES ('tol-v1', '{}')"))
        connection.execute(text(
            "INSERT INTO records VALUES ('task', 'decision', 'model-v1', 'tol-v1', "
            "'completed', '{}', '{}', '2026-11-01T00:00:00+00:00')"
        ))
        connection.execute(text("INSERT INTO candidates VALUES ('c', 'task', '{}', 'reviewed', 'checked')"))
    command.upgrade(config, "head")
    assert "admin" in inspect(sqlite).get_table_names()
    with sqlite.connect() as connection:
        assert connection.execute(text("SELECT review_status, notes FROM candidates")).one() == ("reviewed", "checked")
    sqlite.dispose()
    url = os.getenv("TEST_IMPORT_DATABASE_URL")
    if not url:
        return
    pg = create_engine(url)
    try:
        monkeypatch.setattr(db, "engine", pg)
        command.upgrade(config, "head")
        backup = tmp_path / "snapshot.db"
        assert import_history(source, backup, pg) == {
            "model_versions": 1, "tolerances": 1, "batches": 0, "records": 1, "candidates": 1,
        }
        assert backup.is_file()
        with pg.connect() as connection:
            assert connection.execute(text("SELECT model_id, tolerance_id FROM records")).one() == ("model-v1", "tol-v1")
            assert connection.execute(text("SELECT notes FROM candidates")).scalar_one() == "checked"
        with pytest.raises(ValueError, match="not empty"):
            import_history(source, tmp_path / "second.db", pg)
    finally:
        pg.dispose()
