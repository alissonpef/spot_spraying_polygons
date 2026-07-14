from shapely import STRtree
from shapely.geometry import Polygon
from shapely.prepared import prep

from src.geo.extraction import extract_and_transform
from src.geo.projection import prepare_projection
from src.geo.spatial_index import query_tree_indices


def count_weeds_per_field(
    weeds_metric: list[Polygon],
    fields_metric: list[Polygon],
) -> list[int]:

    if not weeds_metric:
        return [0] * len(fields_metric)

    tree = STRtree(weeds_metric)

    counts: list[int] = []

    for field in fields_metric:
        prepared_field = prep(field)

        idxs = query_tree_indices(tree, field)

        counts.append(sum(1 for i in idxs if prepared_field.intersects(weeds_metric[i])))

    return counts


def get_field_info(
    weeds_geojson: dict,
    fields_geojson: dict,
    config: dict | None = None,
) -> list[dict]:

    t2m, t2w = prepare_projection(weeds_geojson, config)

    weeds_m = extract_and_transform(weeds_geojson, t2m)

    fields_m = extract_and_transform(fields_geojson, t2m)

    weed_counts = count_weeds_per_field(weeds_m, fields_m)

    info: list[dict] = []

    for i, (field, weed_count) in enumerate(zip(fields_m, weed_counts, strict=False)):
        centroid_m = field.centroid

        cx, cy = t2w.transform(centroid_m.x, centroid_m.y)

        info.append(
            {
                "id": i,
                "nome": f"Field {i + 1}",
                "weeds": weed_count,
                "area_ha": field.area / 10_000,
                "centroid_lat": cy,
                "centroid_lon": cx,
            }
        )

    return info
