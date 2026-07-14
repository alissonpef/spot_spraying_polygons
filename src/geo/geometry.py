from __future__ import annotations

import logging
from collections.abc import Callable, Sequence

from shapely.errors import GEOSException, TopologicalError
from shapely.geometry import GeometryCollection, MultiPolygon, Polygon
from shapely.geometry.base import BaseGeometry
from shapely.ops import unary_union
from shapely.prepared import prep
from shapely.validation import make_valid

logger = logging.getLogger(__name__)


PolygonalGeometry = Polygon | MultiPolygon

GeometryFixer = Callable[[], BaseGeometry]

WGS84_LON_RANGE = (-180.0, 180.0)

WGS84_LAT_RANGE = (-90.0, 90.0)


def _as_polygonal(geom: BaseGeometry | None) -> PolygonalGeometry | None:

    if geom is None or not isinstance(geom, BaseGeometry):
        return None

    if isinstance(geom, (Polygon, MultiPolygon)):
        return geom

    return None


def to_polygon_list(geom: BaseGeometry | None) -> list[Polygon]:

    if geom is None or not isinstance(geom, BaseGeometry) or geom.is_empty:
        return []

    if isinstance(geom, Polygon):
        return [geom]

    if isinstance(geom, MultiPolygon):
        return [polygon for polygon in geom.geoms if isinstance(polygon, Polygon)]

    if isinstance(geom, GeometryCollection):
        out: list[Polygon] = []

        for sub_geom in geom.geoms:
            out.extend(to_polygon_list(sub_geom))

        return out

    return []


def ensure_polygonal(geom: BaseGeometry | None) -> PolygonalGeometry:

    polygonal = _as_polygonal(geom)

    if polygonal is not None:
        return polygonal

    parts = to_polygon_list(geom)

    if not parts:
        return Polygon()

    merged = unary_union(parts)

    polygonal = _as_polygonal(merged)

    if polygonal is None:
        return Polygon()

    return polygonal


def make_valid_if_needed(
    geom: BaseGeometry,
    fix_invalid: bool = True,
    fallback_buffer_distance: float = 0.0,
) -> PolygonalGeometry:

    if geom is None or not hasattr(geom, "is_valid"):
        return Polygon()

    if geom.is_empty:
        return Polygon()

    current_geom = ensure_polygonal(geom)

    if current_geom and current_geom.is_valid:
        return current_geom

    if not fix_invalid:
        return ensure_polygonal(geom)

    strategies: list[tuple[str, GeometryFixer]] = [
        ("buffer_zero", lambda: geom.buffer(0)),
        ("make_valid", lambda: make_valid(geom)),
        ("envelope", lambda: geom.envelope),
    ]

    if fallback_buffer_distance > 0:
        strategies.append(
            ("centroid_buffer", lambda: geom.centroid.buffer(fallback_buffer_distance))
        )

    for strategy_name, strategy in strategies:
        try:
            fixed = strategy()

        except (GEOSException, TopologicalError, TypeError, ValueError) as exc:
            logger.debug("Strategy %s failed: %s", strategy_name, exc)

            continue

        polygonal = ensure_polygonal(fixed)

        if polygonal and polygonal.is_valid:
            logger.debug("Invalid geometry repaired using strategy: %s", strategy_name)

            return polygonal

    logger.warning(
        "Could not repair invalid geometry. Returning empty geometry.",
        extra={"repair_strategies": len(strategies)},
    )

    return Polygon()


def clip_polygons_to_boundary(
    polygons: Sequence[Polygon],
    boundary: Polygon,
    *,
    fix_invalid: bool,
) -> list[Polygon]:

    prepared_boundary = prep(boundary)

    output: list[Polygon] = []

    for polygon in polygons:
        if not prepared_boundary.intersects(polygon):
            continue

        clipped = make_valid_if_needed(polygon.intersection(boundary), fix_invalid=fix_invalid)

        output.extend(to_polygon_list(clipped))

    return output


def dissolve_polygons(polygons: Sequence[BaseGeometry], *, fix_invalid: bool) -> PolygonalGeometry:

    parts: list[Polygon] = []

    for polygon in polygons:
        parts.extend(to_polygon_list(polygon))

    if not parts:
        return Polygon()

    return ensure_polygonal(make_valid_if_needed(unary_union(parts), fix_invalid=fix_invalid))


def is_valid_wgs84_coord(lon: float, lat: float) -> bool:

    return (
        WGS84_LON_RANGE[0] <= lon <= WGS84_LON_RANGE[1]
        and WGS84_LAT_RANGE[0] <= lat <= WGS84_LAT_RANGE[1]
    )
