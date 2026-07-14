from __future__ import annotations

import argparse
import logging
import math
from dataclasses import dataclass
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
from shapely.geometry import Polygon
from shapely.ops import unary_union

from src.algorithms.coverage import MrrCoverageStrategy
from src.algorithms.factory import build_coverage_context
from src.core.config import AlgorithmConfig, Config
from src.geo.extraction import extract_and_transform
from src.geo.geometry import dissolve_polygons, to_polygon_list
from src.geo.projection import prepare_projection
from src.io.geojson import load_geojsons

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class SensitivityResult:
    rho_min: float

    max_depth: int

    total_area_m2: float

    final_polygon_count: int

    ground_truth_area_m2: float

    coverage_pct: float

    iou: float

    total_turns: int

    turns_per_ha: float

    mean_straight_line_length_m: float

    std_straight_line_length_m: float

    total_flight_length_m: float


def compute_operational_metrics_for_mrr(
    mrr_polygons: list[Polygon], ground_truth_polygons: list[Polygon], swath_width: float
) -> tuple[float, float, float, int, float, float, float]:

    if not mrr_polygons:
        return 0.0, 0.0, 0.0, 0, 0.0, 0.0, 0.0

    mrr_union = unary_union(mrr_polygons)

    total_area = mrr_union.area

    gt_union = unary_union(ground_truth_polygons)

    gt_area = gt_union.area

    intersection_area = mrr_union.intersection(gt_union).area

    union_area = mrr_union.union(gt_union).area

    iou = intersection_area / union_area if union_area > 0.0 else 0.0

    coverage_pct = (intersection_area / gt_area * 100.0) if gt_area > 0.0 else 0.0

    from src.utils.metrics.geometric import _analyze_linestring_turns
    from src.utils.pulverization_lines import SprayLineUtil, iter_line_strings

    util = SprayLineUtil()

    all_lines = []

    for mrr in mrr_polygons:
        coords = list(mrr.exterior.coords)

        if len(coords) < 4:
            continue

        dx1 = coords[1][0] - coords[0][0]

        dy1 = coords[1][1] - coords[0][1]

        len1 = math.hypot(dx1, dy1)

        dx2 = coords[2][0] - coords[1][0]

        dy2 = coords[2][1] - coords[1][1]

        len2 = math.hypot(dx2, dy2)

        angle_rad = math.atan2(dy1, dx1) if len1 >= len2 else math.atan2(dy2, dx2)

        angle_deg = math.degrees(angle_rad) % 180.0

        multiline = util.generate_lines(mrr, swath_width, angle_deg)

        all_lines.extend(list(iter_line_strings(multiline)))

    total_turns = 0

    all_straight_lengths = []

    total_spray_length = 0.0

    for line in all_lines:
        coords = list(line.coords)

        turns, lengths = _analyze_linestring_turns(coords)

        total_turns += turns

        all_straight_lengths.extend(lengths)

        total_spray_length += float(line.length)

    if all_lines:
        total_turns += max(len(all_lines) - 1, 0)

    mean_line_len = float(np.mean(all_straight_lengths)) if all_straight_lengths else 0.0

    std_line_len = float(np.std(all_straight_lengths)) if all_straight_lengths else 0.0

    turn_length_m = 0.0

    for idx in range(len(all_lines) - 1):
        pt_end = all_lines[idx].coords[-1]

        pt_start = all_lines[idx + 1].coords[0]

        turn_length_m += math.hypot(pt_start[0] - pt_end[0], pt_start[1] - pt_end[1])

    total_flight_length_m = total_spray_length + turn_length_m

    return (
        total_area,
        iou,
        coverage_pct,
        total_turns,
        mean_line_len,
        std_line_len,
        total_flight_length_m,
    )


def _run_sensitivity_analysis(
    metric_inputs: list[tuple[Path, list[Polygon]]],
    base_config: AlgorithmConfig,
    rho_values: list[float],
    depth_values: list[int],
) -> list[SensitivityResult]:

    strategy = MrrCoverageStrategy()

    results: list[SensitivityResult] = []

    ground_truth_polys = []

    for _, metric_polygons in metric_inputs:
        ground_truth_polys.extend(metric_polygons)

    ground_truth_area = unary_union(ground_truth_polys).area

    for max_depth in depth_values:
        for rho_min in rho_values:
            config = base_config.with_overrides(
                rectangle_min_fill_ratio=rho_min, rectangle_max_depth=max_depth
            )

            context = build_coverage_context(config)

            final_polygons: list[Polygon] = []

            for _, metric_polygons in metric_inputs:
                final_polygons.extend(strategy.generate(metric_polygons, context))

            dissolved = dissolve_polygons(final_polygons, fix_invalid=config.fix_invalid_geometries)

            final_polygon_count = len(to_polygon_list(dissolved))

            (total_area, iou, coverage_pct, tot_turns, mean_len, std_len, flight_len) = (
                compute_operational_metrics_for_mrr(
                    final_polygons, ground_truth_polys, swath_width=config.strip_width_m
                )
            )

            total_area_ha = total_area / 10000.0

            turns_per_ha = tot_turns / total_area_ha if total_area_ha > 0.0 else 0.0

            results.append(
                SensitivityResult(
                    rho_min=rho_min,
                    max_depth=max_depth,
                    total_area_m2=total_area,
                    final_polygon_count=final_polygon_count,
                    ground_truth_area_m2=ground_truth_area,
                    coverage_pct=coverage_pct,
                    iou=iou,
                    total_turns=tot_turns,
                    turns_per_ha=turns_per_ha,
                    mean_straight_line_length_m=mean_len,
                    std_straight_line_length_m=std_len,
                    total_flight_length_m=flight_len,
                )
            )

    return results


