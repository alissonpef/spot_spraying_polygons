from __future__ import annotations

from collections.abc import Sequence

from shapely.affinity import rotate
from shapely.geometry import Polygon, box

from src.algorithms.coverage._common import principal_axis_angle
from src.algorithms.coverage.base import CoverageContext, CoverageStrategy
from src.geo.geometry import (
    dissolve_polygons,
    ensure_polygonal,
    make_valid_if_needed,
    to_polygon_list,
)


class StripBasedCoverageStrategy(CoverageStrategy):
    method_name = "strip-based"

    def generate(self, polygons: Sequence[Polygon], context: CoverageContext) -> list[Polygon]:

        valid = [polygon for polygon in polygons if not polygon.is_empty and polygon.area > 0]

        if not valid:
            return []

        union = dissolve_polygons(valid, fix_invalid=context.config.fix_invalid_geometries)

        if union.is_empty:
            return []

        strip_width_m = context.config.strip_width_m

        if strip_width_m <= 0:
            return to_polygon_list(union)

        origin = union.centroid

        sweep_angle = principal_axis_angle(valid)

        rotated = make_valid_if_needed(
            rotate(union, -sweep_angle, origin=origin),
            fix_invalid=context.config.fix_invalid_geometries,
        )

        rotated_parts = to_polygon_list(rotated)

        if not rotated_parts:
            return []

        minx = min(part.bounds[0] for part in rotated_parts)

        maxx = max(part.bounds[2] for part in rotated_parts)

        miny = min(part.bounds[1] for part in rotated_parts)

        maxy = max(part.bounds[3] for part in rotated_parts)

        selected_bands: list[Polygon] = []

        y = (miny // strip_width_m) * strip_width_m

        while y < maxy:
            band = box(minx, y, maxx, y + strip_width_m)

            clipped = make_valid_if_needed(
                rotated.intersection(band), fix_invalid=context.config.fix_invalid_geometries
            )

            if not clipped.is_empty and band.area > 0:
                occupancy = clipped.area / band.area

                if occupancy >= context.config.strip_fill_threshold:
                    selected_bands.append(band)

            y += strip_width_m

        if not selected_bands:
            fallback = make_valid_if_needed(
                rotate(rotated, sweep_angle, origin=origin),
                fix_invalid=context.config.fix_invalid_geometries,
            )

            return to_polygon_list(fallback)

        dissolved = dissolve_polygons(
            selected_bands, fix_invalid=context.config.fix_invalid_geometries
        )

        restored = rotate(dissolved, sweep_angle, origin=origin)

        fixed = make_valid_if_needed(restored, fix_invalid=context.config.fix_invalid_geometries)

        return to_polygon_list(ensure_polygonal(fixed))
