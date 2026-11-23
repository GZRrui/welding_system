"""Trusted source adapter. Resolve original modules once, without mutating sys.path."""

import hashlib
import importlib.util
import json
import sys
from functools import lru_cache
from pathlib import Path

import pandas as pd

from app.core import MANIFEST_SHA256, PACKAGE_ROOT, SOURCE
from app.model_release import TOLERANCE, verify

RELEASE = verify(SOURCE, MANIFEST_SHA256) if PACKAGE_ROOT else None


def module(name):
    source = SOURCE / (name + ".py")
    spec = importlib.util.spec_from_file_location(name, source)
    obj = importlib.util.module_from_spec(spec)
    sys.modules[name] = obj
    if RELEASE:
        # Execute the verified source directly, without consulting a bytecode cache.
        exec(compile(source.read_bytes(), str(source), "exec"), obj.__dict__)
    else:
        spec.loader.exec_module(obj)
    return obj


w = module("welding")
module("validate")
module("enhanced")
decision = module("decision")
RUNS = RELEASE["runs"] if RELEASE else {"enhanced": "enhanced_20261103_152620", "baseline": "20261103_145522_273665"}
TOL = json.loads((SOURCE / TOLERANCE).read_text(encoding="utf-8"))
TV = "project_v1-" + hashlib.sha256(json.dumps(TOL, sort_keys=True).encode()).hexdigest()[:12]
LIMITS = {
    "max_displacement_m": TOL["residual_displacement_limit"] / 1000,
    "total_eqv_strain_max": TOL["total_strain_limit"],
    "plastic_eqv_strain_max": TOL["plastic_strain_limit"],
}


def run(version):
    if version not in RUNS:
        raise ValueError("未知模型版本")
    return SOURCE / "artifacts/runs" / RUNS[version]


if RELEASE:
    original_load_bundle = w.load_bundle
    released_datasets = {run(key): SOURCE / RELEASE["datasets"][key] for key in RUNS}

    def release_bundle(path):
        loaded = original_load_bundle(path)
        return dict(loaded, dataset=str(released_datasets[Path(path).resolve()]))

    w.load_bundle = release_bundle


@lru_cache(maxsize=2)
def bundle(version):
    return w.load_bundle(run(version))


def predict(version, values):
    result = w.predict(bundle(version), values)
    for key, item in result["outputs"].items():
        if key in LIMITS:
            budget = (
                TOL["model_error_budget_displacement"] / 1000
                if key.endswith("_m")
                else TOL["model_error_budget_strain"]
            )
            radius = bundle(version)["models"][(values["process_order"], key)]["radius"]
            item["conservative_upper"] = item["prediction"] + max(budget, radius)
            item["limit"] = LIMITS[key]
            item["feasible"] = item["conservative_upper"] <= LIMITS[key]
    return dict(
        result,
        model_version=RUNS[version],
        tolerance_version=TV,
        risk="高电流区域历史误差较高" if values["current_A"] >= 225 else "全局区间不保证局部覆盖；需ANSYS复核",
    )


def records(path):
    return json.loads(pd.read_csv(path).to_json(orient="records"))


def dataset(version):
    path = Path(bundle(version)["dataset"])
    if not path.is_absolute():
        path = SOURCE / path
    return pd.read_csv(path / "dataset.csv")
