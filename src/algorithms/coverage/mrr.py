from __future__ import annotations

import math
from collections.abc import Sequence

from shapely.geometry import Polygon
from shapely.ops import unary_union

from src.algorithms.coverage.base import CoverageContext, CoverageStrategy
from src.algorithms.decomposition import (
    compute_split_axes,
    partition_by_gap,
    project_polygons_on_axis,
)


class MrrCoverageStrategy(CoverageStrategy):
    method_name = "mrr"

    def generate(self, polygons: Sequence[Polygon], context: CoverageContext) -> list[Polygon]:

        valid = [polygon for polygon in polygons if not polygon.is_empty and polygon.area > 0]

        if not valid:
            return []

        return self._split_recursive(
            valid, context, remaining_depth=context.config.rectangle_max_depth
        )

    def _split_recursive(
        self,
        polygons: Sequence[Polygon],
        context: CoverageContext,
        *,
        remaining_depth: int,
    ) -> list[Polygon]:

        valid = [polygon for polygon in polygons if not polygon.is_empty and polygon.area > 0]

        if not valid:
            return []

        union = unary_union(valid)

        if union.is_empty:
            return []

        mrr_candidate = union.minimum_rotated_rectangle

        if not isinstance(mrr_candidate, Polygon) or mrr_candidate.is_empty:
            return []

        weed_area = union.area

        rect_area = mrr_candidate.area

        if rect_area <= 0:
            return [mrr_candidate]

        fill_ratio = min(weed_area / rect_area, 1.0)

        fill_ratio_safe = max(fill_ratio, 1e-9)

        fill_depth = max(1, math.ceil(math.log2(max(1.0 / fill_ratio_safe, 2.0)))) - 1

        effective_depth = min(remaining_depth, max(1, fill_depth))

        if (
            fill_ratio >= context.config.rectangle_min_fill_ratio
            or len(valid) < context.min_polygons_to_split
            or effective_depth <= 0
        ):
            return [mrr_candidate]

        best_result: list[Polygon] = [mrr_candidate]

        best_area = rect_area

        for axis in compute_split_axes(mrr_candidate):
            projected = project_polygons_on_axis(valid, axis)

            groups = partition_by_gap(valid, projected, context.config.merge_distance_m)

            if groups is None:
                continue

            group_a, group_b = groups

            candidate_a = self._split_recursive(
                group_a,
                context,
                remaining_depth=effective_depth - 1,
            )

            candidate_b = self._split_recursive(
                group_b,
                context,
                remaining_depth=effective_depth - 1,
            )

            candidate = candidate_a + candidate_b

            total_area = sum(polygon.area for polygon in candidate)

            if total_area < best_area * 0.7:
                best_area = total_area

                best_result = candidate

        return best_result
