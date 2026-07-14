from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

from shapely.errors import GEOSException

from src.core.config import AlgorithmConfig, Config
from src.io.geojson import empty_feature_collection, load_geojsons, save_geojson
from src.pipeline import generate_spraying_per_field

logging.basicConfig(
    level=Config.LOG_LEVEL,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)

logger = logging.getLogger(__name__)


def _non_negative_float(value: str) -> float:

    parsed = float(value)

    if parsed < 0:
        raise argparse.ArgumentTypeError("Value must be >= 0")

    return parsed


def _ratio_zero_one(value: str) -> float:

    parsed = float(value)

    if not 0.0 <= parsed <= 1.0:
        raise argparse.ArgumentTypeError("Value must be between 0.0 and 1.0")

    return parsed


def _min_depth(value: str) -> int:

    parsed = int(value)

    if parsed < 1:
        raise argparse.ArgumentTypeError("Value must be >= 1")

    return parsed


def _min_sides(value: str) -> int:

    parsed = int(value)

    if parsed < 4:
        raise argparse.ArgumentTypeError("Value must be >= 4")

    return parsed


def _positive_float(value: str) -> float:

    parsed = float(value)

    if parsed <= 0:
        raise argparse.ArgumentTypeError("Value must be > 0")

    return parsed


def _positive_int(value: str) -> int:

    parsed = int(value)

    if parsed < 1:
        raise argparse.ArgumentTypeError("Value must be >= 1")

    return parsed


def _parse_arguments() -> argparse.Namespace:

    parser = argparse.ArgumentParser()

    parser.add_argument("--weeds", nargs="+", required=True)

    parser.add_argument("--fields", nargs="+", required=True)

    parser.add_argument("--obstacles", nargs="*", default=[])

    parser.add_argument("--output", required=True)

    parser.add_argument("--config", type=str)

    parser.add_argument("--weed_buffer_m", type=_non_negative_float)

    parser.add_argument("--merge_distance_m", type=_non_negative_float)

    parser.add_argument("--obstacle_safety_buffer_m", type=_non_negative_float)

    parser.add_argument("--negative_buffer_m", type=_non_negative_float)

    parser.add_argument("--min_polygon_area_m2", type=_non_negative_float)

    parser.add_argument(
        "--fix_invalid_geometries",
        action=argparse.BooleanOptionalAction,
        default=None,
    )

    parser.add_argument("--rectangle_min_fill_ratio", type=_ratio_zero_one)

    parser.add_argument("--rectangle_max_depth", type=_min_depth)

    parser.add_argument("--max_polygon_sides", type=_min_sides)

    parser.add_argument("--coverage_method", type=str)

    parser.add_argument("--grid_cell_size_m", type=_positive_float)

    parser.add_argument("--grid_fill_threshold", type=_ratio_zero_one)

    parser.add_argument("--quadtree_min_cell_size_m", type=_positive_float)

    parser.add_argument("--quadtree_fill_threshold", type=_ratio_zero_one)

    parser.add_argument("--alpha_shape_radius_m", type=_positive_float)

    parser.add_argument("--strip_width_m", type=_positive_float)

    parser.add_argument("--strip_fill_threshold", type=_ratio_zero_one)

    parser.add_argument("--working_crs", type=str)

    return parser.parse_args()


def _load_config(config_path: str | None) -> dict:

    base_config = AlgorithmConfig().to_dict()

    if not config_path:
        return base_config

    path = Path(config_path)

    if not path.exists():
        raise FileNotFoundError(f"Configuration file not found: {config_path}")

    with open(path, encoding="utf-8") as file_handle:
        user_config = json.load(file_handle)

    if not isinstance(user_config, dict):
        raise ValueError("Configuration file must contain a JSON object.")

    base_config.update(user_config)

    return base_config


def _apply_cli_overrides(config: dict, args: argparse.Namespace) -> dict:

    override_keys = [
        "weed_buffer_m",
        "merge_distance_m",
        "obstacle_safety_buffer_m",
        "negative_buffer_m",
        "min_polygon_area_m2",
        "fix_invalid_geometries",
        "rectangle_min_fill_ratio",
        "rectangle_max_depth",
        "max_polygon_sides",
        "coverage_method",
        "grid_cell_size_m",
        "grid_fill_threshold",
        "quadtree_min_cell_size_m",
        "quadtree_fill_threshold",
        "alpha_shape_radius_m",
        "strip_width_m",
        "strip_fill_threshold",
        "working_crs",
    ]

    merged = dict(config)

    for key in override_keys:
        value = getattr(args, key, None)

        if value is not None:
            merged[key] = value

    return merged


def main() -> int:

    try:
        args = _parse_arguments()

        logger.info("Starting worker processing")

        Config.ensure_directories()

        weeds_geojson = load_geojsons(args.weeds)

        fields_geojson = load_geojsons(args.fields)

        obstacles_geojson = (
            load_geojsons(args.obstacles, allow_missing=True)
            if args.obstacles
            else empty_feature_collection()
        )

        if not weeds_geojson.get("features") or not fields_geojson.get("features"):
            logger.error("Input files are empty or invalid.")

            return 1

        algorithm_config = AlgorithmConfig.from_mapping(
            _apply_cli_overrides(_load_config(args.config), args)
        )

        result_geojson = generate_spraying_per_field(
            weeds_geojson=weeds_geojson,
            obstacles_geojson=obstacles_geojson,
            fields_geojson=fields_geojson,
            config=algorithm_config,
        )

        save_geojson(result_geojson, args.output)

        logger.info("Processing completed successfully. Saved to: %s", args.output)

        return 0

    except (FileNotFoundError, ValueError, json.JSONDecodeError, OSError, GEOSException) as exc:
        logger.error("Processing error: %s", exc, exc_info=True)

        return 1


if __name__ == "__main__":
    sys.exit(main())
