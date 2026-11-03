import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SOURCE = Path(os.getenv("ALGORITHM_ROOT", str(ROOT.parent / "weldingproject_v2"))).resolve()
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///" + (ROOT / "runtime/db/system.db").as_posix())
ORIGINS = os.getenv("CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").split(",")
for name in ("db", "exports", "logs"):
    (ROOT / "runtime" / name).mkdir(parents=True, exist_ok=True)
