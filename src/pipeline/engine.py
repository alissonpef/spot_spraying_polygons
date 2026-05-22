from __future__ import annotations

import logging
from collections.abc import Mapping

from shapely import STRtree
from shapely.errors import GEOSException, TopologicalError
from shapely.geometry import mapping
from shapely.ops import transform as shp_transform

from src.algorithms import generate_spray_geometry_for_field
from src.core.config import AlgorithmConfig
from src.geo.extraction import extract_and_transform
from src.geo.geometry import make_valid_if_needed, to_polygon_list
from src.geo.projection import prepare_projection
from src.geo.spatial_index import query_tree_indices
from src.io.geojson import empty_feature_collection

logger = logging.getLogger(__name__)


def _coerce_config(config: AlgorithmConfig | Mapping[str, object] | None) -> AlgorithmConfig:
    if config is None:
        return AlgorithmConfig()
    if isinstance(config, AlgorithmConfig):
        return config
    return AlgorithmConfig.from_mapping(config)


def generate_spraying_per_field(
    weeds_geojson: dict,
    obstacles_geojson: dict,
    fields_geojson: dict,
    config: AlgorithmConfig | Mapping[str, object] | None,
) -> dict:
    algorithm_config = _coerce_config(config)
    projection = prepare_projection(weeds_geojson, algorithm_config)
    t2m = projection.to_metric
    t2w = projection.to_wgs84

    weeds_m = extract_and_transform(
        weeds_geojson,
        t2m,
        fix_invalid=algorithm_config.fix_invalid_geometries,
    )
    fields_m = extract_and_transform(
        fields_geojson,
        t2m,
        fix_invalid=algorithm_config.fix_invalid_geometries,
    )
    obstacles_m = (
        extract_and_transform(
            obstacles_geojson,
            t2m,
            fix_invalid=algorithm_config.fix_invalid_geometries,
        )
        if obstacles_geojson.get("features")
        else []
    )

    if not weeds_m or not fields_m:
        return empty_feature_collection()

    all_features: list[dict] = []
    weeds_tree = STRtree(weeds_m)
    merge_distance_m = algorithm_config.merge_distance_m

    for idx, field in enumerate(fields_m):
        logger.info("── Field %d/%d ──", idx + 1, len(fields_m))

        candidate_indexes = query_tree_indices(weeds_tree, field.envelope)
        local_weeds = [weeds_m[int(index)] for index in candidate_indexes]
        if not local_weeds:
            continue

        try:
            result = generate_spray_geometry_for_field(
                local_weeds,
                obstacles_m,
                field,
                algorithm_config,
            )
        except (ValueError, RuntimeError, GEOSException, TopologicalError) as exc:
            logger.warning(
                "Failed to generate rectangles in field %d: %s. Field will be ignored.",
                idx + 1,
                exc,
                extra={"field_idx": idx + 1, "error_type": type(exc).__name__},
            )
            logger.debug("Failed field %d details", idx + 1, exc_info=True)
            continue

        if result.is_empty:
            continue

        for poly_m in to_polygon_list(result):
            poly_wgs = shp_transform(t2w.transform, poly_m)
            poly_wgs_fixed = make_valid_if_needed(
                poly_wgs,
                fix_invalid=algorithm_config.fix_invalid_geometries,
            )

            for poly in to_polygon_list(poly_wgs_fixed):
                if poly.is_empty:
                    continue
                poly_metric_area = shp_transform(t2m.transform, poly).area
                if poly_metric_area <= 0.0001:
                    continue
                all_features.append(
                    {
                        "type": "Feature",
                        "geometry": mapping(poly),
                        "properties": {
                            "field_id": idx,
                            "field_name": f"Field {idx + 1}",
                            "area_m2": round(poly_metric_area, 4),
                            "merge_distance_m": round(merge_distance_m, 1),
                            "coverage_method": algorithm_config.normalized_coverage_method,
                        },
                    }
                )

    return {"type": "FeatureCollection", "features": all_features}
