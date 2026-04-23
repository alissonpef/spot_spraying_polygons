from __future__ import annotations

from collections.abc import Sequence

from shapely.geometry import Polygon


def compute_split_axes(mrr: Polygon) -> list[tuple[float, float]]:
    coords = list(mrr.exterior.coords)
    edge1 = (coords[1][0] - coords[0][0], coords[1][1] - coords[0][1])
    edge2 = (coords[2][0] - coords[1][0], coords[2][1] - coords[1][1])

    len1 = (edge1[0] ** 2 + edge1[1] ** 2) ** 0.5
    len2 = (edge2[0] ** 2 + edge2[1] ** 2) ** 0.5

    axes: list[tuple[float, float]] = []
    if len1 > 0:
        axes.append((edge1[0] / len1, edge1[1] / len1))
    if len2 > 0:
        axes.append((edge2[0] / len2, edge2[1] / len2))
    return axes


def project_polygons_on_axis(
    polygons: Sequence[Polygon],
    axis: tuple[float, float],
) -> list[tuple[float, int]]:
    projected: list[tuple[float, int]] = []
    for index, polygon in enumerate(polygons):
        centroid = polygon.centroid
        projected.append((centroid.x * axis[0] + centroid.y * axis[1], index))
    projected.sort()
    return projected


def partition_by_gap(
    polygons: Sequence[Polygon],
    projected: Sequence[tuple[float, int]],
    merge_distance_m: float | None,
) -> tuple[list[Polygon], list[Polygon]] | None:
    if len(projected) < 2:
        return None

    proj_range = projected[-1][0] - projected[0][0]
    if proj_range <= 0:
        return None

    max_gap = -1.0
    best_split = -1
    for idx in range(len(projected) - 1):
        gap = projected[idx + 1][0] - projected[idx][0]
        if gap > max_gap:
            max_gap = gap
            best_split = idx

    if best_split < 0 or max_gap / proj_range < 0.1:
        return None
    if merge_distance_m is not None and max_gap < merge_distance_m:
        return None

    group_a = [polygons[projected[idx][1]] for idx in range(best_split + 1)]
    group_b = [polygons[projected[idx][1]] for idx in range(best_split + 1, len(projected))]
    if not group_a or not group_b:
        return None
    return group_a, group_b
