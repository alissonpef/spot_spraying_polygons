from __future__ import annotations

from collections import deque
from collections.abc import Sequence

from shapely import STRtree
from shapely.geometry import Point, Polygon

from src.algorithms.coverage.base import CoverageContext, CoverageStrategy
from src.geo.geometry import dissolve_polygons, to_polygon_list
from src.geo.spatial_index import query_tree_indices


class DbscanBufferCoverageStrategy(CoverageStrategy):
    method_name = "dbscan-buffer"

    def generate(self, polygons: Sequence[Polygon], context: CoverageContext) -> list[Polygon]:
        valid = [polygon for polygon in polygons if not polygon.is_empty and polygon.area > 0]
        if not valid:
            return []

        if len(valid) == 1 or context.config.merge_distance_m <= 0:
            return to_polygon_list(dissolve_polygons(valid, fix_invalid=context.config.fix_invalid_geometries))

        points = [polygon.centroid for polygon in valid]
        tree = STRtree(points)
        visited = [False] * len(points)
        assigned = [False] * len(points)
        clusters: list[list[int]] = []

        for index in range(len(points)):
            if visited[index]:
                continue
            visited[index] = True

            neighbors = self._region_query_indices(points, tree, index, context.config.merge_distance_m)
            if len(neighbors) < max(1, context.config.dbscan_min_samples):
                continue

            cluster: list[int] = []
            cluster_seen: set[int] = set()
            queue = deque(neighbors)

            while queue:
                neighbor_index = queue.popleft()
                if neighbor_index in cluster_seen:
                    continue
                cluster_seen.add(neighbor_index)

                if not visited[neighbor_index]:
                    visited[neighbor_index] = True
                    neighbor_neighbors = self._region_query_indices(
                        points,
                        tree,
                        neighbor_index,
                        context.config.merge_distance_m,
                    )
                    if len(neighbor_neighbors) >= max(1, context.config.dbscan_min_samples):
                        queue.extend(neighbor_neighbors)

                if not assigned[neighbor_index]:
                    assigned[neighbor_index] = True
                    cluster.append(neighbor_index)

            if cluster:
                clusters.append(cluster)

        for index in range(len(points)):
            if not assigned[index]:
                clusters.append([index])

        outputs: list[Polygon] = []
        for cluster in clusters:
            dissolved = dissolve_polygons([valid[index] for index in cluster], fix_invalid=context.config.fix_invalid_geometries)
            outputs.extend(to_polygon_list(dissolved))

        return outputs

    @staticmethod
    def _region_query_indices(
        points: list[Point],
        tree: STRtree,
        index: int,
        eps_m: float,
    ) -> list[int]:
        if eps_m <= 0:
            return [index]

        candidate_indices = query_tree_indices(tree, points[index].buffer(eps_m))
        neighbors: list[int] = []
        for candidate_index in candidate_indices:
            neighbor_index = int(candidate_index)
            if points[index].distance(points[neighbor_index]) <= eps_m:
                neighbors.append(neighbor_index)
        return neighbors
