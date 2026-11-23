import importlib.metadata
import json
import logging
import math
import os
import subprocess
import sys
import tempfile
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import BoundedSemaphore

from sqlalchemy import select

from app import ml
from app.auth import audit
from app.core import ROOT
from app.db import Batch, Candidate, ModelVersion, Record, Session, Tolerance
from app.model_release import sha256

TASK_CAPACITY = int(os.getenv("TASK_CAPACITY", "8"))
TASK_TIMEOUT = int(os.getenv("TASK_TIMEOUT_SECONDS", "180"))
if min(TASK_CAPACITY, TASK_TIMEOUT) < 1:
    raise ValueError("Task settings must be positive")
pool = ThreadPoolExecutor(max_workers=1)
slots = BoundedSemaphore(TASK_CAPACITY)


class QueueFull(Exception):
    pass


def enqueue(values, request, retry_of=None):
    if not slots.acquire(blocking=False):
        raise QueueFull
    try:
        lineage = {"retry_of": retry_of} if retry_of else {}
        rid = save("decision", values, lineage, "queued", request=request)
        pool.submit(execute, rid, values)
    except Exception:
        slots.release()
        raise
    return rid


def register():
    with Session.begin() as db:
        if not db.get(Tolerance, ml.TV):
            db.add(Tolerance(id=ml.TV, config=ml.TOL))
        for version, rid in ml.RUNS.items():
            path = ml.run(version) / "bundle.joblib"
            fingerprint = sha256(path)
            registered = db.get(ModelVersion, rid)
            if registered and registered.metadata_json.get("sha256") != fingerprint:
                raise ValueError(f"Registered model SHA-256 mismatch: {rid}")
            if not registered:
                metadata = {
                    "source": str(path),
                    "sha256": fingerprint,
                    "release": ml.RELEASE["version"] if ml.RELEASE else None,
                    "status": "trusted_local_candidate",
                    "dependencies": {
                        p: importlib.metadata.version(p)
                        for p in ["numpy", "pandas", "scikit-learn", "xgboost", "joblib"]
                    },
                }
                db.add(ModelVersion(id=rid, metadata_json=metadata))
        for batch, frame in ml.dataset("enhanced").groupby("batch_id"):
            if not db.get(Batch, str(batch)):
                db.add(
                    Batch(
                        id=str(batch),
                        metadata_json={"samples": len(frame), "source": str(ml.bundle("enhanced")["dataset"])},
                    )
                )
        for task in db.scalars(select(Record).where(Record.status.in_(["queued", "running"]))):
            task.status = "interrupted"
            task.result = dict(task.result, error="服务重启中断任务，请显式重试")


def save(kind, req, result, status="completed", request=None):
    rid = str(uuid.uuid4())
    with Session.begin() as db:
        db.add(
            Record(
                id=rid,
                kind=kind,
                model_id=ml.RUNS[req["model"]],
                tolerance_id=ml.TV,
                request=req,
                result=result,
                status=status,
            )
        )
        if request is not None:
            audit(db, "task_retry" if result.get("retry_of") else kind, "ok", request, rid)
    return rid


def serialize(r):
    return {
        k: getattr(r, k) for k in ("id", "kind", "model_id", "tolerance_id", "status", "request", "result", "created")
    }


def grid_request(req):
    return {k: v for k, v in req.items() if k != "model"}


def validate_search(req):
    b = ml.bundle(req["model"])
    ml.predict(req["model"], req["current"])
    keys = set(b["bounds"])
    if set(req["steps"]) != keys or set(req["max_change"]) != keys:
        raise ValueError("步长和调整幅度必须包含四个连续参数")
    size = 2
    for key, (lo, hi) in b["bounds"].items():
        step, change = req["steps"][key], req["max_change"][key]
        if not math.isfinite(step) or step <= 0 or not math.isfinite(change) or change < 0:
            raise ValueError("步长必须为正有限数，调整幅度须非负")
        if key not in req["locked"]:
            size *= min(math.floor((hi - lo) / step) + 2, math.floor(2 * change / step) + 2)
    if size > 20000:
        raise ValueError("候选规模上限20000，请增大步长或锁定参数")
    grid = ml.decision.grid(b, grid_request(req))
    if len(grid) > 20000:
        raise ValueError("候选规模超过20000")


def execute(rid, req):
    try:
        with Session.begin() as db:
            db.get(Record, rid).status = "running"
        exports = ROOT / "runtime/exports"
        with tempfile.TemporaryDirectory(prefix=".task-", dir=exports) as tmp:
            out = Path(tmp) / "result"
            subprocess.run(
                [sys.executable, "-m", "app.task_worker"],
                input=json.dumps({"request": req, "output": str(out)}),
                text=True, cwd=ROOT / "backend", timeout=TASK_TIMEOUT, check=True,
            )
            rows = ml.records(out / "recommendations.csv")
            queue = ml.records(out / "ansys_verification_queue.csv")
            manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
            out.rename(exports / rid)
        current = ml.predict(req["model"], req["current"])
        satisfied = all(v.get("feasible", True) for v in current["outputs"].values())
        result = {
            "manifest": manifest,
            "recommendations": rows,
            "queue": queue,
            "message": "当前工况已满足代理约束，无需调整"
            if satisfied
            else ("代理约束满足候选，待ANSYS复核" if rows else "设定步长与调整范围内无可行解"),
        }
        with Session.begin() as db:
            r = db.get(Record, rid)
            r.status, r.result = "completed", dict(r.result, **result)
            for i, row in enumerate(rows):
                db.add(Candidate(id=f"{rid}-{i}", task_id=rid, data=row, review_status="pending", notes=""))
    except subprocess.TimeoutExpired:
        record_failure(rid, "timed_out", "推荐计算超时")
    except Exception:
        logging.exception("task %s failed", rid)
        record_failure(rid, "failed", "计算失败，请查看服务日志")
    finally:
        slots.release()


def record_failure(rid, status, error):
    with Session.begin() as db:
        task = db.get(Record, rid)
        task.status = status
        task.result = dict(task.result, error=error)
