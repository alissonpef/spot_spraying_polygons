from __future__ import annotations

import json
import math
from collections.abc import Iterator
from heapq import heappop, heappush
from pathlib import Path
from typing import cast

import click
from pyproj import CRS, Transformer
from shapely.affinity import rotate
from shapely.errors import GEOSException
from shapely.geometry import (
    GeometryCollection,
    LineString,
    MultiLineString,
    Polygon,
    mapping,
    shape,
)
from shapely.geometry.base import BaseGeometry
from shapely.ops import transform as shapely_transform
from shapely.ops import unary_union

from src.geo.geometry import to_polygon_list
from src.io.geojson import load_geojson
from src.io.geojson import save_geojson as write_geojson

try:
    from shapely import make_valid as shapely_make_valid

except ImportError:
    shapely_make_valid = None


XY = tuple[float, float]


class SprayLineUtil:
    _EPSILON = 1e-9

    def generate_lines(
        self,
        polygon: Polygon,
        distance_between: float,
        angle_degrees: float,
    ) -> MultiLineString:

        if distance_between <= 0:
            return MultiLineString([])

        centroid = polygon.centroid

        origin = (centroid.x, centroid.y)

        rotated_polygon = rotate(
            polygon,
            -angle_degrees,
            origin=origin,
            use_radians=False,
        )

        rows = self._build_rows(rotated_polygon, distance_between)

        segments = self._order_rows_zigzag(rows)

        if not segments:
            return MultiLineString([])

        path = self._connect_segments(segments, rotated_polygon)

        if path.is_empty or len(path.coords) < 2:
            return MultiLineString([])

        restored = rotate(path, angle_degrees, origin=origin, use_radians=False)

        if restored.is_empty or len(restored.coords) < 2 or restored.length <= 0:
            return MultiLineString([])

        return MultiLineString([list(restored.coords)])

    def _build_rows(self, polygon: Polygon, distance_between: float) -> list[list[LineString]]:

        min_x, min_y, max_x, max_y = polygon.bounds

        span = math.hypot(max_x - min_x, max_y - min_y)

        rows: list[list[LineString]] = []

        y = min_y

        epsilon = self._EPSILON

        while y <= max_y + epsilon:
            probe = LineString([(min_x - span, y), (max_x + span, y)])

            row_segments = self._extract_lines(probe.intersection(polygon))

            if row_segments:
                rows.append(sorted(row_segments, key=lambda segment: segment.centroid.x))

            y += distance_between

        return rows

    def _order_rows_zigzag(self, rows: list[list[LineString]]) -> list[LineString]:

        ordered: list[LineString] = []

        for row_index, row_segments in enumerate(rows):
            left_to_right = row_index % 2 == 0

            ordered_row = row_segments if left_to_right else list(reversed(row_segments))

            ordered.extend(self._orient_segment(segment, left_to_right) for segment in ordered_row)

        return ordered

    def _orient_segment(self, segment: LineString, left_to_right: bool) -> LineString:

        coords = list(segment.coords)

        if len(coords) < 2:
            return segment

        start = coords[0]

        end = coords[-1]

        should_reverse = False

        if left_to_right:
            should_reverse = (start[0], start[1]) > (end[0], end[1])

        else:
            should_reverse = (start[0], start[1]) < (end[0], end[1])

        if should_reverse:
            return LineString(coords[::-1])

        return segment

    def _connect_segments(self, segments: list[LineString], polygon: Polygon) -> LineString:

        if not segments:
            return LineString([])

        path_coords = self._line_coords_as_xy(segments[0])

        safe_polygon = polygon.buffer(self._EPSILON)

        exterior_coords = [self._as_xy(coord) for coord in list(polygon.exterior.coords)[:-1]]

        base_nodes = self._deduplicate_nodes(exterior_coords)

        base_adjacency = {i: [] for i in range(len(base_nodes))}

        for i in range(len(base_nodes)):
            for j in range(i + 1, len(base_nodes)):
                segment = LineString([base_nodes[i], base_nodes[j]])

                if not safe_polygon.covers(segment):
                    continue

                weight = math.dist(base_nodes[i], base_nodes[j])

                base_adjacency[i].append((j, weight))

                base_adjacency[j].append((i, weight))

        for current in segments[1:]:
            previous_end = path_coords[-1]

            current_start = self._as_xy(current.coords[0])

            connector = self._build_connector(
                previous_end, current_start, polygon, safe_polygon, base_nodes, base_adjacency
            )

            self._append_coords(path_coords, self._line_coords_as_xy(connector))

            self._append_coords(path_coords, self._line_coords_as_xy(current))

        return LineString(path_coords)

    def _append_coords(self, path: list[XY], chunk: list[XY]) -> None:

        if not chunk:
            return

        if not path:
            path.extend(chunk)

            return

        if self._points_close(path[-1], chunk[0]):
            path.extend(chunk[1:])

            return

        path.extend(chunk)

    def _build_connector(
        self,
        start: XY,
        end: XY,
        polygon: Polygon,
        safe_polygon: Polygon,
        base_nodes: list[XY],
        base_adjacency: dict[int, list[tuple[int, float]]],
    ) -> LineString:

        if self._points_close(start, end):
            return LineString([start, end])

        direct = LineString([start, end])

        if safe_polygon.covers(direct):
            return direct

        internal_path = self._shortest_inside_path(
            start, end, polygon, safe_polygon, base_nodes, base_adjacency
        )

        if not internal_path.is_empty and len(internal_path.coords) >= 2:
            return internal_path

        return direct

    def _shortest_inside_path(
        self,
        start: XY,
        end: XY,
        polygon: Polygon,
        safe_polygon: Polygon,
        base_nodes: list[XY],
        base_adjacency: dict[int, list[tuple[int, float]]],
    ) -> LineString:

        nodes = list(base_nodes)

        start_idx = self._find_node_index(nodes, start)

        if start_idx is None:
            nodes.append(start)

            start_idx = len(nodes) - 1

        end_idx = self._find_node_index(nodes, end)

        if end_idx is None:
            nodes.append(end)

            end_idx = len(nodes) - 1

        if start_idx == end_idx:
            return LineString([start, end])

        adjacency = {i: list(neighbors) for i, neighbors in base_adjacency.items()}

        for i in range(len(base_adjacency), len(nodes)):
            adjacency[i] = []

        new_indices = [i for i in range(len(base_adjacency), len(nodes))]

        for new_i in new_indices:
            for j in range(len(nodes)):
                if new_i == j:
                    continue

                segment = LineString([nodes[new_i], nodes[j]])

                if not safe_polygon.covers(segment):
                    continue

                weight = math.dist(nodes[new_i], nodes[j])

                adjacency[new_i].append((j, weight))

                adjacency[j].append((new_i, weight))

        path_indices = self._shortest_path_indices(adjacency, start_idx, end_idx)

        if not path_indices:
            return LineString([start, end])

        ordered_nodes = [nodes[index] for index in path_indices]

        ordered_nodes[0] = start

        ordered_nodes[-1] = end

        return LineString(ordered_nodes)

    def _find_node_index(self, nodes: list[XY], target: XY) -> int | None:

        for index, node in enumerate(nodes):
            if self._points_close(node, target):
                return index

        return None

    def _build_visibility_graph(
        self,
        nodes: list[XY],
        polygon: Polygon,
    ) -> dict[int, list[tuple[int, float]]]:

        safe_polygon = polygon.buffer(self._EPSILON)

        adjacency: dict[int, list[tuple[int, float]]] = {i: [] for i in range(len(nodes))}

        for i in range(len(nodes)):
            for j in range(i + 1, len(nodes)):
                segment = LineString([nodes[i], nodes[j]])

                if not safe_polygon.covers(segment):
                    continue

                weight = math.dist(nodes[i], nodes[j])

                adjacency[i].append((j, weight))

                adjacency[j].append((i, weight))

        return adjacency

    def _shortest_path_indices(
        self,
        adjacency: dict[int, list[tuple[int, float]]],
        start_idx: int,
        end_idx: int,
    ) -> list[int]:

        if not adjacency[start_idx] or not adjacency[end_idx]:
            return []

        distances = [math.inf] * len(adjacency)

        previous: list[int | None] = [None] * len(adjacency)

        distances[start_idx] = 0.0

        heap: list[tuple[float, int]] = [(0.0, start_idx)]

        while heap:
            current_distance, current_idx = heappop(heap)

            if current_distance > distances[current_idx]:
                continue

            if current_idx == end_idx:
                break

            for neighbor_idx, edge_weight in adjacency[current_idx]:
                new_distance = current_distance + edge_weight

                if new_distance >= distances[neighbor_idx]:
                    continue

                distances[neighbor_idx] = new_distance

                previous[neighbor_idx] = current_idx

                heappush(heap, (new_distance, neighbor_idx))

        if math.isinf(distances[end_idx]):
            return []

        ordered_indices: list[int] = []

        cursor: int | None = end_idx

        while cursor is not None:
            ordered_indices.append(cursor)

            cursor = previous[cursor]

        ordered_indices.reverse()

        return ordered_indices

    def _deduplicate_nodes(self, nodes: list[XY], tolerance: float = 1e-9) -> list[XY]:

        deduplicated: list[XY] = []

        for node in nodes:
            if any(self._points_close(node, existing, tolerance) for existing in deduplicated):
                continue

            deduplicated.append(node)

        return deduplicated

    def _extract_lines(self, geometry: BaseGeometry) -> list[LineString]:

        if geometry.is_empty:
            return []

        if isinstance(geometry, LineString):
            return [geometry] if len(geometry.coords) >= 2 else []

        if isinstance(geometry, MultiLineString):
            return [
                segment
                for segment in geometry.geoms
                if not segment.is_empty and len(segment.coords) >= 2 and segment.length > 0
            ]

        if isinstance(geometry, GeometryCollection):
            lines: list[LineString] = []

            for sub_geom in geometry.geoms:
                lines.extend(self._extract_lines(sub_geom))

            return lines

        return []

    def _line_coords_as_xy(self, line: LineString) -> list[XY]:

        return [self._as_xy(coord) for coord in line.coords]

    def _as_xy(self, coord: tuple[float, ...]) -> XY:

        return (float(coord[0]), float(coord[1]))

    def _points_close(
        self,
        first: XY,
        second: XY,
        tolerance: float = 1e-8,
    ) -> bool:

        return abs(first[0] - second[0]) <= tolerance and abs(first[1] - second[1]) <= tolerance


