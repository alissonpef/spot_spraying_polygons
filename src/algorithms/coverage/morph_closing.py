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


class MorphClosingCoverageStrategy(CoverageStrategy):
    method_name = "morph-closing"

    def generate(self, polygons: Sequence[Polygon], context: CoverageContext) -> list[Polygon]:
        union = dissolve_polygons(polygons, fix_invalid=context.config.fix_invalid_geometries)
        if union.is_empty:
            return []

        closing_radius_m = context.config.weed_buffer_m
        if closing_radius_m <= 0:
            closing_radius_m = 1.0

        closed = union.buffer(closing_radius_m, quad_segs=context.buffer_quad_segs)
        closed = closed.buffer(-closing_radius_m, quad_segs=context.buffer_quad_segs)
        fixed = make_valid_if_needed(closed, fix_invalid=context.config.fix_invalid_geometries)
        return to_polygon_list(ensure_polygonal(fixed))
