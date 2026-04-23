from __future__ import annotations

import math
from collections.abc import Sequence

from shapely.geometry import Polygon, box

from src.algorithms.coverage.base import CoverageContext, CoverageStrategy
from src.geo.geometry import (
    dissolve_polygons,
    ensure_polygonal,
    make_valid_if_needed,
    to_polygon_list,
)


class FixedGridCoverageStrategy(CoverageStrategy):
    method_name = "fixed-grid"

    def generate(self, polygons: Sequence[Polygon], context: CoverageContext) -> list[Polygon]:
        union = dissolve_polygons(polygons, fix_invalid=context.config.fix_invalid_geometries)
        valid_union = ensure_polygonal(make_valid_if_needed(union, fix_invalid=context.config.fix_invalid_geometries))
        if valid_union.is_empty:
            return []

        cell_size_m = context.config.grid_cell_size_m
        threshold = context.config.grid_fill_threshold
        if cell_size_m <= 0:
            return to_polygon_list(valid_union)

        minx, miny, maxx, maxy = valid_union.bounds
        start_x = math.floor(minx / cell_size_m) * cell_size_m
        start_y = math.floor(miny / cell_size_m) * cell_size_m

        selected_cells: list[Polygon] = []
        x = start_x
        while x < maxx:
            y = start_y
            while y < maxy:
                cell = box(x, y, x + cell_size_m, y + cell_size_m)
                intersection = valid_union.intersection(cell)
                if not intersection.is_empty and intersection.area / cell.area >= threshold:
                    selected_cells.append(cell)
                y += cell_size_m
            x += cell_size_m

        if not selected_cells:
            return []

        dissolved = dissolve_polygons(selected_cells, fix_invalid=context.config.fix_invalid_geometries)
        return to_polygon_list(dissolved)
