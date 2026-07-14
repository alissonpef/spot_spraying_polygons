from __future__ import annotations

from collections.abc import Sequence

from shapely.geometry import Polygon, box

from src.algorithms.coverage.base import CoverageContext, CoverageStrategy
from src.geo.geometry import (
    dissolve_polygons,
    ensure_polygonal,
    make_valid_if_needed,
    to_polygon_list,
)


class QuadtreeCoverageStrategy(CoverageStrategy):
    method_name = "quadtree"

    def generate(self, polygons: Sequence[Polygon], context: CoverageContext) -> list[Polygon]:

        union = dissolve_polygons(polygons, fix_invalid=context.config.fix_invalid_geometries)

        valid_union = ensure_polygonal(
            make_valid_if_needed(union, fix_invalid=context.config.fix_invalid_geometries)
        )

        if valid_union.is_empty:
            return []

        minx, miny, maxx, maxy = valid_union.bounds

        side = max(maxx - minx, maxy - miny)

        if side <= 0:
            return to_polygon_list(valid_union)

        root = box(minx, miny, minx + side, miny + side)

        selected_cells: list[Polygon] = []

        def recurse(cell: Polygon, depth: int) -> None:

            intersection = valid_union.intersection(cell)

            if intersection.is_empty:
                return

            bounds = cell.bounds

            cell_side = max(bounds[2] - bounds[0], bounds[3] - bounds[1])

            if (
                depth >= context.config.rectangle_max_depth
                or cell_side <= context.config.quadtree_min_cell_size_m
            ):
                selected_cells.append(cell)

                return

            occupancy = intersection.area / cell.area if cell.area > 0 else 0.0

            if occupancy >= context.config.quadtree_fill_threshold:
                selected_cells.append(cell)

                return

            midx = (bounds[0] + bounds[2]) / 2.0

            midy = (bounds[1] + bounds[3]) / 2.0

            recurse(box(bounds[0], bounds[1], midx, midy), depth + 1)

            recurse(box(midx, bounds[1], bounds[2], midy), depth + 1)

            recurse(box(bounds[0], midy, midx, bounds[3]), depth + 1)

            recurse(box(midx, midy, bounds[2], bounds[3]), depth + 1)

        recurse(root, 0)

        if not selected_cells:
            return []

        dissolved = dissolve_polygons(
            selected_cells, fix_invalid=context.config.fix_invalid_geometries
        )

        return to_polygon_list(dissolved)
