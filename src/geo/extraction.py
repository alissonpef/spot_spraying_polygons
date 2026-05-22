from __future__ import annotations

from collections.abc import Sequence

from pyproj import Transformer
from shapely.errors import GEOSException
from shapely.geometry import Polygon, shape

from src.geo.geometry import make_valid_if_needed, to_polygon_list


def extract_polygons_from_featurecollection(
    geojson: dict,
    transformer: Transformer,
    *,
    fix_invalid: bool,
) -> list[Polygon]:
    polygons: list[Polygon] = []
    features = geojson.get("features", [])
    if not isinstance(features, list):
        return polygons

    for feature in features:
        if not isinstance(feature, dict):
            continue

        geometry_data = feature.get("geometry")
        if not geometry_data:
            continue

        try:
            raw_geom = shape(geometry_data)
        except (TypeError, ValueError, GEOSException):
            continue

        geom = make_valid_if_needed(raw_geom, fix_invalid=fix_invalid)
        if geom.is_empty or geom.geom_type not in {"Polygon", "MultiPolygon"}:
            continue

        for polygon in to_polygon_list(geom):
            sample = polygon.exterior.coords[0]
            if not (-180.0 <= sample[0] <= 180.0 and -90.0 <= sample[1] <= 90.0):
                continue

            exterior_coords = [transformer.transform(x, y) for x, y in polygon.exterior.coords]
            interior_coords = [
                [transformer.transform(x, y) for x, y in ring.coords] for ring in polygon.interiors
            ]

            try:
                transformed = Polygon(exterior_coords, interior_coords)
            except (TypeError, ValueError):
                continue

            if transformed.is_empty or transformed.area <= 0:
                continue
            polygons.append(transformed)

    return polygons


def transform_polygons(polygons: Sequence[Polygon], transformer: Transformer) -> list[Polygon]:
    transformed: list[Polygon] = []
    for polygon in polygons:
        exterior = [transformer.transform(x, y) for x, y in polygon.exterior.coords]
        interiors = [
            [transformer.transform(x, y) for x, y in ring.coords] for ring in polygon.interiors
        ]
        transformed_polygon = Polygon(exterior, interiors)
        if transformed_polygon.is_empty or transformed_polygon.area <= 0:
            continue
        transformed.append(transformed_polygon)
    return transformed


def extract_and_transform(
    geojson: dict,
    transformer: Transformer,
    fix_invalid: bool = True,
) -> list[Polygon]:
    return extract_polygons_from_featurecollection(
        geojson,
        transformer,
        fix_invalid=fix_invalid,
    )
