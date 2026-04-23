from __future__ import annotations

import math
from collections.abc import Sequence

from shapely.geometry import Point, Polygon
from shapely.ops import unary_union

from src.algorithms.coverage.base import CoverageContext, CoverageStrategy
from src.geo.geometry import make_valid_if_needed, to_polygon_list


class BpMopsCoverageStrategy(CoverageStrategy):
    method_name = "bp-mops"

    def generate(self, polygons: Sequence[Polygon], context: CoverageContext) -> list[Polygon]:
        valid = [polygon for polygon in polygons if not polygon.is_empty and polygon.area > 0]
        if not valid:
            return []

        union = unary_union(valid)
        if union.is_empty:
            return []

        spray_radius_m = context.config.weed_buffer_m
        if spray_radius_m <= 0:
            return to_polygon_list(union)

        minx, miny, maxx, maxy = union.bounds
        dx = math.sqrt(3.0) * spray_radius_m
        dy = 1.5 * spray_radius_m

        circles: list[Polygon] = []
        row = 0
        y = miny - dy
        y_limit = maxy + dy
        x_limit = maxx + dx
        x_start = minx - dx

        while y <= y_limit:
            offset = 0.0 if row % 2 == 0 else dx / 2.0
            x = x_start + offset
            while x <= x_limit:
                circle = Point(x, y).buffer(spray_radius_m, quad_segs=context.buffer_quad_segs)
                if circle.intersects(union):
                    fixed_circle = make_valid_if_needed(
                        circle,
                        fix_invalid=context.config.fix_invalid_geometries,
                    )
                    circles.extend(to_polygon_list(fixed_circle))
                x += dx
            row += 1
            y += dy

        return circles if circles else to_polygon_list(union)
