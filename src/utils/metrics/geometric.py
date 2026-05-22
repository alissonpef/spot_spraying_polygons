from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

import click
import geopandas as gpd
import numpy as np
import pandas as pd
from pyproj import CRS
from shapely.errors import GEOSException
from shapely.geometry import GeometryCollection, shape
from shapely.geometry.base import BaseGeometry
from shapely.ops import unary_union

from src.io.geojson import load_geojson

try:
    from shapely import make_valid as shapely_make_valid
except ImportError:
    shapely_make_valid = None

DEFAULT_OUTPUT_LINES_DIR = (
    Path("data/output/lines") if Path("data/output/lines").exists() else Path("data/output-lines")
)
DEFAULT_POLYGONS_DIR = (
    Path("data/output/polygons") if Path("data/output/polygons").exists() else Path("data/output")
)
DEFAULT_OUTPUT_DIR = Path("data/output")
TARGET_LINE_TYPE = "spray"
FIELD_ID_CANDIDATES = ("field_id", "field", "id", "ID")


@dataclass(slots=True)
class FieldMetrics:
    field_id: int
    num_polygons: int = 0
    target_area_m2: float = 0.0
    target_perimeter_m: float = 0.0
    line_lengths_m: tuple[float, ...] = ()
    num_turns: int = 0
    target_coverage_area_m2: float = 0.0
    clean_area_waste_m2: float = 0.0


def _resolve_source_crs(geojson_data: dict[str, Any]) -> CRS:
    crs_data = geojson_data.get("crs")
    if isinstance(crs_data, dict):
        properties = crs_data.get("properties")
        if isinstance(properties, dict):
            crs_name = properties.get("name")
            if isinstance(crs_name, str) and crs_name.strip():
                return CRS.from_user_input(crs_name.strip())
    return CRS.from_epsg(4326)


def _ensure_valid_geometry(geometry: BaseGeometry | None) -> BaseGeometry | None:
    if geometry is None or geometry.is_empty:
        return geometry
    if geometry.is_valid:
        return geometry
    if shapely_make_valid is not None:
        fixed_geometry = shapely_make_valid(geometry)
        if fixed_geometry is not None and not fixed_geometry.is_empty:
            return fixed_geometry
    return geometry.buffer(0)


def _safe_union(geometries: list[BaseGeometry]) -> BaseGeometry | None:
    valid_geometries = [geometry for geometry in geometries if geometry is not None and not geometry.is_empty]
    if not valid_geometries:
        return None

    try:
        merged = unary_union(valid_geometries)
    except GEOSException:
        repaired_geometries = [
            repaired
            for geometry in valid_geometries
            if (repaired := _ensure_valid_geometry(geometry)) is not None and not repaired.is_empty
        ]
        if not repaired_geometries:
            return None

        try:
            merged = unary_union(repaired_geometries)
        except GEOSException:
            merged = GeometryCollection(repaired_geometries)

    return _ensure_valid_geometry(merged)


def _iter_atomic_geometries(
    geometry: BaseGeometry, allowed_types: set[str]
) -> Iterable[BaseGeometry]:
    if geometry.is_empty:
        return
    if geometry.geom_type in allowed_types:
        yield geometry
        return
    geometries = getattr(geometry, "geoms", None)
    if geometries is None:
        return
    for part in geometries:
        yield from _iter_atomic_geometries(part, allowed_types)


def _normalize_field_id(value: Any) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value) if value.is_integer() else None
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return None
        try:
            numeric_value = float(stripped)
        except ValueError:
            return None
        return int(numeric_value) if numeric_value.is_integer() else None
    return None


def _detect_field_id_column(columns: Iterable[str]) -> str | None:
    normalized_lookup = {column.lower(): column for column in columns}
    for candidate in FIELD_ID_CANDIDATES:
        column = normalized_lookup.get(candidate.lower())
        if column is not None:
            return column
    return None


