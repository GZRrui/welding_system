"""Generate synthetic model files from the pinned algorithm checkout for CI."""

import os
from pathlib import Path

import joblib
import pandas as pd
from sklearn.dummy import DummyRegressor

from app import ml

root = Path(os.environ["ALGORITHM_ROOT"])
data = root / "data/ci"
data.mkdir(parents=True, exist_ok=True)
bounds = dict(current_A=(180, 240), voltage_V=(24, 32), ambient_C=(40, 140), speed_m_s=(0.004, 0.008))
frame = pd.DataFrame([
    dict(current_A=210, voltage_V=27.2, ambient_C=80, speed_m_s=0.006, process_order=1, batch_id="ci"),
])
frame.to_csv(data / "dataset.csv", index=False)
features = list(bounds)
model = DummyRegressor(strategy="constant", constant=0.05).fit(frame[features], [0.05])
bundle = {
    "dataset": str(data),
    "bounds": bounds,
    "features": features,
    "models": {(order, target): {"model": model, "radius": 0.00001}
               for order in (1, 2) for target in ml.w.TARGETS},
}
for key in ml.RUNS:
    run = ml.run(key)
    (run / "validation").mkdir(parents=True, exist_ok=True)
    joblib.dump(bundle, run / "bundle.joblib")
    for name in (
        "comparison.csv" if key == "enhanced" else "metrics.csv",
        "validation/regional_errors.csv", "validation/level_holdout_metrics.csv",
    ):
        (run / name).write_text("target,mae\nci,0\n", encoding="utf-8")
