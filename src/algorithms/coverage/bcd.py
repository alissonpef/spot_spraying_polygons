from __future__ import annotations

from collections.abc import Sequence

from shapely.affinity import rotate
from shapely.geometry import Polygon, box
from shapely.ops import unary_union

from src.algorithms.coverage._common import (
    collect_reflex_split_positions,
    deduplicate_positions,
    principal_axis_angle,
)
from src.algorithms.coverage.base import CoverageContext, CoverageStrategy
from src.geo.geometry import make_valid_if_needed, to_polygon_list


class BoustrophedonCoverageStrategy(CoverageStrategy):
    method_name = "bcd"

    def generate(self, polygons: Sequence[Polygon], context: CoverageContext) -> list[Polygon]:
        fix_invalid = context.config.fix_invalid_geometries
        merge_distance_m = context.config.merge_distance_m

        valid = [polygon for polygon in polygons if not polygon.is_empty and polygon.area > 0]
        if not valid:
            return []

        union = unary_union(valid)
        if union.is_empty:
            return []

        origin = union.centroid
        sweep_angle = principal_axis_angle(valid)
        rotated = make_valid_if_needed(
            rotate(union, -sweep_angle, origin=origin),
            fix_invalid=fix_invalid,
        )
        rotated_parts = to_polygon_list(rotated)
        if not rotated_parts:
            return []

        minx = min(part.bounds[0] for part in rotated_parts)
        miny = min(part.bounds[1] for part in rotated_parts)
        maxx = max(part.bounds[2] for part in rotated_parts)
        maxy = max(part.bounds[3] for part in rotated_parts)

        tolerance = max((merge_distance_m or 0.0) * 0.25, 0.5)
        split_positions: list[float] = []
        for part in rotated_parts:
            split_positions.extend(collect_reflex_split_positions(part, tolerance))

        split_positions = deduplicate_positions(
            [position for position in split_positions if minx < position < maxx],
            tolerance,
        )

        if not split_positions:
            restored = make_valid_if_needed(
                rotate(rotated, sweep_angle, origin=origin),
                fix_invalid=fix_invalid,
            )
            return self._clean_cells(to_polygon_list(restored), fix_invalid=fix_invalid)

        x_positions = [minx, *split_positions, maxx]
        band_padding_x = max((maxx - minx) * 0.01, tolerance)
        band_padding_y = max((maxy - miny) * 0.05, tolerance)

        cells: list[Polygon] = []
        for left, right in zip(x_positions, x_positions[1:]):
            if right - left <= tolerance:
                continue

            strip = box(
                left - band_padding_x,
                miny - band_padding_y,
                right + band_padding_x,
                maxy + band_padding_y,
            )
            clipped = make_valid_if_needed(rotated.intersection(strip), fix_invalid=fix_invalid)
            for piece in to_polygon_list(clipped):
                if piece.is_empty or piece.area <= 0.01:
                    continue

                restored = make_valid_if_needed(
                    rotate(piece, sweep_angle, origin=origin),
                    fix_invalid=fix_invalid,
                )
                cells.extend(to_polygon_list(restored))

        if cells:
            return self._clean_cells(cells, fix_invalid=fix_invalid)

        restored = make_valid_if_needed(
            rotate(rotated, sweep_angle, origin=origin),
            fix_invalid=fix_invalid,
        )
        return self._clean_cells(to_polygon_list(restored), fix_invalid=fix_invalid)

    @staticmethod
    def _clean_cells(cells: Sequence[Polygon], *, fix_invalid: bool) -> list[Polygon]:
        cleaned: list[Polygon] = []
        for candidate in cells:
            candidate_fixed = make_valid_if_needed(candidate.buffer(0), fix_invalid=fix_invalid)
            for part in to_polygon_list(candidate_fixed):
                if part.is_empty or part.area <= 0.01:
                    continue
                cleaned.append(part)
        return cleaned