def _load_feature_rows(
    file_path: Path, allowed_types: set[str], default_field_id: int | None
) -> tuple[list[dict[str, Any]], CRS]:
    geojson_data = load_geojson(file_path)
    if not isinstance(geojson_data, dict) or geojson_data.get("type") != "FeatureCollection":
        raise click.ClickException(f"Invalid GeoJSON file: {file_path}")
    features = geojson_data.get("features")
    if not isinstance(features, list):
        raise click.ClickException(f"Invalid GeoJSON file: {file_path}")
    source_crs = _resolve_source_crs(geojson_data)
    rows: list[dict[str, Any]] = []
    for feature in features:
        if not isinstance(feature, dict):
            continue
        geometry_data = feature.get("geometry")
        if geometry_data is None:
            continue
        try:
            geometry = shape(geometry_data)
        except (TypeError, ValueError, GEOSException):
            continue
        valid_geometry = _ensure_valid_geometry(geometry)
        if valid_geometry is None or valid_geometry.is_empty:
            continue
        properties = feature.get("properties")
        if not isinstance(properties, dict):
            properties = {}
        for atomic_geometry in _iter_atomic_geometries(valid_geometry, allowed_types):
            row = dict(properties)
            row["geometry"] = atomic_geometry
            rows.append(row)
    if not rows:
        return [], source_crs
    if default_field_id is not None:
        for row in rows:
            row.setdefault("field_id", default_field_id)
    return rows, source_crs


def _load_geodataframe(
    file_path: Path,
    allowed_types: set[str],
    default_field_id: int | None,
    *,
    require_geometry: bool = True,
) -> gpd.GeoDataFrame:
    rows, source_crs = _load_feature_rows(file_path, allowed_types, default_field_id)
    if not rows:
        if require_geometry:
            raise click.ClickException(f"No valid geometry found in {file_path}")
        return gpd.GeoDataFrame(
            columns=["field_id", "geometry"], geometry="geometry", crs=source_crs
        )
    gdf = gpd.GeoDataFrame(rows, geometry="geometry", crs=source_crs)
    gdf = gdf[gdf.geometry.notna() & ~gdf.geometry.is_empty].copy()
    field_id_column = _detect_field_id_column(gdf.columns)
    if field_id_column is None:
        gdf["field_id"] = pd.Series([pd.NA] * len(gdf), index=gdf.index, dtype="Int64")
    elif field_id_column != "field_id":
        gdf = gdf.rename(columns={field_id_column: "field_id"})
    gdf["field_id"] = gdf["field_id"].map(_normalize_field_id)
    gdf["field_id"] = pd.Series(gdf["field_id"], index=gdf.index, dtype="Int64")
    if default_field_id is not None:
        gdf["field_id"] = gdf["field_id"].fillna(default_field_id)
    return gdf.reset_index(drop=True)


def _prepare_metric_crs(polygon_gdf: gpd.GeoDataFrame) -> CRS:
    if polygon_gdf.crs is None:
        polygon_gdf = polygon_gdf.set_crs(CRS.from_epsg(4326))
    if polygon_gdf.crs.is_geographic:
        try:
            estimated_crs = polygon_gdf.estimate_utm_crs()
            if estimated_crs is not None:
                return CRS.from_user_input(estimated_crs)
        except Exception:
            pass
    return CRS.from_user_input(polygon_gdf.crs)


def _field_groups(gdf: gpd.GeoDataFrame) -> dict[int, gpd.GeoDataFrame]:
    return {int(field_id): group.copy() for field_id, group in gdf.groupby("field_id", sort=True)}


