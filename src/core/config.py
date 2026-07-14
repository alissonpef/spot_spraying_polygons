from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import asdict, dataclass, fields, replace
from pathlib import Path
from typing import Any

SUPPORTED_COVERAGE_METHODS = {
    "mrr",
    "bcd",
    "fixed-grid",
    "quadtree",
    "convex-hull",
    "concave-hull",
    "aabb",
    "morph-closing",
    "strip-based",
}


COVERAGE_METHOD_ALIASES: dict[str, str] = {
    "minimum-rotated-rectangle": "mrr",
    "minimum-rotated-rectangles": "mrr",
    "rotated-rectangle": "mrr",
    "boustrophedon": "bcd",
    "boustrophedon-cellular": "bcd",
    "grid": "fixed-grid",
    "grid-fixed": "fixed-grid",
    "chessboard": "fixed-grid",
    "chessboard-segmentation": "fixed-grid",
    "quad-tree": "quadtree",
    "convex": "convex-hull",
    "concave": "concave-hull",
    "alpha-shape": "concave-hull",
    "alphashape": "concave-hull",
    "bbox": "aabb",
    "axis-aligned-bounding-box": "aabb",
    "morphological-closing": "morph-closing",
    "closing": "morph-closing",
    "swath-aligned": "strip-based",
    "strip-based-merging": "strip-based",
    "1d-striping": "strip-based",
}


def normalize_coverage_method(raw_value: object | None) -> str:

    if raw_value is None:
        return "mrr"

    normalized = str(raw_value).strip().lower().replace("_", "-")

    normalized = COVERAGE_METHOD_ALIASES.get(normalized, normalized)

    if normalized not in SUPPORTED_COVERAGE_METHODS:
        raise ValueError(
            "Invalid coverage method: "
            f"{raw_value!r}. Use mrr, bcd, fixed-grid, quadtree, "
            "convex-hull, concave-hull, aabb, morph-closing or strip-based."
        )

    return normalized


@dataclass(slots=True, frozen=True)
class AlgorithmConfig:
    weed_buffer_m: float = 1.0

    merge_distance_m: float = 5.0

    obstacle_safety_buffer_m: float = 3.0

    negative_buffer_m: float = 0.5

    min_polygon_area_m2: float = 1000.0

    fix_invalid_geometries: bool = True

    rectangle_min_fill_ratio: float = 0.45

    rectangle_max_depth: int = 6

    max_polygon_sides: int = 16

    coverage_method: str = "mrr"

    grid_cell_size_m: float = 2.0

    grid_fill_threshold: float = 0.35

    quadtree_min_cell_size_m: float = 1.0

    quadtree_fill_threshold: float = 0.35

    alpha_shape_radius_m: float = 20.0

    strip_width_m: float = 3.0

    strip_fill_threshold: float = 0.30

    working_crs: str | None = None

    def to_dict(self) -> dict[str, Any]:

        return asdict(self)

    @property
    def normalized_coverage_method(self) -> str:

        return normalize_coverage_method(self.coverage_method)

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any] | None) -> AlgorithmConfig:

        if raw is None:
            config = cls()

            config.validate()

            return config

        values: dict[str, Any] = {}

        for field_info in fields(cls):
            field_name = field_info.name

            if field_name not in raw:
                continue

            values[field_name] = raw[field_name]

        if "coverage_method" in values:
            values["coverage_method"] = normalize_coverage_method(values["coverage_method"])

        config = cls(**values)

        config.validate()

        return config

    def with_overrides(
        self, overrides: Mapping[str, Any] | None = None, **kwargs: Any
    ) -> AlgorithmConfig:

        merged: dict[str, Any] = {}

        if overrides:
            merged.update(overrides)

        merged.update(kwargs)

        if not merged:
            return self

        normalized_values: dict[str, Any] = {}

        for key, value in merged.items():
            if not hasattr(self, key):
                continue

            normalized_values[key] = value

        if "coverage_method" in normalized_values:
            normalized_values["coverage_method"] = normalize_coverage_method(
                normalized_values["coverage_method"]
            )

        updated = replace(self, **normalized_values)

        updated.validate()

        return updated

    def validate(self) -> None:

        numeric_ranges: dict[str, tuple[float, float | None]] = {
            "weed_buffer_m": (0.0, None),
            "merge_distance_m": (0.0, None),
            "obstacle_safety_buffer_m": (0.0, None),
            "negative_buffer_m": (0.0, None),
            "min_polygon_area_m2": (0.0, None),
            "rectangle_min_fill_ratio": (0.0, 1.0),
            "grid_cell_size_m": (0.0, None),
            "grid_fill_threshold": (0.0, 1.0),
            "quadtree_min_cell_size_m": (0.0, None),
            "quadtree_fill_threshold": (0.0, 1.0),
            "alpha_shape_radius_m": (0.0, None),
            "strip_width_m": (0.0, None),
            "strip_fill_threshold": (0.0, 1.0),
        }

        for key, (min_value, max_value) in numeric_ranges.items():
            value = float(getattr(self, key))

            if value < min_value:
                raise ValueError(f"Invalid parameter ({key}): value must be >= {min_value}")

            if max_value is not None and value > max_value:
                raise ValueError(f"Invalid parameter ({key}): value must be <= {max_value}")

        if int(self.rectangle_max_depth) < 1:
            raise ValueError("Invalid parameter (rectangle_max_depth): value must be >= 1")

        if int(self.max_polygon_sides) < 4:
            raise ValueError("Invalid parameter (max_polygon_sides): value must be >= 4")

        normalize_coverage_method(self.coverage_method)


BASE_DIR = Path(__file__).resolve().parents[2]


class Config:
    BASE_DIR = BASE_DIR

    DATA_DIR = BASE_DIR / "data"

    INPUT_DIR = DATA_DIR / "input"

    OUTPUT_DIR = DATA_DIR / "output"

    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")

    @classmethod
    def ensure_directories(cls) -> None:

        cls.INPUT_DIR.mkdir(parents=True, exist_ok=True)

        cls.OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
