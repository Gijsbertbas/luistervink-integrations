from dataclasses import dataclass
from typing import Any


@dataclass
class Task:
    type: str
    spec: Any


@dataclass
class Detection:
    detected_at: int  # Unix epoch seconds, from detections.detected_at
    scientific_name: str
    confidence: float
    latitude: float | None
    longitude: float | None
