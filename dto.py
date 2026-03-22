from dataclasses import dataclass
from typing import Any


@dataclass
class Task:
    type: str
    spec: Any


@dataclass
class Detection:
    date: str
    time: str
    begin_time: str
    end_time: str
    scientific_name: str
    common_name: str
    confidence: float
    latitude: float
    longitude: float