def _select_spray_lines(line_gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    if "line_type" not in line_gdf.columns:
        return line_gdf
    spray_lines = line_gdf[line_gdf["line_type"].astype(str).str.lower() == TARGET_LINE_TYPE].copy()
    if spray_lines.empty:
        return line_gdf
    return spray_lines


def _analyze_linestring_turns(
    coords: list[tuple[float, float]], angle_threshold: float = 45.0
) -> tuple[int, list[float]]:
    if len(coords) < 2:
        return 0, []
    turns = 0
    straight_lengths = []
    current_straight_length = 0.0
    for i in range(1, len(coords)):
        p1 = coords[i - 1]
        p2 = coords[i]
        dist = float(np.hypot(p2[0] - p1[0], p2[1] - p1[1]))
        if i == 1:
            current_straight_length += dist
            continue
        p0 = coords[i - 2]
        v1 = (p1[0] - p0[0], p1[1] - p0[1])
        v2 = (p2[0] - p1[0], p2[1] - p1[1])
        norm1 = float(np.hypot(*v1))
        norm2 = float(np.hypot(*v2))
        if norm1 > 0 and norm2 > 0:
            cos_theta = (v1[0] * v2[0] + v1[1] * v2[1]) / (norm1 * norm2)
            cos_theta = max(-1.0, min(1.0, cos_theta))
            angle_deg = np.degrees(np.arccos(cos_theta))
            if angle_deg >= angle_threshold:
                turns += 1
                if current_straight_length > 0:
                    straight_lengths.append(current_straight_length)
                current_straight_length = dist
            else:
                current_straight_length += dist
        else:
            current_straight_length += dist
    if current_straight_length > 0:
        straight_lengths.append(current_straight_length)
    return turns, straight_lengths


def _aggregate_field_metrics(
    field_id: int,
    polygon_group: gpd.GeoDataFrame,
    line_group: gpd.GeoDataFrame,
    swath_width_m: float,
) -> FieldMetrics:
    polygon_parts = polygon_group.geometry.to_list()
    if not polygon_parts:
        return FieldMetrics(field_id=field_id)
    target_geom = _safe_union(polygon_parts)
    if target_geom is None:
        return FieldMetrics(field_id=field_id)
    target_area_m2 = float(np.sum(polygon_group.geometry.area.to_numpy(dtype=float)))
    target_perimeter_m = float(np.sum(polygon_group.geometry.length.to_numpy(dtype=float)))
    num_polygons = int(len(polygon_group))
    spray_lines = _select_spray_lines(line_group)
    if spray_lines.empty:
        spray_lines = line_group
    spray_lines = spray_lines[spray_lines.geometry.geom_type == "LineString"].copy()
    total_line_length_m = 0.0
    total_turns = 0
    all_straight_lengths = []
    for geom in spray_lines.geometry:
        coords = list(geom.coords)
        turns, lengths = _analyze_linestring_turns(coords)
        total_turns += turns
        all_straight_lengths.extend(lengths)
        total_line_length_m += float(geom.length)
    if not spray_lines.empty:
        total_turns += max(len(spray_lines) - 1, 0)
    num_turns = total_turns
    line_lengths_m = tuple(float(length) for length in all_straight_lengths if length > 0.0)
    target_coverage_area_m2 = 0.0
    clean_area_waste_m2 = 0.0
    if target_area_m2 > 0.0 and total_line_length_m > 0.0 and not spray_lines.empty:
        corridor_parts = spray_lines.geometry.buffer(
            swath_width_m / 2.0, cap_style=2, join_style=2
        ).to_list()
        corridor_geom = _safe_union(corridor_parts)
        if corridor_geom is None:
            return FieldMetrics(field_id=field_id)
        target_coverage_area_m2 = float(corridor_geom.intersection(target_geom).area)
        clean_area_waste_m2 = float(corridor_geom.difference(target_geom).area)
    return FieldMetrics(
        field_id=field_id,
        num_polygons=num_polygons,
        target_area_m2=target_area_m2,
        target_perimeter_m=target_perimeter_m,
        line_lengths_m=line_lengths_m,
        num_turns=num_turns,
        target_coverage_area_m2=target_coverage_area_m2,
        clean_area_waste_m2=clean_area_waste_m2,
    )


def _discover_method_sources(output_lines_dir: Path) -> list[Path]:
    candidates: dict[str, Path] = {}
    for entry in output_lines_dir.iterdir():
        if entry.is_dir():
            if any(entry.glob("pulverizacao_*.geojson")):
                candidates.setdefault(entry.name, entry)
            continue
        if entry.is_file() and entry.suffix.lower() == ".geojson":
            candidates.setdefault(entry.stem, entry)
    return [candidates[name] for name in sorted(candidates)]


def _field_id_set(gdf: gpd.GeoDataFrame) -> set[int]:
    if "field_id" not in gdf.columns:
        return set()
    normalized_ids: set[int] = set()
    for value in gdf["field_id"].dropna().tolist():
        normalized = _normalize_field_id(value)
        if normalized is not None:
            normalized_ids.add(normalized)
    return normalized_ids


def _load_method_dataframe(
    method_source: Path, polygons_dir: Path, swath_width_m: float
) -> pd.DataFrame:
    method_name = method_source.name if method_source.is_dir() else method_source.stem
    polygon_file = polygons_dir / f"{method_name}.geojson"
    if not polygon_file.exists():
        raise click.ClickException(f"Polygon file not found: {polygon_file}")
    polygon_gdf = _load_geodataframe(polygon_file, {"Polygon", "MultiPolygon"}, None)
    metric_crs = _prepare_metric_crs(polygon_gdf)
    polygon_metric = polygon_gdf.to_crs(metric_crs)
    line_frames: list[gpd.GeoDataFrame] = []
    line_files = (
        sorted(method_source.glob("pulverizacao_*.geojson"))
        if method_source.is_dir()
        else [method_source]
    )
    for line_file in line_files:
        match = re.fullmatch(r"pulverizacao_(\d+)", line_file.stem)
        default_field_id = int(match.group(1)) if match is not None else None
        line_gdf = _load_geodataframe(
            line_file, {"LineString", "MultiLineString"}, default_field_id, require_geometry=False
        )
        line_frames.append(line_gdf.to_crs(metric_crs))
    if line_frames:
        line_metric = gpd.GeoDataFrame(
            pd.concat(line_frames, ignore_index=True), geometry="geometry", crs=metric_crs
        )
    else:
        line_metric = gpd.GeoDataFrame(
            columns=["field_id", "geometry"], geometry="geometry", crs=metric_crs
        )
    polygon_ids = _field_id_set(polygon_metric)
    line_ids = _field_id_set(line_metric)
    shared_ids = polygon_ids & line_ids
    use_field_groups = bool(shared_ids) and polygon_ids == line_ids
    if use_field_groups:
        field_polygon_groups = _field_groups(polygon_metric)
        field_line_groups = _field_groups(line_metric)
        field_metrics = [
            _aggregate_field_metrics(
                field_id=field_id,
                polygon_group=field_polygon_groups[field_id],
                line_group=field_line_groups[field_id],
                swath_width_m=swath_width_m,
            )
            for field_id in sorted(shared_ids)
        ]
    else:
        if polygon_metric.empty:
            raise click.ClickException(f"No valid geometry found for method {method_name}.")
        field_metrics = [
            _aggregate_field_metrics(
                field_id=0,
                polygon_group=polygon_metric,
                line_group=line_metric,
                swath_width_m=swath_width_m,
            )
        ]
    total_target_area_m2 = float(np.sum([metric.target_area_m2 for metric in field_metrics]))
    total_target_perimeter_m = float(
        np.sum([metric.target_perimeter_m for metric in field_metrics])
    )
    total_target_coverage_area_m2 = float(
        np.sum([metric.target_coverage_area_m2 for metric in field_metrics])
    )
    total_clean_area_waste_m2 = float(
        np.sum([metric.clean_area_waste_m2 for metric in field_metrics])
    )
    straight_line_lengths = np.asarray(
        [length for metric in field_metrics for length in metric.line_lengths_m], dtype=float
    )
    num_turns = int(np.sum([metric.num_turns for metric in field_metrics]))
    num_polygons = int(np.sum([metric.num_polygons for metric in field_metrics]))
    mean_straight_line_length_m = (
        float(np.mean(straight_line_lengths)) if straight_line_lengths.size else 0.0
    )
    std_straight_line_length_m = (
        float(np.std(straight_line_lengths)) if straight_line_lengths.size else 0.0
    )
    total_area_ha = total_target_area_m2 / 10000.0
    turns_per_ha = (num_turns / total_area_ha) if total_area_ha > 0.0 else 0.0
    area_perimeter_ratio = (
        total_target_area_m2 / total_target_perimeter_m if total_target_perimeter_m > 0.0 else 0.0
    )
    target_coverage_pct = (
        (total_target_coverage_area_m2 / total_target_area_m2 * 100.0)
        if total_target_area_m2 > 0.0
        else 0.0
    )
    clean_area_waste_pct = (
        (total_clean_area_waste_m2 / total_target_area_m2 * 100.0)
        if total_target_area_m2 > 0.0
        else 0.0
    )
    return pd.DataFrame(
        [
            {
                "method": method_name,
                "num_polygons": num_polygons,
                "total_area_ha": total_area_ha,
                "area_perimeter_ratio": area_perimeter_ratio,
                "mean_straight_length_m": mean_straight_line_length_m,
                "std_straight_length_m": std_straight_line_length_m,
                "num_turns": num_turns,
                "turns_per_ha": turns_per_ha,
                "target_coverage_pct": target_coverage_pct,
                "clean_area_waste_pct": clean_area_waste_pct,
            }
        ]
    )


def build_geometric_metrics(
    output_lines_dir: Path = DEFAULT_OUTPUT_LINES_DIR,
    polygons_dir: Path = DEFAULT_POLYGONS_DIR,
    swath_width_m: float = 2.0,
) -> pd.DataFrame:
    if not output_lines_dir.exists():
        raise click.ClickException(f"Lines directory not found: {output_lines_dir}")
    if not polygons_dir.exists():
        raise click.ClickException(f"Polygons directory not found: {polygons_dir}")
    method_frames: list[pd.DataFrame] = []
    for method_source in _discover_method_sources(output_lines_dir):
        try:
            method_frames.append(_load_method_dataframe(method_source, polygons_dir, swath_width_m))
        except click.ClickException:
            pass
    if not method_frames:
        raise click.ClickException(f"No methods found in {output_lines_dir}")
    metrics = pd.concat(method_frames, ignore_index=True)
    metrics = metrics.sort_values("method").reset_index(drop=True)
    return metrics


def _format_report(metrics: pd.DataFrame) -> str:
    notes = [
        "method num_polygons total_area_ha area_perimeter_ratio mean_straight_length_m std_straight_length_m num_turns turns_per_ha target_coverage_pct clean_area_waste_pct",
        metrics.to_string(index=False, float_format=lambda value: f"{value:.4f}"),
    ]
    return "\n".join(notes)


def export_metrics(metrics: pd.DataFrame, output_dir: Path) -> None:
    metrics_dir = output_dir / "metrics"
    metrics_dir.mkdir(parents=True, exist_ok=True)

    metrics.to_csv(metrics_dir / "geometric_metrics.csv", index=False)
    metrics_dir.joinpath("geometric_metrics.md").write_text(
        metrics.to_markdown(index=False), encoding="utf-8"
    )


@click.command()
@click.option(
    "--output-lines-dir",
    type=click.Path(file_okay=False, path_type=Path),
    default=DEFAULT_OUTPUT_LINES_DIR,
)
@click.option(
    "--polygons-dir", type=click.Path(file_okay=False, path_type=Path), default=DEFAULT_POLYGONS_DIR
)
@click.option(
    "--output-dir", type=click.Path(file_okay=False, path_type=Path), default=DEFAULT_OUTPUT_DIR
)
@click.option("--swath-width", type=float, default=2.0)
def cli(output_lines_dir: Path, polygons_dir: Path, output_dir: Path, swath_width: float) -> None:
    metrics = build_geometric_metrics(
        output_lines_dir=output_lines_dir, polygons_dir=polygons_dir, swath_width_m=swath_width
    )
    export_metrics(metrics, output_dir)


if __name__ == "__main__":
    cli()