def validate_distance(distance: float) -> None:

    if distance <= 0:
        raise click.BadParameter("Distance must be greater than 0", param_hint="distancia")


def validate_angle(angle: float) -> None:

    if not 0 <= angle < 360:
        raise click.BadParameter("Angle must be between 0 and 360 degrees", param_hint="angulo")


def parse_fields_to_process(fields_raw: str) -> list[int]:

    try:
        fields_to_process = json.loads(fields_raw)

    except json.JSONDecodeError as exc:
        raise click.BadParameter(
            "Formato invalido para fields_to_process. Use [1,2,3].",
            param_hint="fields_to_process",
        ) from exc

    if not isinstance(fields_to_process, list) or not all(
        isinstance(i, int) for i in fields_to_process
    ):
        raise click.BadParameter(
            "fields_to_process deve ser uma lista de inteiros no formato [1,2,3].",
            param_hint="fields_to_process",
        )

    return fields_to_process


def normalize_field_id(value) -> int | None:

    if value is None:
        return None

    if isinstance(value, bool):
        return None

    if isinstance(value, int):
        return value

    if isinstance(value, float):
        if value.is_integer():
            return int(value)

        return None

    if isinstance(value, str):
        stripped = value.strip()

        if not stripped:
            return None

        try:
            float_value = float(stripped)

            if float_value.is_integer():
                return int(float_value)

        except ValueError:
            return None

    return None


