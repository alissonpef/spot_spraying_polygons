from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Mapping

from pyproj import CRS, Transformer
from shapely.errors import GEOSException
from shapely.geometry import shape
from shapely.geometry.base import BaseGeometry

from src.core.config import AlgorithmConfig
from src.geo.geometry import is_valid_wgs84_coord

logger = logging.getLogger(__name__)
FALLBACK_WORKING_CRS = "EPSG:32721"


@dataclass(frozen=True, slots=True)
class ProjectionContext:
    target_crs: CRS
    to_metric: Transformer
    to_wgs84: Transformer

    def __iter__(self):
        yield self.to_metric
        yield self.to_wgs84


def resolve_working_crs(hint: Any, reference: dict | None = None) -> str:
    if hint:
        if isinstance(hint, str):
            return hint
        if isinstance(hint, int):
            return f"EPSG:{hint}"

    if not reference:
        return FALLBACK_WORKING_CRS

    first_geom = _first_geometry(reference)
    if first_geom is None or first_geom.is_empty:
        return FALLBACK_WORKING_CRS

    centroid = first_geom.centroid
    lon, lat = centroid.x, centroid.y
    if not is_valid_wgs84_coord(lon, lat):
        logger.warning("Centroide fora do range WGS84. Usando fallback %s.", FALLBACK_WORKING_CRS)
        return FALLBACK_WORKING_CRS

    zone_number = int((lon + 180) / 6) + 1
    hemisphere = "6" if lat >= 0 else "7"
    return f"EPSG:32{hemisphere}{zone_number:02d}"


def prepare_projection(
    weeds_geojson: dict,
    config: AlgorithmConfig | Mapping[str, Any] | None = None,
) -> ProjectionContext:
    working_crs_hint = _extract_working_crs_hint(config)
    working_crs = resolve_working_crs(working_crs_hint, weeds_geojson)
    target_crs = CRS.from_user_input(working_crs)

    to_metric = Transformer.from_crs("EPSG:4326", target_crs, always_xy=True)
    to_wgs84 = Transformer.from_crs(target_crs, "EPSG:4326", always_xy=True)

    return ProjectionContext(target_crs=target_crs, to_metric=to_metric, to_wgs84=to_wgs84)


def _extract_working_crs_hint(config: AlgorithmConfig | Mapping[str, Any] | None) -> Any:
    if config is None:
        return None
    if isinstance(config, AlgorithmConfig):
        return config.working_crs
    return config.get("working_crs")


def _first_geometry(reference: dict) -> BaseGeometry | None:
    features = reference.get("features")
    if isinstance(features, list):
        for feature in features:
            geometry = feature.get("geometry") if isinstance(feature, dict) else None
            if not geometry:
                continue
            parsed = _parse_geometry(geometry)
            if parsed is not None:
                return parsed
        return None

    if reference.get("type") in {
        "Polygon",
        "MultiPolygon",
        "Point",
        "LineString",
        "MultiPoint",
        "MultiLineString",
    }:
        return _parse_geometry(reference)

    return None


def _parse_geometry(geometry_data: dict) -> BaseGeometry | None:
    try:
        return shape(geometry_data)
    except (TypeError, ValueError, GEOSException):
        return None
