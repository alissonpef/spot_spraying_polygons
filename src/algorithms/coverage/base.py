from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence
from dataclasses import dataclass

from shapely.geometry import Polygon

from src.core.config import AlgorithmConfig


@dataclass(frozen=True, slots=True)
class CoverageContext:
    config: AlgorithmConfig
    buffer_quad_segs: int
    min_polygons_to_split: int = 2


class CoverageStrategy(ABC):
    method_name: str = ""

    @abstractmethod
    def generate(self, polygons: Sequence[Polygon], context: CoverageContext) -> list[Polygon]:
        raise NotImplementedError
