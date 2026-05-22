from __future__ import annotations

import logging
import math
from collections.abc import Mapping, Sequence

from shapely import BufferJoinStyle
from shapely.geometry import MultiPolygon, Polygon
from shapely.geometry.base import BaseGeometry
from shapely.ops import unary_union

from src.algorithms.clustering import group_nearby_polygons
from src.algorithms.factory import split_into_optimized_rectangles
from src.core.config import AlgorithmConfig
from src.geo.geometry import (
    PolygonalGeometry,
    clip_polygons_to_boundary,
    dissolve_polygons,
    ensure_polygonal,
    make_valid_if_needed,
    to_polygon_list,
)

logger = logging.getLogger(__name__)

TRIM_SLIVER_MAX_AREA_M2 = 5.0
TRIM_SLIVER_MIN_ANGLE_DEG = 30.0
SMALL_PRIMITIVE_METHODS = {
    "bcd",
    "fixed-grid",
    "quadtree",
    "strip-based",
    "morph-closing",
}


def _coerce_config(config: AlgorithmConfig | Mapping[str, object]) -> AlgorithmConfig:
    if isinstance(config, AlgorithmConfig):
        return config
    return AlgorithmConfig.from_mapping(config)


def _buffer_quad_segs_from_config(config: AlgorithmConfig) -> int:
    return max(1, math.ceil(config.max_polygon_sides / 4))


def generate_spray_geometry_for_field(
    weeds_metric: Sequence[Polygon],
    obstacles_metric: Sequence[Polygon],
    field_poly: Polygon,
    config: AlgorithmConfig | Mapping[str, object],
) -> PolygonalGeometry:
    algorithm_config = _coerce_config(config)
    local_weeds = clip_polygons_to_boundary(
        weeds_metric,
        field_poly,
        fix_invalid=algorithm_config.fix_invalid_geometries,
    )
    if not local_weeds:
        return Polygon()

    coverage_method = algorithm_config.normalized_coverage_method
    buffer_quad_segs = _buffer_quad_segs_from_config(algorithm_config)

    logger.info(
        "  Field: %d internal weeds, buffer=%.1fm, merge=%.1fm, method=%s",
        len(local_weeds),
        algorithm_config.weed_buffer_m,
        algorithm_config.merge_distance_m,
        coverage_method,
    )

    buffered_weeds: list[Polygon] = []
    for weed in local_weeds:
        buffered = weed.buffer(
            algorithm_config.weed_buffer_m,
            quad_segs=buffer_quad_segs,
        )
        fixed_buffer = make_valid_if_needed(
            buffered,
            fix_invalid=algorithm_config.fix_invalid_geometries,
        )
        buffered_weeds.extend(to_polygon_list(fixed_buffer))

    return _build_safe_geometry(
        buffered_weeds,
        obstacles_metric,
        field_poly,
        algorithm_config,
        buffer_quad_segs=buffer_quad_segs,
    )


def generate_spray_rectangles_for_field(
    weeds_metric: Sequence[Polygon],
    obstacles_metric: Sequence[Polygon],
    field_poly: Polygon,
    config: AlgorithmConfig | Mapping[str, object],
) -> PolygonalGeometry:
    return generate_spray_geometry_for_field(
        weeds_metric=weeds_metric,
        obstacles_metric=obstacles_metric,
        field_poly=field_poly,
        config=config,
    )


def _build_safe_geometry(
    buffered_weeds: Sequence[Polygon],
    obstacles_metric: Sequence[Polygon],
    field_poly: Polygon,
    config: AlgorithmConfig,
    *,
    buffer_quad_segs: int,
) -> PolygonalGeometry:
    grouped_weeds = group_nearby_polygons(
        buffered_weeds,
        config.merge_distance_m,
        fix_invalid=config.fix_invalid_geometries,
        buffer_quad_segs=buffer_quad_segs,
    )
    coverage_method = config.normalized_coverage_method
    logger.info("  %d group(s) formed (method=%s)", len(grouped_weeds), coverage_method)

    relevant_obstacles = [
        obstacle for obstacle in obstacles_metric if field_poly.intersects(obstacle)
    ]
    obstacle_union = _build_obstacle_union(
        relevant_obstacles,
        buffer_m=config.obstacle_safety_buffer_m,
        fix_invalid=config.fix_invalid_geometries,
        buffer_quad_segs=buffer_quad_segs,
    )

    raw_geometries: list[Polygon] = []
    primitive_min_area_m2 = (
        0.0 if coverage_method in SMALL_PRIMITIVE_METHODS else config.min_polygon_area_m2
    )

    for weed_group in grouped_weeds:
        primitives = split_into_optimized_rectangles(
            weed_group,
            config,
            buffer_quad_segs=buffer_quad_segs,
        )

        for primitive in primitives:
            candidate = ensure_polygonal(
                make_valid_if_needed(primitive, fix_invalid=config.fix_invalid_geometries)
            )
            if candidate.is_empty:
                continue

            if config.negative_buffer_m > 0:
                candidate = ensure_polygonal(
                    make_valid_if_needed(
                        candidate.buffer(-config.negative_buffer_m, quad_segs=buffer_quad_segs),
                        fix_invalid=config.fix_invalid_geometries,
                    )
                )
                if candidate.is_empty:
                    continue

            if obstacle_union is not None:
                candidate = _subtract_obstacle_union(
                    candidate,
                    obstacle_union,
                    fix_invalid=config.fix_invalid_geometries,
                )
                if candidate.is_empty:
                    continue

            clipped = ensure_polygonal(
                make_valid_if_needed(
                    candidate.intersection(field_poly),
                    fix_invalid=config.fix_invalid_geometries,
                )
            )

            for polygon in to_polygon_list(clipped):
                if polygon.is_empty or polygon.area <= 0.01:
                    continue
                if primitive_min_area_m2 > 0 and polygon.area < primitive_min_area_m2:
                    continue
                raw_geometries.append(polygon)

    final_min_area_m2 = (
        0.0 if coverage_method in SMALL_PRIMITIVE_METHODS else config.min_polygon_area_m2
    )
    return _resolve_overlapping_geometries(
        raw_geometries,
        fix_invalid=config.fix_invalid_geometries,
        min_polygon_area_m2=final_min_area_m2,
    )


