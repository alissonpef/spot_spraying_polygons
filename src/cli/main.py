from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

from shapely.errors import GEOSException

from src.core.config import AlgorithmConfig, Config
from src.io.geojson import empty_feature_collection, load_geojsons, save_geojson
from src.pipeline import generate_catacao_per_talhao

logging.basicConfig(
    level=Config.LOG_LEVEL,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)


def _non_negative_float(value: str) -> float:
    parsed = float(value)
    if parsed < 0:
        raise argparse.ArgumentTypeError("Valor deve ser >= 0")
    return parsed


def _ratio_zero_one(value: str) -> float:
    parsed = float(value)
    if not 0.0 <= parsed <= 1.0:
        raise argparse.ArgumentTypeError("Valor deve estar entre 0.0 e 1.0")
    return parsed


def _min_depth(value: str) -> int:
    parsed = int(value)
    if parsed < 1:
        raise argparse.ArgumentTypeError("Valor deve ser >= 1")
    return parsed


def _min_sides(value: str) -> int:
    parsed = int(value)
    if parsed < 4:
        raise argparse.ArgumentTypeError("Valor deve ser >= 4")
    return parsed


def _positive_float(value: str) -> float:
    parsed = float(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("Valor deve ser > 0")
    return parsed


def _positive_int(value: str) -> int:
    parsed = int(value)
    if parsed < 1:
        raise argparse.ArgumentTypeError("Valor deve ser >= 1")
    return parsed


def _parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--daninhas", nargs="+", required=True)
    parser.add_argument("--talhoes", nargs="+", required=True)
    parser.add_argument("--obstaculos", nargs="*", default=[])
    parser.add_argument("--saida", required=True)
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
    parser.add_argument("--dbscan_min_samples", type=_positive_int)
    parser.add_argument("--working_crs", type=str)
    return parser.parse_args()


def _load_config(config_path: str | None) -> dict:
    base_config = AlgorithmConfig().to_dict()
    if not config_path:
        return base_config

    path = Path(config_path)
    if not path.exists():
        raise FileNotFoundError(f"Arquivo de config não encontrado: {config_path}")

    with open(path, "r", encoding="utf-8") as file_handle:
        user_config = json.load(file_handle)
    if not isinstance(user_config, dict):
        raise ValueError("Arquivo de config deve conter um objeto JSON.")

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
        "dbscan_min_samples",
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
        logger.info("Iniciando processamento do worker")

        Config.ensure_directories()

        weeds_geojson = load_geojsons(args.daninhas)
        talhoes_geojson = load_geojsons(args.talhoes)
        obstacles_geojson = (
            load_geojsons(args.obstaculos, allow_missing=True)
            if args.obstaculos
            else empty_feature_collection()
        )

        if not weeds_geojson.get("features") or not talhoes_geojson.get("features"):
            logger.error("Arquivos de entrada vazios ou inválidos.")
            return 1

        algorithm_config = AlgorithmConfig.from_mapping(_apply_cli_overrides(_load_config(args.config), args))

        result_geojson = generate_catacao_per_talhao(
            weeds_geojson=weeds_geojson,
            obstacles_geojson=obstacles_geojson,
            talhoes_geojson=talhoes_geojson,
            config=algorithm_config,
        )

        save_geojson(result_geojson, args.saida)
        logger.info("Processamento concluído com sucesso. Salvo em: %s", args.saida)
        return 0

    except (FileNotFoundError, ValueError, json.JSONDecodeError, OSError, GEOSException) as exc:
        logger.error("Erro no processamento: %s", exc, exc_info=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())
