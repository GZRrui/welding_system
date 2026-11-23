import hashlib
import importlib.metadata
import json
import logging
import math
import uuid
from concurrent.futures import ThreadPoolExecutor

from sqlalchemy import select

from app import ml
from app.auth import audit
from app.core import ROOT
from app.db import Batch, Candidate, ModelVersion, Record, Session, Tolerance

pool = ThreadPoolExecutor(max_workers=1)


def register():
    with Session.begin() as db:
        if not db.get(Tolerance, ml.TV):
            db.add(Tolerance(id=ml.TV, config=ml.TOL))
        for version, rid in ml.RUNS.items():
            if not db.get(ModelVersion, rid):
                path = ml.run(version) / "bundle.joblib"
                metadata = {
                    "source": str(path),
                    "sha256": hashlib.file_digest(path.open("rb"), "sha256").hexdigest(),
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
            task.result = {"error": "服务重启中断任务，请重新提交；历史不会自动重算"}


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
            audit(db, kind, "ok", request, rid)
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
        out = ROOT / "runtime/exports" / rid
        ml.decision.optimize(ml.run(req["model"]), grid_request(req), out)
        rows = ml.records(out / "recommendations.csv")
        queue = ml.records(out / "ansys_verification_queue.csv")
        current = ml.predict(req["model"], req["current"])
        satisfied = all(v.get("feasible", True) for v in current["outputs"].values())
        result = {
            "manifest": json.loads((out / "manifest.json").read_text()),
            "recommendations": rows,
            "queue": queue,
            "message": "当前工况已满足代理约束，无需调整"
            if satisfied
            else ("代理约束满足候选，待ANSYS复核" if rows else "设定步长与调整范围内无可行解"),
        }
        with Session.begin() as db:
            r = db.get(Record, rid)
            r.status, r.result = "completed", result
            for i, row in enumerate(rows):
                db.add(Candidate(id=f"{rid}-{i}", task_id=rid, data=row, review_status="pending", notes=""))
    except Exception as exc:
        logging.exception("task %s failed", rid)
        with Session.begin() as db:
            r = db.get(Record, rid)
            r.status, r.result = "failed", {"error": str(exc)}
