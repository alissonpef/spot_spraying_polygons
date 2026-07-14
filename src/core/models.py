from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from shapely.geometry import MultiPolygon, Polygon

PolygonalGeometry = Polygon | MultiPolygon


@dataclass(slots=True)
class Field:
    field_id: int

    name: str

    geometry: Polygon

    properties: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class WeedPatch:
    patch_id: int

    geometry: Polygon

    properties: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class Obstacle:
    obstacle_id: int

    geometry: Polygon

    properties: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class SprayZone:
    field_id: int

    geometry: PolygonalGeometry

    area_m2: float

    coverage_method: str

    properties: dict[str, Any] = field(default_factory=dict)
