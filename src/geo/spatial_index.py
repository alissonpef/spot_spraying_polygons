from __future__ import annotations

from shapely import STRtree
from shapely.geometry.base import BaseGeometry


def query_tree_indices(tree: STRtree, geom: BaseGeometry) -> list[int]:
    result = tree.query(geom)
    if result is None:
        return []
    if hasattr(result, "tolist"):
        result = result.tolist()
    if isinstance(result, int):
        return [int(result)]
    if not isinstance(result, list):
        return [int(idx) for idx in result]
    if not result:
        return []
    if isinstance(result[0], list):
        if len(result) >= 2:
            return [int(idx) for idx in result[1]]
        return []
    return [int(idx) for idx in result]
