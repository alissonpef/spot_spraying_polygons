from __future__ import annotations

from dataclasses import dataclass

from src.core import SUPPORTED_COVERAGE_METHODS, normalize_coverage_method

PREFERRED_METHOD_ORDER = (
    "mrr",
    "bcd",
    "fixed-grid",
    "quadtree",
    "strip-based",
    "convex-hull",
    "concave-hull",
    "aabb",
    "morph-closing",
)

METHOD_PARAMETER_KEYS: dict[str, tuple[str, ...]] = {
    "fixed-grid": ("grid_cell_size_m", "grid_fill_threshold"),
    "quadtree": ("quadtree_min_cell_size_m", "quadtree_fill_threshold"),
    "concave-hull": ("alpha_shape_radius_m",),
    "strip-based": ("strip_width_m", "strip_fill_threshold"),
}

METHOD_METADATA: dict[str, tuple[str, str]] = {
    "mrr": (
        "MRR",
        "Generates minimum rotated rectangles and splits only when there is a clear operational benefit.",
    ),
    "bcd": (
        "Boustrophedon",
        "Decomposes patches into more navigable cells for systematic coverage.",
    ),
    "fixed-grid": (
        "Fixed Grid",
        "Approximates the area with regular cells, prioritizing simplicity and repeatability.",
    ),
    "quadtree": (
        "Quadtree",
        "Refines the grid only where needed, balancing local detail and area reduction.",
    ),
    "strip-based": (
        "Strips",
        "Aligns bands to the patch's main axis to favor long drone passes.",
    ),
    "convex-hull": (
        "Convex Hull",
        "Creates the convex hull of the patch, covering quickly but with a tendency for overcoverage.",
    ),
    "concave-hull": (
        "Concave Hull",
        "Better follows the patch's voids and cutouts with an adaptive hull.",
    ),
    "aabb": (
        "AABB",
        "Uses the axis-aligned bounding box; it is the simplest and most conservative method.",
    ),
    "morph-closing": (
        "Morphological Closing",
        "Smoothes the patch with morphological operations to reduce small cutouts and noise.",
    ),
}


@dataclass(frozen=True, slots=True)
class AlgorithmOption:
    key: str
    label: str
    description: str


def list_algorithm_options() -> list[AlgorithmOption]:
    supported_methods = {normalize_coverage_method(method) for method in SUPPORTED_COVERAGE_METHODS}
    ordered_methods = [method for method in PREFERRED_METHOD_ORDER if method in supported_methods]
    ordered_methods.extend(sorted(supported_methods.difference(ordered_methods)))
    return [build_algorithm_option(method) for method in ordered_methods]


def build_algorithm_option(method: str) -> AlgorithmOption:
    normalized_method = normalize_coverage_method(method)
    label, description = METHOD_METADATA.get(
        normalized_method,
        (normalized_method.replace("-", " ").title(), "Method supported by the engine."),
    )
    return AlgorithmOption(
        key=normalized_method,
        label=label,
        description=description,
    )


def get_algorithm_parameter_keys(method: str) -> tuple[str, ...]:
    return METHOD_PARAMETER_KEYS.get(normalize_coverage_method(method), ())