def ensure_valid_geometry(geometry: BaseGeometry | None) -> BaseGeometry | None:

    if geometry is None or geometry.is_empty:
        return geometry

    if geometry.is_valid:
        return geometry

    if shapely_make_valid is not None:
        fixed = shapely_make_valid(geometry)

        if fixed is not None and not fixed.is_empty:
            return fixed

    return geometry.buffer(0)


def detect_field_id_column(columns: list[str]) -> str | None:

    candidates = ["Field_id", "field_id", "field_id", "id", "ID"]

    for candidate in candidates:
        if candidate in columns:
            return candidate

    return None


def detect_obstacle_column(columns: list[str]) -> str | None:

    for candidate in ("obstacle", "is_obstacle"):
        if candidate in columns:
            return candidate

    return None


def resolve_source_crs(geojson_data: dict) -> tuple[CRS, bool]:

    crs_data = geojson_data.get("crs")

    if isinstance(crs_data, dict):
        properties = crs_data.get("properties")

        if isinstance(properties, dict):
            name = properties.get("name")

            if isinstance(name, str) and name.strip():
                return CRS.from_user_input(name.strip()), False

    return CRS.from_epsg(4326), True


def load_feature_records(
    geojson_file: Path,
) -> tuple[list[tuple[BaseGeometry, dict]], CRS, bool]:

    geojson_data = load_geojson(geojson_file)

    if not isinstance(geojson_data, dict) or geojson_data.get("type") != "FeatureCollection":
        raise click.ClickException("Empty or invalid GeoJSON file.")

    features = geojson_data.get("features")

    if not isinstance(features, list) or not features:
        raise click.ClickException("Empty or invalid GeoJSON file.")

    source_crs, assumed_wgs84 = resolve_source_crs(geojson_data)

    records: list[tuple[BaseGeometry, dict]] = []

    for feature in features:
        if not isinstance(feature, dict):
            continue

        geometry_data = feature.get("geometry")

        if geometry_data is None:
            continue

        try:
            geom = shape(geometry_data)

        except (TypeError, ValueError, GEOSException):
            continue

        normalized = ensure_valid_geometry(cast(BaseGeometry, geom))

        if normalized is None or normalized.is_empty:
            continue

        properties = feature.get("properties")

        if not isinstance(properties, dict):
            properties = {}

        records.append((normalized, properties))

    if not records:
        raise click.ClickException("No valid geometry found in the GeoJSON.")

    return records, source_crs, assumed_wgs84


