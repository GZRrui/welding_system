"""Build and verify a portable immutable release of the trusted welding models."""

import argparse
import hashlib
import importlib.metadata
import json
import shutil
import tempfile
from pathlib import Path, PurePosixPath

MODULES = ("welding", "validate", "enhanced", "decision")
DEPENDENCIES = ("numpy", "pandas", "scipy", "scikit-learn", "xgboost", "joblib")
TOLERANCE = "configs/engineering_tolerances.json"
RUN_ROOT = "artifacts/runs"
COMMON_REPORTS = ("validation/regional_errors.csv", "validation/level_holdout_metrics.csv")


def sha256(path):
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def versions():
    return {dep: importlib.metadata.version(dep) for dep in DEPENDENCIES}


def release_file(root, name):
    relative = PurePosixPath(name)
    if relative.is_absolute() or ".." in relative.parts or "\\" in name:
        raise ValueError(f"Invalid release file path: {name}")
    path = root.joinpath(*relative.parts)
    if not path.resolve().is_relative_to(root) or path.is_symlink() or not path.is_file():
        raise ValueError(f"Missing or unsafe release file: {path}")
    return path


def verify(root, fingerprint):
    root = root.resolve()
    manifest = release_file(root, "manifest.json")
    if not fingerprint or sha256(manifest) != fingerprint:
        raise ValueError(f"Model release manifest SHA-256 mismatch: {manifest}")
    content = json.loads(manifest.read_text(encoding="utf-8"))
    if content["format"] != 1 or set(content["runs"]) != {"enhanced", "baseline"}:
        raise ValueError("Unsupported model release format")
    if content["dependencies"] != versions():
        raise ValueError(f"Model dependency version mismatch: expected {content['dependencies']}, found {versions()}")
    required = {TOLERANCE, "golden.json", "requirements.lock.txt", *(name + ".py" for name in MODULES)}
    for key, run in content["runs"].items():
        if PurePosixPath(run).name != run or run in {".", ".."} or "\\" in run:
            raise ValueError(f"Invalid model run ID: {run}")
        report = "comparison.csv" if key == "enhanced" else "metrics.csv"
        prefix = f"{RUN_ROOT}/{run}"
        required.update(f"{prefix}/{name}" for name in ("bundle.joblib", report, *COMMON_REPORTS))
        required.add(f"{content['datasets'][key]}/dataset.csv")
    if required - content["files"].keys():
        raise ValueError(f"Incomplete model release: {sorted(required - content['files'].keys())}")
    for name, expected in content["files"].items():
        if sha256(release_file(root, name)) != expected:
            raise ValueError(f"Model release file SHA-256 mismatch: {name}")
    return content


def build(output, version, lock):
    import pandas as pd

    from app import ml

    output = output.resolve()
    if output.exists():
        raise FileExistsError(output)
    files = {}
    datasets = {}
    with tempfile.TemporaryDirectory(dir=output.parent) as tmp:
        root = Path(tmp) / "release"
        root.mkdir()

        def copy(src, name):
            dest = root / name
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(src, dest)
            files[name] = sha256(dest)

        for module in MODULES:
            copy(ml.SOURCE / (module + ".py"), module + ".py")
        copy(ml.SOURCE / TOLERANCE, TOLERANCE)
        copy(lock, "requirements.lock.txt")
        for key, run in ml.RUNS.items():
            prefix = f"{RUN_ROOT}/{run}"
            report = "comparison.csv" if key == "enhanced" else "metrics.csv"
            for name in ("bundle.joblib", report, *COMMON_REPORTS):
                copy(ml.run(key) / name, f"{prefix}/{name}")
            data = Path(ml.bundle(key)["dataset"])
            if not data.is_absolute():
                data = ml.SOURCE / data
            datasets[key] = f"datasets/{key}"
            copy(data / "dataset.csv", datasets[key] + "/dataset.csv")

        current = dict(current_A=210, voltage_V=27.2, ambient_C=80, speed_m_s=0.006, process_order=1)
        predictions = {key: ml.predict(key, current) for key in ml.RUNS}
        request = {
            "current": current,
            "steps": dict(current_A=5, voltage_V=0.8, ambient_C=10, speed_m_s=0.0005),
            "max_change": dict(current_A=5, voltage_V=0, ambient_C=0, speed_m_s=0),
            "orders": [1],
        }
        decision = Path(tmp) / "decision"
        ml.decision.optimize(ml.run("enhanced"), request, decision)
        sample = {
            "current": current, "predictions": predictions, "search": request,
            "recommendations": ml.records(decision / "recommendations.csv"),
            "candidates": pd.read_csv(decision / "all_candidates.csv", float_precision="round_trip").to_dict("records"),
        }
        (root / "golden.json").write_text(json.dumps(sample, indent=2), encoding="utf-8")
        files["golden.json"] = sha256(root / "golden.json")
        content = {
            "format": 1, "version": version, "runs": ml.RUNS, "datasets": datasets,
            "dependencies": versions(), "files": files,
        }
        manifest = root / "manifest.json"
        manifest.write_text(json.dumps(content, indent=2, sort_keys=True), encoding="utf-8")
        fingerprint = sha256(manifest)
        verify(root, fingerprint)
        root.rename(output)
    return fingerprint


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--version", required=True)
    parser.add_argument("--lock", type=Path, default=Path("requirements.lock.txt"))
    options = parser.parse_args()
    print("MODEL_MANIFEST_SHA256=" + build(options.output, options.version, options.lock))
