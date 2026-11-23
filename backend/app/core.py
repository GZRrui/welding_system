import os
from pathlib import Path

PACKAGE_ROOT = os.getenv("MODEL_PACKAGE_DIR")
MANIFEST_SHA256 = os.getenv("MODEL_MANIFEST_SHA256")
ROOT = Path(__file__).resolve().parents[2]
SOURCE = Path(PACKAGE_ROOT or os.getenv("ALGORITHM_ROOT", str(ROOT.parent / "weldingproject_v2"))).resolve()
DATABASE_URL_FILE = os.getenv("DATABASE_URL_FILE")
DATABASE_URL = (Path(DATABASE_URL_FILE).read_text().strip() if DATABASE_URL_FILE else None) or os.getenv("DATABASE_URL", "sqlite:///" + (ROOT / "runtime/db/system.db").as_posix())
ORIGINS = os.getenv("CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").split(",")
for name in ("db", "exports", "logs"):
    (ROOT / "runtime" / name).mkdir(parents=True, exist_ok=True)
