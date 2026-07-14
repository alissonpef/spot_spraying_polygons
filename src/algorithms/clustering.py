from __future__ import annotations

from collections.abc import Sequence

from shapely import STRtree
from shapely.geometry import Polygon
from shapely.geometry.base import BaseGeometry
from shapely.ops import unary_union

from src.geo.geometry import ensure_polygonal, make_valid_if_needed, to_polygon_list
from src.geo.spatial_index import query_tree_indices


def group_nearby_polygons(
    polygons: Sequence[BaseGeometry],
    max_distance: float,
    *,
    fix_invalid: bool,
    buffer_quad_segs: int,
) -> list[list[Polygon]]:

    flat: list[Polygon] = []

    for polygon in polygons:
        flat.extend(to_polygon_list(polygon))

    if not flat:
        return []

    if len(flat) == 1:
        return [flat]

    if max_distance <= 0:
        return [[polygon] for polygon in flat]

    half_distance = max_distance / 2.0

    expanded = [
        make_valid_if_needed(
            polygon.buffer(half_distance, quad_segs=buffer_quad_segs),
            fix_invalid=fix_invalid,
        )
        for polygon in flat
    ]

    merged = ensure_polygonal(make_valid_if_needed(unary_union(expanded), fix_invalid=fix_invalid))

    merged_regions = to_polygon_list(merged)

    if not merged_regions:
        return []

    region_tree = STRtree(merged_regions)

    groups: list[list[Polygon]] = [[] for _ in merged_regions]

    for index, expanded_polygon in enumerate(expanded):
        candidate_indices = query_tree_indices(region_tree, expanded_polygon)

        if not candidate_indices:
            continue

        if len(candidate_indices) == 1:
            groups[candidate_indices[0]].append(flat[index])

            continue

        best_region_index = max(
            candidate_indices,
            key=lambda region_index: (
                expanded_polygon.intersection(merged_regions[region_index]).area
            ),
        )

        groups[best_region_index].append(flat[index])

    return [group for group in groups if group]
