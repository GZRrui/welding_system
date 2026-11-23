"""Import an offline SQLite snapshot into an empty, migrated PostgreSQL database."""

import argparse
import json
import sqlite3
from contextlib import closing
from pathlib import Path

from sqlalchemy import create_engine, insert, select, text

from app.db import Batch, Candidate, ModelVersion, Record, Tolerance, engine

TABLES = [item.__table__ for item in (ModelVersion, Tolerance, Batch, Record, Candidate)]


def snapshot(source, backup):
    if not source.is_file():
        raise ValueError(f"Source database does not exist: {source}")
    with backup.open("xb"):
        pass
    with closing(sqlite3.connect(source.resolve().as_uri() + "?mode=ro", uri=True)) as old:
        with closing(sqlite3.connect(backup)) as copy:
            old.backup(copy)
            if copy.execute("PRAGMA integrity_check").fetchall() != [("ok",)]:
                raise ValueError(f"Invalid SQLite backup: {backup}")
            if copy.execute("PRAGMA foreign_key_check").fetchone():
                raise ValueError(f"SQLite history contains broken foreign keys: {backup}")


def import_history(source, backup, target=engine):
    if target.dialect.name != "postgresql":
        raise ValueError("DATABASE_URL must point to the target PostgreSQL database")
    snapshot(source, backup)
    source_db = create_engine("sqlite:///" + backup.resolve().as_posix())
    try:
        with source_db.connect() as old, target.begin() as new:
            if old.scalar(text("SELECT version_num FROM alembic_version")) not in {"001", "002"}:
                raise ValueError("Unsupported source schema version")
            if new.scalar(text("SELECT version_num FROM alembic_version")) != "002":
                raise ValueError("Upgrade target database to current schema first")
            names = ", ".join(table.name for table in TABLES)
            new.execute(text(f"LOCK TABLE {names} IN ACCESS EXCLUSIVE MODE"))
            for table in TABLES:
                if new.execute(select(table.c.id).limit(1)).first():
                    raise ValueError(f"Target history is not empty: {table.name}")
            counts = {}
            for table in TABLES:
                statement = select(table).order_by(table.c.id)
                rows = [dict(row) for row in old.execute(statement).mappings()]
                for offset in range(0, len(rows), 500):
                    new.execute(insert(table), rows[offset:offset + 500])
                actual = [dict(row) for row in new.execute(statement).mappings()]
                if actual != rows:
                    raise ValueError(f"Data verification failed: {table.name}")
                counts[table.name] = len(rows)
            return counts
    finally:
        source_db.dispose()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--backup", type=Path, required=True)
    args = parser.parse_args()
    try:
        counts = import_history(args.source, args.backup)
    except (ValueError, FileExistsError) as exc:
        parser.exit(1, f"{exc}\n")
    print(json.dumps(counts, indent=2))


if __name__ == "__main__":
    main()