def coerce_bool(value) -> bool:

    if isinstance(value, bool):
        return value

    if isinstance(value, str):
        normalized = value.strip().lower()

        if normalized in {"1", "true", "yes", "y"}:
            return True

        if normalized in {"0", "false", "no", "n"}:
            return False

    return bool(value)


def transform_geometry(geometry: BaseGeometry, transformer: Transformer) -> BaseGeometry:

    return shapely_transform(transformer.transform, geometry)


def safe_union(geometries: list[BaseGeometry]) -> BaseGeometry | None:

    valid_geometries = [
        geometry for geometry in geometries if geometry is not None and not geometry.is_empty
    ]

    if not valid_geometries:
        return None

    try:
        merged = unary_union(valid_geometries)

    except GEOSException:
        repaired_geometries = [
            repaired
            for geometry in valid_geometries
            if (repaired := ensure_valid_geometry(geometry)) is not None and not repaired.is_empty
        ]

        if not repaired_geometries:
            return None

        try:
            merged = unary_union(repaired_geometries)

        except GEOSException:
            merged = GeometryCollection(repaired_geometries)

    return ensure_valid_geometry(cast(BaseGeometry, merged))


def infer_utm_epsg(geometry_wgs84: BaseGeometry) -> int:

    centroid = geometry_wgs84.centroid

    lon, lat = centroid.x, centroid.y

    if lon < -180 or lon > 180 or lat < -90 or lat > 90:
        raise click.ClickException(f"Invalid centroid for UTM calculation: lon={lon}, lat={lat}")

    zone = int((lon + 180) // 6) + 1

    zone = max(1, min(60, zone))

    return (32600 + zone) if lat >= 0 else (32700 + zone)


def iter_line_strings(geometry: BaseGeometry) -> Iterator[LineString]:

    if geometry is None or geometry.is_empty:
        return

    if isinstance(geometry, LineString):
        yield geometry

        return

    if isinstance(geometry, MultiLineString):
        for geom in geometry.geoms:
            if not geom.is_empty:
                yield geom

        return

    if isinstance(geometry, GeometryCollection):
        for geom in geometry.geoms:
            yield from iter_line_strings(geom)


def generate_spray_route_lines(
    geometry: BaseGeometry,
    distance_between_lines: float,
    angle_degrees: float,
) -> list[LineString]:

    util = SprayLineUtil()

    route_lines: list[LineString] = []

    for polygon in to_polygon_list(geometry):
        multiline = util.generate_lines(polygon, distance_between_lines, angle_degrees)

        route_lines.extend(iter_line_strings(multiline))

    return route_lines


def reproject_lines(
    lines: list[LineString],
    source_crs,
    target_crs,
) -> list[LineString]:

    if not lines:
        return []

    transformer = Transformer.from_crs(source_crs, target_crs, always_xy=True)

    reprojected_lines: list[LineString] = []

    for geometry in lines:
        reprojected_geometry = transform_geometry(geometry, transformer)

        reprojected_lines.extend(iter_line_strings(reprojected_geometry))

    return reprojected_lines


def save_geojson(
    features: list[dict],
    output_file: Path,
) -> None:

    payload = {"type": "FeatureCollection", "features": features}

    write_geojson(payload, output_file)


def append_line_features(
    target_features: list[dict],
    lines: list[LineString],
    field_id: int,
) -> None:

    for line in lines:
        target_features.append(
            {
                "type": "Feature",
                "geometry": mapping(line),
                "properties": {
                    "line_type": "spray",
                    "field_id": field_id,
                },
            }
        )


def generate_spray_lines(
    geojson_file: Path,
    distance_between_lines: float,
    angle: float,
    output_dir: Path,
    fields_to_process: list[int],
) -> None:

    records, source_crs, assumed_wgs84 = load_feature_records(geojson_file)

    if assumed_wgs84:
        click.echo("!!!CLI WARNING!!!\nCRS not specified in the file. Assuming EPSG:4326.")

    property_columns = sorted({key for _, properties in records for key in properties})

    id_column = detect_field_id_column(property_columns)

    obstacle_column = detect_obstacle_column(property_columns)

    field_records: list[tuple[BaseGeometry, dict, int | None]] = []

    obstacle_records: list[tuple[BaseGeometry, dict, int | None]] = []

    for geometry, properties in records:
        normalized_id = normalize_field_id(properties.get(id_column))

        record = (geometry, properties, normalized_id)

        if obstacle_column is not None and coerce_bool(properties.get(obstacle_column, False)):
            obstacle_records.append(record)

        else:
            field_records.append(record)

    available_ids = sorted(
        {int(field_id) for _, _, field_id in field_records if field_id is not None}
    )

    fallback_single_group = False

    if not available_ids and not fields_to_process:
        if not field_records:
            raise click.ClickException("No valid field geometry was found in the GeoJSON.")

        fallback_single_group = True

        valid_ids = [0]

        invalid_ids = []

        click.echo(
            "!!!CLI WARNING!!!\n"
            "No usable field ID was found. Processing the entire file as a single group."
        )

    elif not fields_to_process:
        valid_ids = available_ids

        invalid_ids = []

    else:
        available_ids_set = set(available_ids)

        valid_ids = [field_id for field_id in fields_to_process if field_id in available_ids_set]

        invalid_ids = [
            field_id for field_id in fields_to_process if field_id not in available_ids_set
        ]

    if invalid_ids:
        click.echo(
            "!!!CLI WARNING!!!\n"
            f"The following IDs do not correspond to any polygon in the GeoJSON: {invalid_ids}"
        )

    obstacles = sorted(
        {int(field_id) for _, _, field_id in obstacle_records if field_id is not None}
    )

    click.echo(f"Obstacles found in the file: {obstacles}")

    if not valid_ids:
        raise click.ClickException(
            "No valid ID to process. Check the provided IDs and the GeoJSON file."
        )

    output_features: list[dict] = []

    processed_count = 0

    for feature_id in valid_ids:
        source_field_geometries = (
            [geometry for geometry, _, _ in field_records]
            if fallback_single_group
            else [geometry for geometry, _, field_id in field_records if field_id == feature_id]
        )

        if not source_field_geometries:
            continue

        source_field_geometry = safe_union(source_field_geometries)

        if source_field_geometry is None or source_field_geometry.is_empty:
            continue

        if source_field_geometry.geom_type not in {"Polygon", "MultiPolygon"}:
            click.echo(f"!!!CLI WARNING!!!\nPolygon ID {feature_id} is not polygonal. Ignoring.")

            continue

        source_to_wgs84 = Transformer.from_crs(source_crs, 4326, always_xy=True)

        source_field_geometry_wgs84 = transform_geometry(
            source_field_geometry,
            source_to_wgs84,
        )

        target_epsg = infer_utm_epsg(source_field_geometry_wgs84)

        source_to_target = Transformer.from_crs(source_crs, target_epsg, always_xy=True)

        projected_field_records = [
            (transform_geometry(geometry, source_to_target), properties, field_id)
            for geometry, properties, field_id in field_records
        ]

        projected_obstacle_records = [
            (transform_geometry(geometry, source_to_target), properties, field_id)
            for geometry, properties, field_id in obstacle_records
        ]

        field_geometry = safe_union(
            [
                geometry
                for geometry, _, field_id in projected_field_records
                if fallback_single_group or field_id == feature_id
            ]
        )

        if field_geometry is None or field_geometry.is_empty:
            continue

        obstacle_ids_inside: list[int] = []

        obstacle_geometries_inside: list[BaseGeometry] = []

        for obstacle_geometry, _, obstacle_id in projected_obstacle_records:
            if obstacle_geometry is None or obstacle_geometry.is_empty:
                continue

            if field_geometry.intersects(obstacle_geometry):
                obstacle_geometries_inside.append(obstacle_geometry)

                if obstacle_id is not None:
                    obstacle_ids_inside.append(obstacle_id)

        click.echo(f"Obstacles inside polygon ID {feature_id}: {sorted(set(obstacle_ids_inside))}")

        cropped_polygon = field_geometry

        if obstacle_geometries_inside:
            cropped_polygon = ensure_valid_geometry(
                field_geometry.difference(
                    safe_union(obstacle_geometries_inside) or GeometryCollection()
                )
            )

        if cropped_polygon is None or cropped_polygon.is_empty:
            click.echo(
                f"!!!CLI WARNING!!!\nPolygon ID {feature_id} became empty after cropping obstacles."
            )

            continue

        spray_lines_projected = generate_spray_route_lines(
            cropped_polygon,
            distance_between_lines,
            angle,
        )

        if not spray_lines_projected:
            click.echo(
                f"!!!CLI WARNING!!!\nNo spraying lines were generated for polygon ID {feature_id}."
            )

            continue

        spray_lines_source = reproject_lines(
            spray_lines_projected,
            source_crs=target_epsg,
            target_crs=source_crs,
        )

        append_line_features(output_features, spray_lines_source, feature_id)

        click.echo(f"Spraying lines successfully generated for polygon ID {feature_id}!")

        processed_count += 1

    if processed_count == 0:
        raise click.ClickException(
            "No lines were processed. Check the provided IDs and the GeoJSON file."
        )

    output_file = output_dir / f"{geojson_file.stem}.geojson"

    save_geojson(output_features, output_file)


@click.command(context_settings={"help_option_names": ["-h", "--help"]})
@click.argument("geojson_file", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.argument("distance", type=float)
@click.argument("angle", type=float)
@click.argument("fields_to_process", type=str)
@click.option(
    "--output-dir",
    type=click.Path(file_okay=False, path_type=Path),
    default=Path("data/output/lines"),
    help="Directory to save the generated spraying lines.",
)
def cli(
    geojson_file: Path,
    distance: float,
    angle: float,
    fields_to_process: str,
    output_dir: Path,
) -> None:

    validate_distance(distance)

    validate_angle(angle)

    parsed_fields = parse_fields_to_process(fields_to_process)

    output_dir.mkdir(parents=True, exist_ok=True)

    try:
        generate_spray_lines(
            geojson_file=geojson_file,
            distance_between_lines=distance,
            angle=angle,
            output_dir=output_dir,
            fields_to_process=parsed_fields,
        )

    except click.ClickException:
        raise

    except Exception as exc:
        raise click.ClickException(f"Error generating spraying lines: {exc}") from exc


@click.command(context_settings={"help_option_names": ["-h", "--help"]})
@click.argument("input_dir", type=click.Path(exists=True, file_okay=False, path_type=Path))
@click.argument("distance", type=float)
@click.argument("angle", type=float)
@click.option(
    "--output-dir",
    type=click.Path(file_okay=False, path_type=Path),
    default=Path("data/output/lines"),
    help="Directory to save the generated spraying lines.",
)
@click.option(
    "--recursive/--no-recursive",
    default=False,
    help="Search for .geojson files recursively inside input_dir.",
)
def batch(
    input_dir: Path,
    distance: float,
    angle: float,
    output_dir: Path,
    recursive: bool,
) -> None:

    validate_distance(distance)

    validate_angle(angle)

    output_dir.mkdir(parents=True, exist_ok=True)

    geojson_iterable = input_dir.rglob("*.geojson") if recursive else input_dir.glob("*.geojson")

    processed_any = False

    for geojson_file in sorted(path for path in geojson_iterable if path.is_file()):
        try:
            generate_spray_lines(
                geojson_file=geojson_file,
                distance_between_lines=distance,
                angle=angle,
                output_dir=output_dir,
                fields_to_process=[],
            )

            processed_any = True

        except click.ClickException as exc:
            click.echo(
                f"!!!CLI WARNING!!!\nFile {geojson_file.relative_to(input_dir)} ignored: {exc}"
            )

        except Exception as exc:
            click.echo(
                f"!!!CLI WARNING!!!\nFile {geojson_file.relative_to(input_dir)} ignored: {exc}"
            )

    if not processed_any:
        raise click.ClickException("No GeoJSON file was processed.")


if __name__ == "__main__":
    cli()