def _build_obstacle_union(
    obstacles: Sequence[Polygon],
    *,
    buffer_m: float,
    fix_invalid: bool,
    buffer_quad_segs: int,
) -> PolygonalGeometry | None:
    if not obstacles:
        return None

    buffered_polygons: list[Polygon] = []
    for obstacle in obstacles:
        buffered = obstacle.buffer(
            buffer_m,
            quad_segs=buffer_quad_segs,
            join_style=BufferJoinStyle.mitre,
            mitre_limit=2.0,
        )
        fixed_buffer = make_valid_if_needed(buffered, fix_invalid=fix_invalid)
        buffered_polygons.extend(to_polygon_list(fixed_buffer))

    if not buffered_polygons:
        return None

    obstacle_union = dissolve_polygons(buffered_polygons, fix_invalid=fix_invalid)
    return None if obstacle_union.is_empty else obstacle_union


def _subtract_obstacle_union(
    polygon: PolygonalGeometry,
    obstacle_union: PolygonalGeometry,
    *,
    fix_invalid: bool,
) -> PolygonalGeometry:
    result = polygon.difference(obstacle_union)
    return ensure_polygonal(make_valid_if_needed(result, fix_invalid=fix_invalid))


def _resolve_overlapping_geometries(
    raw_geometries: Sequence[Polygon],
    *,
    fix_invalid: bool,
    min_polygon_area_m2: float = 0.0,
) -> PolygonalGeometry:
    if not raw_geometries:
        return Polygon()

    ordered = sorted(raw_geometries, key=lambda polygon: polygon.area, reverse=True)
    final_polygons: list[Polygon] = []
    covered = Polygon()
    covered_batch: list[Polygon] = []

    def flush_covered_batch() -> None:
        nonlocal covered, covered_batch
        if not covered_batch:
            return
        covered = ensure_polygonal(
            make_valid_if_needed(
                unary_union([covered, *covered_batch]),
                fix_invalid=fix_invalid,
            )
        )
        covered_batch = []

    for polygon in ordered:
        if not covered_batch and covered.is_empty:
            trimmed = polygon
        else:
            trimmed_geometry: BaseGeometry = (
                polygon.difference(covered) if not covered.is_empty else polygon
            )
            for pending in covered_batch:
                if trimmed_geometry.is_empty:
                    break
                if pending.intersects(trimmed_geometry):
                    trimmed_geometry = trimmed_geometry.difference(pending)
            trimmed = ensure_polygonal(
                make_valid_if_needed(trimmed_geometry, fix_invalid=fix_invalid)
            )

        for piece in to_polygon_list(trimmed):
            if piece.is_empty or piece.area <= 0.01:
                continue
            if min_polygon_area_m2 > 0 and piece.area < min_polygon_area_m2:
                continue
            if _is_trim_sliver_artifact(piece):
                continue
            final_polygons.append(piece)

        covered_batch.append(polygon)
        if len(covered_batch) >= 32:
            flush_covered_batch()

    flush_covered_batch()

    if not final_polygons:
        return Polygon()
    if len(final_polygons) == 1:
        return final_polygons[0]
    return MultiPolygon(final_polygons)


def _is_trim_sliver_artifact(polygon: Polygon) -> bool:
    if polygon.area > TRIM_SLIVER_MAX_AREA_M2:
        return False
    return _polygon_min_interior_angle_deg(polygon) < TRIM_SLIVER_MIN_ANGLE_DEG


def _polygon_min_interior_angle_deg(polygon: Polygon) -> float:
    coords = list(polygon.exterior.coords)
    if len(coords) < 4:
        return 180.0

    ring = coords[:-1]
    min_angle = 180.0

    for index, (bx, by) in enumerate(ring):
        ax, ay = ring[index - 1]
        cx, cy = ring[(index + 1) % len(ring)]

        vector_a = (ax - bx, ay - by)
        vector_c = (cx - bx, cy - by)
        norm_a = math.hypot(*vector_a)
        norm_c = math.hypot(*vector_c)
        if norm_a == 0 or norm_c == 0:
            continue

        cosine = (vector_a[0] * vector_c[0] + vector_a[1] * vector_c[1]) / (norm_a * norm_c)
        cosine = max(-1.0, min(1.0, cosine))
        min_angle = min(min_angle, math.degrees(math.acos(cosine)))

    return min_angle
