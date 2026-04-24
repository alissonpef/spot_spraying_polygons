from __future__ import annotations

import math
from collections.abc import Sequence

from shapely.geometry import MultiPoint, Polygon
from shapely.ops import triangulate, unary_union

from src.geo.geometry import (
    dissolve_polygons,
    ensure_polygonal,
    make_valid_if_needed,
    to_polygon_list,
)


def ring_signed_area(coords: Sequence[tuple[float, float]]) -> float:
    if len(coords) < 3:
        return 0.0

    area = 0.0
    for idx, (x1, y1) in enumerate(coords):
        x2, y2 = coords[(idx + 1) % len(coords)]
        area += x1 * y2 - x2 * y1
    return area / 2.0


def principal_axis_angle(polygons: Sequence[Polygon]) -> float:
    points: list[tuple[float, float]] = []
    for polygon in polygons:
        points.extend((x, y) for x, y in polygon.exterior.coords)
        for ring in polygon.interiors:
            points.extend((x, y) for x, y in ring.coords)

    if len(points) < 2:
        return 0.0

    mean_x = sum(x for x, _ in points) / len(points)
    mean_y = sum(y for _, y in points) / len(points)

    cov_xx = 0.0
    cov_xy = 0.0
    cov_yy = 0.0
    for x, y in points:
        dx = x - mean_x
        dy = y - mean_y
        cov_xx += dx * dx
        cov_xy += dx * dy
        cov_yy += dy * dy

    return math.degrees(0.5 * math.atan2(2.0 * cov_xy, cov_xx - cov_yy))


def deduplicate_positions(values: Sequence[float], tolerance: float) -> list[float]:
    if not values:
        return []

    ordered = sorted(values)
    effective_tolerance = tolerance if tolerance > 0 else 1e-6

    deduplicated = [ordered[0]]
    for value in ordered[1:]:
        if abs(value - deduplicated[-1]) <= effective_tolerance:
            continue
        deduplicated.append(value)
    return deduplicated


def collect_reflex_split_positions(polygon: Polygon, tolerance: float) -> list[float]:
    positions: list[float] = []
    rings = [polygon.exterior, *polygon.interiors]

    for ring in rings:
        coords = list(ring.coords)[:-1]
        if len(coords) < 3:
            continue

        ring_area = ring_signed_area(coords)
        if ring_area == 0:
            continue
        is_ccw = ring_area > 0

        for idx, (bx, by) in enumerate(coords):
            ax, ay = coords[idx - 1]
            cx, cy = coords[(idx + 1) % len(coords)]

            cross = (bx - ax) * (cy - by) - (by - ay) * (cx - bx)
            is_reflex = cross < 0 if is_ccw else cross > 0
            if not is_reflex:
                continue

            if tolerance > 0:
                positions.append(round(bx / tolerance) * tolerance)
            else:
                positions.append(bx)

    return positions


def collect_polygon_points(polygons: Sequence[Polygon]) -> list[tuple[float, float]]:
    points: list[tuple[float, float]] = []
    for polygon in polygons:
        points.extend((x, y) for x, y in polygon.exterior.coords[:-1])
        for ring in polygon.interiors:
            points.extend((x, y) for x, y in ring.coords[:-1])
    return points


def triangle_circumradius(triangle: Polygon) -> float:
    coords = list(triangle.exterior.coords)[:-1]
    if len(coords) != 3:
        return math.inf

    side_a = math.dist(coords[0], coords[1])
    side_b = math.dist(coords[1], coords[2])
    side_c = math.dist(coords[2], coords[0])
    area = triangle.area
    if area <= 0:
        return math.inf
    return (side_a * side_b * side_c) / (4.0 * area)


def alpha_shape_from_polygons(
    polygons: Sequence[Polygon],
    max_circumradius_m: float,
    *,
    fix_invalid: bool,
) -> Polygon:
    dissolved = dissolve_polygons(polygons, fix_invalid=fix_invalid)
    dissolved_polygons = to_polygon_list(dissolved)
    if not dissolved_polygons:
        return Polygon()

    points = collect_polygon_points(dissolved_polygons)
    if len(points) < 4:
        return ensure_polygonal(dissolved)

    multipoint = MultiPoint(points)
    if max_circumradius_m <= 0:
        hull = multipoint.convex_hull
        return ensure_polygonal(make_valid_if_needed(hull, fix_invalid=fix_invalid))

    kept_triangles: list[Polygon] = []
    for triangle in triangulate(multipoint):
        if not isinstance(triangle, Polygon) or triangle.is_empty:
            continue
        if triangle_circumradius(triangle) <= max_circumradius_m:
            kept_triangles.append(triangle)

    if not kept_triangles:
        hull = multipoint.convex_hull
        return ensure_polygonal(make_valid_if_needed(hull, fix_invalid=fix_invalid))

    alpha_geom = make_valid_if_needed(unary_union(kept_triangles), fix_invalid=fix_invalid)
    
    # Ensure the alpha shape always covers the original polygons
    alpha_geom = unary_union([alpha_geom, dissolved])
    alpha_geom = make_valid_if_needed(alpha_geom, fix_invalid=fix_invalid)
    
    return ensure_polygonal(alpha_geom)
