from __future__ import annotations

import math
from collections.abc import Sequence

from shapely.geometry import Polygon

from src.algorithms.coverage import (
    AabbCoverageStrategy,
    BoustrophedonCoverageStrategy,
    BpMopsCoverageStrategy,
    ConcaveHullCoverageStrategy,
    ConvexHullCoverageStrategy,
    DbscanBufferCoverageStrategy,
    FixedGridCoverageStrategy,
    MorphClosingCoverageStrategy,
    MrrCoverageStrategy,
    QuadtreeCoverageStrategy,
    StripBasedCoverageStrategy,
)
from src.algorithms.coverage.base import CoverageContext, CoverageStrategy
from src.core.config import AlgorithmConfig, normalize_coverage_method

_STRATEGIES: dict[str, CoverageStrategy] = {
    strategy.method_name: strategy
    for strategy in (
        MrrCoverageStrategy(),
        BoustrophedonCoverageStrategy(),
        BpMopsCoverageStrategy(),
        FixedGridCoverageStrategy(),
        QuadtreeCoverageStrategy(),
        ConvexHullCoverageStrategy(),
        ConcaveHullCoverageStrategy(),
        AabbCoverageStrategy(),
        MorphClosingCoverageStrategy(),
        DbscanBufferCoverageStrategy(),
        StripBasedCoverageStrategy(),
    )
}


def build_coverage_context(
    config: AlgorithmConfig,
    *,
    buffer_quad_segs: int | None = None,
    min_polygons_to_split: int = 2,
) -> CoverageContext:
    effective_buffer_quad_segs = buffer_quad_segs
    if effective_buffer_quad_segs is None:
        effective_buffer_quad_segs = max(1, math.ceil(config.max_polygon_sides / 4))
    return CoverageContext(
        config=config,
        buffer_quad_segs=effective_buffer_quad_segs,
        min_polygons_to_split=max(1, int(min_polygons_to_split)),
    )


def get_coverage_strategy(method_name: str) -> CoverageStrategy:
    normalized = normalize_coverage_method(method_name)
    try:
        return _STRATEGIES[normalized]
    except KeyError as exc:
        raise ValueError(f"Método de cobertura não suportado: {method_name}") from exc


def split_into_optimized_rectangles(
    polygons: Sequence[Polygon],
    config: AlgorithmConfig,
    *,
    buffer_quad_segs: int | None = None,
    min_polygons_to_split: int = 2,
) -> list[Polygon]:
    strategy = get_coverage_strategy(config.coverage_method)
    context = build_coverage_context(
        config,
        buffer_quad_segs=buffer_quad_segs,
        min_polygons_to_split=min_polygons_to_split,
    )
    return strategy.generate(polygons, context)
