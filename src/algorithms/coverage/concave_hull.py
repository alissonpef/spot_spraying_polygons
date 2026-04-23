from __future__ import annotations

from collections.abc import Sequence

from shapely.geometry import Polygon

from src.algorithms.coverage._common import alpha_shape_from_polygons
from src.algorithms.coverage.base import CoverageContext, CoverageStrategy
from src.geo.geometry import to_polygon_list


class ConcaveHullCoverageStrategy(CoverageStrategy):
    method_name = "concave-hull"

    def generate(self, polygons: Sequence[Polygon], context: CoverageContext) -> list[Polygon]:
        return to_polygon_list(
            alpha_shape_from_polygons(
                polygons,
                context.config.alpha_shape_radius_m,
                fix_invalid=context.config.fix_invalid_geometries,
            )
        )
