import logging
import time
import uuid
from contextlib import asynccontextmanager

import numpy as np
from fastapi import APIRouter, Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from sqlalchemy import func, select

from app import ml
from app import services as svc
from app.auth import audit, require_session, router as auth_router
from app.core import ORIGINS, ROOT
from app.db import Batch, Candidate, ModelVersion, Record, Session
from app.schemas import Prediction, Review, Search, Trend

logging.basicConfig(filename=ROOT / "runtime/logs/backend.log", level=logging.INFO)


@asynccontextmanager
async def lifespan(app):
    svc.register()
    yield


app = FastAPI(title="薄板焊接预测与工艺决策系统", version="0.2.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware, allow_origins=ORIGINS, allow_methods=["GET", "POST", "PATCH"], allow_headers=["Content-Type", "X-CSRF-Token"]
)


@app.middleware("http")
async def trace(request: Request, call_next):
    rid = str(uuid.uuid4())
    start = time.monotonic()
    try:
        response = await call_next(request)
    except ValueError as exc:
        response = JSONResponse(status_code=422, content={"detail": str(exc), "request_id": rid})
    except Exception:
        logging.exception("request %s", rid)
        response = JSONResponse(status_code=500, content={"detail": "计算失败，请查看服务日志", "request_id": rid})
    response.headers["X-Request-ID"] = rid
    logging.info("%s %s %.3fs", rid, request.url.path, time.monotonic() - start)
    return response


@app.get("/api/v1/health")
def health():
    return {"status": "ok"}


app.include_router(auth_router)
business = APIRouter(dependencies=[Depends(require_session)])


@business.get("/api/v1/config")
def config(model: str = "enhanced"):
    return {"bounds": ml.bundle(model)["bounds"], "tolerances": ml.TOL, "tolerance_version": ml.TV, "limits": ml.LIMITS}


@business.get("/api/v1/models")
def models():
    result = []
    with Session() as db:
        for key, rid in ml.RUNS.items():
            path = ml.run(key)
            result.append(
                {
                    "key": key,
                    "version": rid,
                    "registry": db.get(ModelVersion, rid).metadata_json,
                    "metrics": ml.records(path / ("comparison.csv" if key == "enhanced" else "metrics.csv")),
                    "regional": ml.records(path / "validation/regional_errors.csv"),
                    "holdout": ml.records(path / "validation/level_holdout_metrics.csv"),
                }
            )
    return result


@business.get("/api/v1/overview")
def overview():
    with Session() as db:
        return {
            "samples": len(ml.dataset("enhanced")),
            "batches": [{"id": b.id, **b.metadata_json} for b in db.scalars(select(Batch))],
            "predictions": db.scalar(select(func.count()).select_from(Record).where(Record.kind == "prediction")),
            "tasks": db.scalar(select(func.count()).select_from(Record).where(Record.kind == "decision")),
            "reviews": {
                s: db.scalar(select(func.count()).select_from(Candidate).where(Candidate.review_status == s))
                for s in ["pending", "reviewed", "rejected"]
            },
        }


@business.post("/api/v1/predict")
def predict(req: Prediction, request: Request):
    result = ml.predict(req.model, req.current.model_dump())
    result["id"] = svc.save("prediction", req.model_dump(), result, request=request)
    return result


@business.post("/api/v1/compare")
def compare(req: Prediction):
    results = [ml.predict(req.model, dict(req.current.model_dump(), process_order=o)) for o in (1, 2)]
    return {
        "orders": results,
        "differences": {
            t: abs(results[0]["outputs"][t]["prediction"] - results[1]["outputs"][t]["prediction"])
            for t in ml.w.TARGETS
        },
        "note": "微小差异需与预测区间比较，不能据此宣称显著优越",
    }


@business.post("/api/v1/trend")
def trend(req: Trend):
    current = req.current.model_dump()
    ml.predict(req.model, current)
    lo, hi = ml.bundle(req.model)["bounds"][req.axis]
    data = ml.dataset(req.model)
    fixed = [k for k in ml.bundle(req.model)["bounds"] if k != req.axis]
    mask = np.ones(len(data), dtype=bool)
    for key in fixed:
        mask &= np.isclose(data[key], current[key], rtol=0, atol=1e-12)
    return {
        "series": [
            {
                "x": float(x),
                "order": order,
                "inputs": dict(current, **{req.axis: float(x), "process_order": order}),
                **ml.predict(req.model, dict(current, **{req.axis: float(x), "process_order": order})),
            }
            for order in (1, 2)
            for x in np.linspace(lo, hi, req.points)
        ],
        "ansys": __import__("json").loads(data[mask].to_json(orient="records")),
        "match": "其余连续参数完全匹配；无邻近替代",
        "fixed": {k: current[k] for k in fixed},
    }


@business.post("/api/v1/tasks", status_code=202)
def create_task(req: Search, request: Request):
    values = req.model_dump()
    svc.validate_search(values)
    rid = svc.save("decision", values, {}, "queued", request=request)
    svc.pool.submit(svc.execute, rid, values)
    return {"id": rid, "status": "queued"}


@business.get("/api/v1/history")
def history():
    with Session() as db:
        return [svc.serialize(r) for r in db.scalars(select(Record).order_by(Record.created.desc()).limit(200))]


@business.get("/api/v1/tasks/{rid}")
def task(rid: str):
    with Session() as db:
        r = db.get(Record, rid)
        if not r:
            raise HTTPException(404, "记录不存在")
        return dict(
            svc.serialize(r),
            candidates=[
                {"id": c.id, "data": c.data, "review_status": c.review_status, "notes": c.notes}
                for c in db.scalars(select(Candidate).where(Candidate.task_id == rid))
            ],
        )


@business.patch("/api/v1/candidates/{cid}")
def review(cid: str, req: Review, request: Request):
    with Session.begin() as db:
        c = db.get(Candidate, cid)
        if not c:
            raise HTTPException(404, "候选不存在")
        c.review_status, c.notes = req.status, req.notes
        audit(db, "review", "ok", request, cid)
    return {"status": req.status}


@business.get("/api/v1/tasks/{rid}/exports/{kind}")
def export(rid: str, kind: str, request: Request):
    task(rid)
    allowed = {"recommendations", "ansys_verification_queue", "all_candidates"}
    if kind not in allowed:
        raise HTTPException(404)
    path = ROOT / "runtime/exports" / rid / (kind + ".csv")
    if not path.is_file():
        raise HTTPException(409, "结果尚未生成")
    with Session.begin() as db:
        audit(db, "export", "ok", request, f"{rid}/{kind}")
    return FileResponse(path, filename=kind + ".csv", media_type="text/csv")


app.include_router(business)
