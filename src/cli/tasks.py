from __future__ import annotations

import argparse
import os
import subprocess
import sys
from collections.abc import Iterable
from pathlib import Path

from src.core.config import SUPPORTED_COVERAGE_METHODS
from src.utils.pulverization_lines import batch as spraying_lines_batch

ROOT_DIR = Path(__file__).resolve().parents[2]

INPUT_DIR = ROOT_DIR / "data" / "input"

OUTPUT_DIR = ROOT_DIR / "data" / "output"

POLYGONS_DIR = OUTPUT_DIR / "polygons"

LINES_DIR = OUTPUT_DIR / "lines"

METRICS_MODULES = (
    "src.utils.metrics.geometric",
    "src.utils.metrics.iou",
    "src.utils.metrics.sensitivity",
    "src.utils.metrics.statistical",
)

SUPPORTED_METHODS_ORDER = (
    "mrr",
    "bcd",
    "fixed-grid",
    "quadtree",
    "convex-hull",
    "concave-hull",
    "aabb",
    "morph-closing",
    "strip-based",
)


WEED_FILES = [
    INPUT_DIR / "weed1.geojson",
    INPUT_DIR / "weed2.geojson",
    INPUT_DIR / "weed3.geojson",
]

FIELDS_FILE = INPUT_DIR / "fields.geojson"


def _run_module(module: str, args: Iterable[str]) -> None:

    subprocess.run([sys.executable, "-m", module, *args], check=True)


def _ensure_dirs() -> None:

    POLYGONS_DIR.mkdir(parents=True, exist_ok=True)

    LINES_DIR.mkdir(parents=True, exist_ok=True)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def _run_metrics_module(module: str) -> None:

    _run_module(module, [])


def _build_process_method_parser() -> argparse.ArgumentParser:

    parser = argparse.ArgumentParser(
        prog="process-method",
        description="Generate a single spray method with explicit core parameters.",
    )

    parser.add_argument(
        "coverage_method",
        choices=sorted(SUPPORTED_COVERAGE_METHODS),
        help="Coverage method to generate.",
    )

    parser.add_argument("weed_buffer_m", type=float, help="Weed buffer in meters.")

    parser.add_argument("merge_distance_m", type=float, help="Clustering distance in meters.")

    parser.add_argument(
        "obstacle_safety_buffer_m",
        type=float,
        help="Obstacle safety buffer in meters.",
    )

    parser.add_argument("--negative-buffer-m", type=float)

    parser.add_argument("--min-polygon-area-m2", type=float)

    parser.add_argument("--rectangle-min-fill-ratio", type=float)

    parser.add_argument("--rectangle-max-depth", type=int)

    parser.add_argument("--max-polygon-sides", type=int)

    parser.add_argument("--grid-cell-size-m", type=float)

    parser.add_argument("--grid-fill-threshold", type=float)

    parser.add_argument("--quadtree-min-cell-size-m", type=float)

    parser.add_argument("--quadtree-fill-threshold", type=float)

    parser.add_argument("--alpha-shape-radius-m", type=float)

    parser.add_argument("--strip-width-m", type=float)

    parser.add_argument("--strip-fill-threshold", type=float)

    parser.add_argument("--working-crs", type=str)

    parser.add_argument(
        "--fix-invalid-geometries",
        action=argparse.BooleanOptionalAction,
        default=None,
    )

    return parser


def _append_optional_flag(args: list[str], flag: str, value: object | None) -> None:

    if value is None:
        return

    args.extend([flag, str(value)])


def _build_process_method_args(parsed: argparse.Namespace) -> list[str]:

    args = [
        "--weeds",
        *[str(path) for path in WEED_FILES],
        "--fields",
        str(FIELDS_FILE),
        "--output",
        str(POLYGONS_DIR / f"spraying-{parsed.coverage_method}.geojson"),
        "--coverage_method",
        parsed.coverage_method,
        "--weed_buffer_m",
        str(parsed.weed_buffer_m),
        "--merge_distance_m",
        str(parsed.merge_distance_m),
        "--obstacle_safety_buffer_m",
        str(parsed.obstacle_safety_buffer_m),
    ]

    _append_optional_flag(args, "--negative_buffer_m", parsed.negative_buffer_m)

    _append_optional_flag(args, "--min_polygon_area_m2", parsed.min_polygon_area_m2)

    _append_optional_flag(args, "--rectangle_min_fill_ratio", parsed.rectangle_min_fill_ratio)

    _append_optional_flag(args, "--rectangle_max_depth", parsed.rectangle_max_depth)

    _append_optional_flag(args, "--max_polygon_sides", parsed.max_polygon_sides)

    _append_optional_flag(args, "--grid_cell_size_m", parsed.grid_cell_size_m)

    _append_optional_flag(args, "--grid_fill_threshold", parsed.grid_fill_threshold)

    _append_optional_flag(args, "--quadtree_min_cell_size_m", parsed.quadtree_min_cell_size_m)

    _append_optional_flag(args, "--quadtree_fill_threshold", parsed.quadtree_fill_threshold)

    _append_optional_flag(args, "--alpha_shape_radius_m", parsed.alpha_shape_radius_m)

    _append_optional_flag(args, "--strip_width_m", parsed.strip_width_m)

    _append_optional_flag(args, "--strip_fill_threshold", parsed.strip_fill_threshold)

    _append_optional_flag(args, "--working_crs", parsed.working_crs)

    if parsed.fix_invalid_geometries is not None:
        args.append(
            "--fix_invalid_geometries"
            if parsed.fix_invalid_geometries
            else "--no-fix_invalid_geometries"
        )

    return args


def dev() -> None:

    _ensure_dirs()

    for method in SUPPORTED_METHODS_ORDER:
        output_file = POLYGONS_DIR / f"spraying-{method}.geojson"

        args = [
            "--weeds",
            *[str(path) for path in WEED_FILES],
            "--fields",
            str(FIELDS_FILE),
            "--output",
            str(output_file),
            "--coverage_method",
            method,
        ]

        _run_module("src.cli.main", args)


def process_method() -> None:

    _ensure_dirs()

    parsed = _build_process_method_parser().parse_args()

    _run_module("src.cli.main", _build_process_method_args(parsed))


def lines() -> None:

    _ensure_dirs()

    spraying_lines_batch.main(
        [
            str(POLYGONS_DIR),
            "2.0",
            "0.0",
            "--output-dir",
            str(LINES_DIR),
            "--recursive",
        ],
        standalone_mode=False,
    )


def metrics() -> None:

    _ensure_dirs()

    for module in METRICS_MODULES:
        _run_metrics_module(module)


def ui() -> None:

    app_path = ROOT_DIR / "src" / "ui" / "app.py"

    env = dict(os.environ)

    env_path = env.get("PYTHONPATH", "")

    env["PYTHONPATH"] = f"{ROOT_DIR}{os.pathsep}{env_path}" if env_path else str(ROOT_DIR)

    subprocess.run(
        [sys.executable, "-m", "streamlit", "run", str(app_path)],
        check=True,
        env=env,
    )
