from __future__ import annotations

from collections.abc import Sequence

from shapely.geometry import Polygon

from src.algorithms.coverage.base import CoverageContext, CoverageStrategy
from src.geo.geometry import (
    dissolve_polygons,
    ensure_polygonal,
    make_valid_if_needed,
    to_polygon_list,
)


class ConvexHullCoverageStrategy(CoverageStrategy):
    method_name = "convex-hull"

    def generate(self, polygons: Sequence[Polygon], context: CoverageContext) -> list[Polygon]:
        union = dissolve_polygons(polygons, fix_invalid=context.config.fix_invalid_geometries)
        if union.is_empty:
            return []

        hull = union.convex_hull
        fixed = make_valid_if_needed(hull, fix_invalid=context.config.fix_invalid_geometries)
        return to_polygon_list(ensure_polygonal(fixed))
