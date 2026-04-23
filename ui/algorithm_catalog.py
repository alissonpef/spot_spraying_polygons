from __future__ import annotations

from dataclasses import dataclass

from src.core import SUPPORTED_COVERAGE_METHODS, normalize_coverage_method

PREFERRED_METHOD_ORDER = (
    "mrr",
    "bcd",
    "bp-mops",
    "fixed-grid",
    "quadtree",
    "strip-based",
    "convex-hull",
    "concave-hull",
    "aabb",
    "morph-closing",
    "dbscan-buffer",
)

METHOD_PARAMETER_KEYS: dict[str, tuple[str, ...]] = {
    "fixed-grid": ("grid_cell_size_m", "grid_fill_threshold"),
    "quadtree": ("quadtree_min_cell_size_m", "quadtree_fill_threshold"),
    "concave-hull": ("alpha_shape_radius_m",),
    "strip-based": ("strip_width_m", "strip_fill_threshold"),
    "dbscan-buffer": ("dbscan_min_samples",),
}

METHOD_METADATA: dict[str, tuple[str, str]] = {
    "mrr": (
        "MRR",
        "Gera retângulos rotacionados mínimos e divide apenas quando há ganho operacional claro.",
    ),
    "bcd": (
        "Boustrophedon",
        "Decompõe manchas com reflexos em células mais navegáveis para cobertura sistemática.",
    ),
    "bp-mops": (
        "BP-MOPS",
        "Preenche a área com discos operacionais; útil quando o diâmetro efetivo de aplicação manda no desenho.",
    ),
    "fixed-grid": (
        "Grade Fixa",
        "Aproxima a área com células regulares, priorizando simplicidade e repetibilidade.",
    ),
    "quadtree": (
        "Quadtree",
        "Refina a malha só onde precisa, equilibrando detalhe local e redução de área.",
    ),
    "strip-based": (
        "Faixas",
        "Alinha bandas ao eixo principal da mancha para favorecer passadas longas do drone.",
    ),
    "convex-hull": (
        "Convex Hull",
        "Cria a envoltória convexa da mancha, cobrindo rápido mas com tendência a sobrecobertura.",
    ),
    "concave-hull": (
        "Concave Hull",
        "Segue melhor os vazios e recortes da mancha com uma envoltória adaptativa.",
    ),
    "aabb": (
        "AABB",
        "Usa o retângulo alinhado aos eixos; é o método mais simples e mais conservador.",
    ),
    "morph-closing": (
        "Fechamento Morfológico",
        "Suaviza a mancha com operações morfológicas para reduzir recortes pequenos e ruído.",
    ),
    "dbscan-buffer": (
        "DBSCAN Buffer",
        "Agrupa manchas pela proximidade dos centroides e dissolve os grupos resultantes.",
    ),
}


@dataclass(frozen=True, slots=True)
class AlgorithmOption:
    key: str
    label: str
    description: str


def list_algorithm_options() -> list[AlgorithmOption]:
    supported_methods = {normalize_coverage_method(method) for method in SUPPORTED_COVERAGE_METHODS}
    ordered_methods = [method for method in PREFERRED_METHOD_ORDER if method in supported_methods]
    ordered_methods.extend(sorted(supported_methods.difference(ordered_methods)))
    return [build_algorithm_option(method) for method in ordered_methods]


def build_algorithm_option(method: str) -> AlgorithmOption:
    normalized_method = normalize_coverage_method(method)
    label, description = METHOD_METADATA.get(
        normalized_method,
        (normalized_method.replace("-", " ").title(), "Método suportado pelo motor."),
    )
    return AlgorithmOption(
        key=normalized_method,
        label=label,
        description=description,
    )


def get_algorithm_parameter_keys(method: str) -> tuple[str, ...]:
    return METHOD_PARAMETER_KEYS.get(normalize_coverage_method(method), ())
