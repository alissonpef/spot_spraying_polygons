from shapely import STRtree
from shapely.geometry import Polygon
from shapely.prepared import prep

from src.geo.extraction import extract_and_transform
from src.geo.projection import prepare_projection
from src.geo.spatial_index import query_tree_indices


def count_weeds_per_talhao(
    weeds_metric: list[Polygon],
    talhoes_metric: list[Polygon],
) -> list[int]:
    if not weeds_metric:
        return [0] * len(talhoes_metric)

    tree = STRtree(weeds_metric)
    counts: list[int] = []
    for talhao in talhoes_metric:
        prepared_talhao = prep(talhao)
        idxs = query_tree_indices(tree, talhao)
        counts.append(sum(1 for i in idxs if prepared_talhao.intersects(weeds_metric[i])))
    return counts


def get_talhao_info(
    weeds_geojson: dict,
    talhoes_geojson: dict,
    config: dict | None = None,
) -> list[dict]:
    t2m, t2w = prepare_projection(weeds_geojson, config)

    weeds_m = extract_and_transform(weeds_geojson, t2m)
    talhoes_m = extract_and_transform(talhoes_geojson, t2m)
    weed_counts = count_weeds_per_talhao(weeds_m, talhoes_m)

    info: list[dict] = []
    for i, (talhao, weed_count) in enumerate(zip(talhoes_m, weed_counts)):
        centroid_m = talhao.centroid
        cx, cy = t2w.transform(centroid_m.x, centroid_m.y)
        info.append(
            {
                "id": i,
                "nome": f"Talhão {i + 1}",
                "daninhas": weed_count,
                "area_ha": talhao.area / 10_000,
                "centroid_lat": cy,
                "centroid_lon": cx,
            }
        )

    return info
