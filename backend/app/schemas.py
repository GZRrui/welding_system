from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class Inputs(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    current_A: float
    voltage_V: float
    ambient_C: float
    speed_m_s: float
    process_order: Literal[1, 2]


class Prediction(BaseModel):
    model_config = ConfigDict(extra="forbid")
    model: Literal["enhanced", "baseline"] = "enhanced"
    current: Inputs


class Trend(Prediction):
    axis: Literal["current_A", "voltage_V", "ambient_C", "speed_m_s"]
    points: int = Field(default=15, ge=2, le=31)


class Search(Prediction):
    steps: dict[str, float]
    max_change: dict[str, float]
    locked: dict[str, float] = Field(default_factory=dict)
    orders: list[Literal[1, 2]] = Field(default_factory=lambda: [1, 2], min_length=1, max_length=2)


class Review(BaseModel):
    status: Literal["pending", "reviewed", "rejected"]
    notes: str = Field(max_length=4000)
