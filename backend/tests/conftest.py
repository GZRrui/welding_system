import os
import tempfile
from pathlib import Path

from alembic import command
from alembic.config import Config

TEST_ROOT = tempfile.TemporaryDirectory(prefix="welding-test-")
os.environ["DATABASE_URL"] = os.getenv(
    "TEST_DATABASE_URL", "sqlite:///" + (Path(TEST_ROOT.name) / "test.db").as_posix(),
)



def pytest_sessionstart():
    directory = Path(__file__).resolve().parents[1]
    config = Config(directory / "alembic.ini")
    config.set_main_option("script_location", str(directory / "migrations"))
    command.upgrade(config, "head")


def pytest_sessionfinish():
    from app.db import engine

    engine.dispose()
    TEST_ROOT.cleanup()