def _plot_results(results: list[SensitivityResult], output_path: Path) -> None:

    by_depth: dict[int, list[SensitivityResult]] = {}

    for r in results:
        by_depth.setdefault(r.max_depth, []).append(r)

    fig, axes = plt.subplots(2, 2, figsize=(14, 10))

    colors = {2: "#3498db", 4: "#e67e22", 8: "#2ecc71"}

    all_depths = sorted(by_depth.keys())

    for idx, d in enumerate(all_depths):
        if d not in colors:
            colors[d] = plt.cm.viridis(idx / max(1, len(all_depths) - 1))

    ax = axes[0, 0]

    for d in all_depths:
        res = sorted(by_depth[d], key=lambda x: x.rho_min)

        ax.plot(
            [x.rho_min for x in res],
            [x.total_area_m2 / 10000.0 for x in res],
            label=f"Depth {d}",
            color=colors[d],
            marker="o",
            linewidth=2.0,
        )

    ax.set_xlabel("Rho Min")

    ax.set_ylabel("Total Area (ha)")

    ax.grid(True, linestyle="--", alpha=0.5)

    ax.legend()

    ax = axes[0, 1]

    for d in all_depths:
        res = sorted(by_depth[d], key=lambda x: x.rho_min)

        ax.plot(
            [x.rho_min for x in res],
            [x.final_polygon_count for x in res],
            label=f"Depth {d}",
            color=colors[d],
            marker="s",
            linewidth=2.0,
        )

    ax.set_xlabel("Rho Min")

    ax.set_ylabel("Polygon Count")

    ax.grid(True, linestyle="--", alpha=0.5)

    ax.legend()

    ax = axes[1, 0]

    for d in all_depths:
        res = sorted(by_depth[d], key=lambda x: x.rho_min)

        ax.plot(
            [x.rho_min for x in res],
            [x.iou * 100.0 for x in res],
            label=f"Depth {d}",
            color=colors[d],
            marker="^",
            linewidth=2.0,
        )

    ax.set_xlabel("Rho Min")

    ax.set_ylabel("IoU (%)")

    ax.grid(True, linestyle="--", alpha=0.5)

    ax.legend()

    ax = axes[1, 1]

    for d in all_depths:
        res = sorted(by_depth[d], key=lambda x: x.rho_min)

        ax.plot(
            [x.rho_min for x in res],
            [x.total_flight_length_m for x in res],
            label=f"Depth {d}",
            color=colors[d],
            marker="v",
            linewidth=2.0,
        )

    ax.set_xlabel("Rho Min")

    ax.set_ylabel("Total Flight Length (m)")

    ax.grid(True, linestyle="--", alpha=0.5)

    ax.legend()

    plt.tight_layout()

    output_path.parent.mkdir(parents=True, exist_ok=True)

    plt.savefig(output_path, dpi=300, bbox_inches="tight")

    plt.close(fig)


def main():

    parser = argparse.ArgumentParser()

    parser.add_argument("--weeds", nargs="*", type=Path)

    parser.add_argument("--output-dir", type=Path, default=Path("data/output"))

    args = parser.parse_args()

    weed_paths = args.weeds if args.weeds else sorted(Config.INPUT_DIR.glob("weed*.geojson"))

    base_config = AlgorithmConfig(coverage_method="mrr")

    metric_inputs = []

    for path in weed_paths:
        single_geojson = load_geojsons([str(path)])

        projection = prepare_projection(single_geojson, base_config)

        metric_polygons = extract_and_transform(
            single_geojson, projection.to_metric, fix_invalid=base_config.fix_invalid_geometries
        )

        metric_inputs.append((path, metric_polygons))

    rho_values = [round(r, 2) for r in np.arange(0.0, 0.51, 0.01)]

    results = _run_sensitivity_analysis(metric_inputs, base_config, rho_values, [2, 4, 8])

    plots_dir = args.output_dir / "plots"

    metrics_dir = args.output_dir / "metrics"

    plots_dir.mkdir(parents=True, exist_ok=True)

    metrics_dir.mkdir(parents=True, exist_ok=True)

    _plot_results(results, plots_dir / "sensitivity_analysis_mrr.png")

    import pandas as pd

    rows = []

    for r in results:
        rows.append(
            {
                "rho_min": r.rho_min,
                "max_depth": r.max_depth,
                "total_area_ha": r.total_area_m2 / 10000.0,
                "final_polygon_count": r.final_polygon_count,
                "coverage_pct": r.coverage_pct,
                "iou_pct": r.iou * 100.0,
                "total_turns": r.total_turns,
                "mean_straight_line_m": r.mean_straight_line_length_m,
                "total_flight_length_km": r.total_flight_length_m / 1000.0,
            }
        )

    df = pd.DataFrame(rows)

    df.to_csv(metrics_dir / "sensitivity_analysis.csv", index=False)

    metrics_dir.joinpath("sensitivity_analysis.md").write_text(
        df.to_markdown(index=False), encoding="utf-8"
    )


if __name__ == "__main__":
    main()
