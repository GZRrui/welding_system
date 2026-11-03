import numpy as np
import pytest
from fastapi.testclient import TestClient

from app import ml
from app import services as svc
from app.main import app

CURRENT = dict(current_A=210, voltage_V=27.2, ambient_C=80, speed_m_s=0.006, process_order=1)


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def test_prediction_parity_and_history(client):
    ids = []
    for version in ml.RUNS:
        response = client.post("/api/v1/predict", json={"model": version, "current": CURRENT})
        assert response.status_code == 200
        result = response.json()
        original = ml.w.predict(ml.bundle(version), CURRENT)
        for target in ml.w.TARGETS:
            assert result["outputs"][target]["prediction"] == pytest.approx(
                original["outputs"][target]["prediction"], abs=1e-12
            )
        ids.append(result["id"])
    records = [client.get("/api/v1/tasks/" + rid).json() for rid in ids]
    assert records[0]["model_id"] != records[1]["model_id"]
    assert all(r["tolerance_id"] == ml.TV for r in records)


def test_invalid(client):
    for values in [dict(CURRENT, current_A=999), dict(CURRENT, process_order=3)]:
        assert client.post("/api/v1/predict", json={"current": values}).status_code == 422
    req = {
        "current": CURRENT,
        "steps": dict(current_A=0, voltage_V=0.8, ambient_C=10, speed_m_s=0.0005),
        "max_change": dict(current_A=0, voltage_V=0, ambient_C=0, speed_m_s=0),
    }
    assert client.post("/api/v1/tasks", json=req).status_code == 422


def test_trend_fixed(client):
    result = client.post("/api/v1/trend", json={"current": CURRENT, "axis": "current_A", "points": 3}).json()
    assert len(result["series"]) == 6
    for row in result["series"]:
        for key in ["voltage_V", "ambient_C", "speed_m_s"]:
            assert row["inputs"][key] == CURRENT[key]


def test_search_limits_and_budget():
    req = {
        "model": "enhanced",
        "current": CURRENT,
        "steps": dict(current_A=5, voltage_V=0.8, ambient_C=10, speed_m_s=0.0005),
        "max_change": dict(current_A=5, voltage_V=0, ambient_C=0, speed_m_s=0),
        "locked": {"ambient_C": 80},
        "orders": [1],
    }
    svc.validate_search(req)
    grid = ml.decision.grid(ml.bundle("enhanced"), svc.grid_request(req))
    assert np.all(abs(grid.current_A - 210) <= 5)
    assert np.all(grid.ambient_C == 80)
    result = ml.predict("enhanced", CURRENT)
    for key, limit in ml.LIMITS.items():
        item = result["outputs"][key]
        radius = ml.bundle("enhanced")["models"][(1, key)]["radius"]
        budget = (
            ml.TOL["model_error_budget_displacement"] / 1000
            if key.endswith("_m")
            else ml.TOL["model_error_budget_strain"]
        )
        assert item["conservative_upper"] == pytest.approx(item["prediction"] + max(budget, radius))
        assert item["feasible"] == (item["conservative_upper"] <= limit)


def test_async_decision_no_solution(client):
    import time

    current = dict(CURRENT, current_A=240, voltage_V=30.4, ambient_C=140, speed_m_s=0.004)
    req = {
        "current": current,
        "steps": {"current_A": 5, "voltage_V": 0.8, "ambient_C": 10, "speed_m_s": 0.0005},
        "max_change": {k: 0 for k in ml.bundle("enhanced")["bounds"]},
        "orders": [1],
    }
    response = client.post("/api/v1/tasks", json=req)
    assert response.status_code == 202
    rid = response.json()["id"]
    for _ in range(100):
        result = client.get("/api/v1/tasks/" + rid).json()
        if result["status"] not in ["queued", "running"]:
            break
        time.sleep(0.05)
    assert result["status"] == "completed", result
    assert result["result"]["manifest"]["evaluated"] == 1
    assert not result["result"]["recommendations"]
    assert "无可行解" in result["result"]["message"]
    assert client.get("/api/v1/tasks/" + rid + "/exports/recommendations").status_code == 200
