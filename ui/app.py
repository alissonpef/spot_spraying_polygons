import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

import streamlit as st
import streamlit.components.v1 as components
from shapely.errors import GEOSException, TopologicalError

from src.core import AlgorithmConfig, normalize_coverage_method
from src.io import empty_feature_collection
from src.pipeline import generate_catacao_per_talhao
from ui.algorithm_catalog import get_algorithm_parameter_keys, list_algorithm_options
from ui.helpers import get_talhao_info
from ui.map_renderer import render_map
from ui.theme import GLOBAL_STYLES, MAP_SIZES, TALHAO_COLORS, render_sidebar_header

st.set_page_config(
    page_title="Catação · GlobalDrones",
    page_icon="🌾",
    layout="wide",
    initial_sidebar_state="expanded",
)
# Safe: styles are static assets controlled by the application, not user-provided input.
st.markdown(GLOBAL_STYLES, unsafe_allow_html=True)

ROOT_DIR = Path(__file__).parent.parent
# Prefer the repository `data/input` directory for sample files
INPUT_DATA_DIR = ROOT_DIR / "data" / "input"


def _has_sample_files(data_dir: Path) -> bool:
    return (data_dir / "talhoes.geojson").exists() and any(data_dir.glob("daninha*.geojson"))


if _has_sample_files(INPUT_DATA_DIR):
    DATA_DIR = INPUT_DATA_DIR
else:
    # Fallback to top-level `data` if `data/input` is not present
    FALLBACK_DATA_DIR = ROOT_DIR / "data"
    DATA_DIR = FALLBACK_DATA_DIR if FALLBACK_DATA_DIR.exists() else INPUT_DATA_DIR
EMPTY_FC: dict = empty_feature_collection()
MAX_GEOJSON_MB = 200


def _validate_feature_collection(data: Any, label: str) -> dict:
    if not isinstance(data, dict):
        raise ValueError(f"{label}: JSON raiz inválido.")
    if data.get("type") != "FeatureCollection":
        raise ValueError(f"{label}: GeoJSON inválido (type deve ser 'FeatureCollection').")
    if not isinstance(data.get("features"), list):
        raise ValueError(f"{label}: GeoJSON inválido (features deve ser uma lista).")
    return data


def _ensure_load_cache() -> None:
    if "geojson_load_cache" not in st.session_state:
        st.session_state.geojson_load_cache = {}


def _key_for_source(source) -> str | None:
    if source is None:
        return None
    if hasattr(source, "read"):
        file_id = getattr(source, "file_id", None)
        if file_id:
            return f"upload:{file_id}"
        name = getattr(source, "name", "uploaded")
        size = getattr(source, "size", "na")
        return f"upload:{name}:{size}"
    p = Path(source)
    if not p.exists():
        return None
    stat = p.stat()
    return f"path:{p.resolve()}:{stat.st_mtime_ns}:{stat.st_size}"


def _load_cached(source, label: str) -> dict | None:
    if source is None:
        return None
    _ensure_load_cache()
    cache = st.session_state.geojson_load_cache
    cache_key = _key_for_source(source)
    if cache_key and cache_key in cache:
        return cache[cache_key]

    if hasattr(source, "read"):
        upload_size = getattr(source, "size", None)
        if isinstance(upload_size, int):
            size_mb = upload_size / (1024 * 1024)
            if size_mb > MAX_GEOJSON_MB:
                raise ValueError(f"{label}: arquivo muito grande ({size_mb:.1f} MB).")

        content = source.read()
        if isinstance(content, bytes):
            try:
                content = content.decode("utf-8")
            except UnicodeDecodeError as exc:
                raise ValueError(f"{label}: encoding inválido. Use UTF-8.") from exc
        if hasattr(source, "seek"):
            source.seek(0)
    else:
        p = Path(source)
        if not p.exists():
            return None
        size_mb = p.stat().st_size / (1024 * 1024)
        if size_mb > MAX_GEOJSON_MB:
            raise ValueError(f"{label}: arquivo muito grande ({size_mb:.1f} MB).")
        try:
            content = p.read_text("utf-8")
        except UnicodeDecodeError as exc:
            raise ValueError(f"{label}: encoding inválido. Use UTF-8.") from exc

    try:
        parsed = json.loads(content)
    except json.JSONDecodeError as exc:
        raise ValueError(f"{label}: JSON inválido: {exc.msg}")

    validated = _validate_feature_collection(parsed, label)
    if cache_key:
        cache[cache_key] = validated
    return validated


def _load_or_stop(source, label: str) -> dict | None:
    try:
        return _load_cached(source, label)
    except ValueError as exc:
        st.error(f"Erro ao carregar {label}: {exc}")
        st.stop()


def _merge_fcs(items: list[dict | None]) -> dict:
    feats: list[dict] = []
    for fc in items:
        if fc:
            feats.extend(fc.get("features", []))
    return {"type": "FeatureCollection", "features": feats}


def _split_talhoes_and_embedded_obstacles(fc: dict | None) -> tuple[dict, dict]:
    if not fc:
        return EMPTY_FC, EMPTY_FC

    talhoes_features: list[dict] = []
    obstacle_features: list[dict] = []

    for feat in fc.get("features", []):
        props = feat.get("properties", {}) if isinstance(feat, dict) else {}
        raw_obstacle = props.get("obstacle", False)
        is_obstacle = raw_obstacle is True or (
            isinstance(raw_obstacle, str) and raw_obstacle.strip().lower() in {"1", "true", "yes"}
        )
        if is_obstacle:
            obstacle_features.append(feat)
        else:
            talhoes_features.append(feat)

    return (
        {"type": "FeatureCollection", "features": talhoes_features},
        {"type": "FeatureCollection", "features": obstacle_features},
    )


def _sync_param(
    main_key: str,
    source_key: str,
    other_key: str,
    step: float = 0.0,
    min_val: float = 0.0,
    max_val: float = float("inf"),
) -> None:
    val = st.session_state.get(source_key)
    if val is None:
        return
    val = float(val)
    val = max(min_val, min(max_val, val))
    if step > 0:
        val = round((val - min_val) / step) * step + min_val
        val = round(val, 10)
        val = max(min_val, min(max_val, val))
    st.session_state[main_key] = val
    st.session_state[other_key] = val


def _param_slider_input(
    label: str,
    min_val: float,
    max_val: float,
    default: float,
    step: float,
    key: str,
    help_text: str = "",
) -> float:
    if key not in st.session_state:
        st.session_state[key] = default
    else:
        val = float(st.session_state[key])
        val = max(min_val, min(max_val, val))
        if step > 0:
            val = round((val - min_val) / step) * step + min_val
            val = round(val, 10)
            val = max(min_val, min(max_val, val))
        st.session_state[key] = val

    s_key = f"__sl_{key}"
    n_key = f"__ni_{key}"
    col_s, col_n = st.columns([3, 1.2])
    with col_s:
        st.slider(
            label,
            min_value=min_val,
            max_value=max_val,
            value=st.session_state[key],
            step=step,
            help=help_text,
            key=s_key,
            on_change=_sync_param,
            args=(key, s_key, n_key, step, min_val, max_val),
        )
    with col_n:
        st.number_input(
            label,
            min_value=min_val,
            max_value=max_val,
            value=st.session_state[key],
            step=step,
            label_visibility="collapsed",
            key=n_key,
            on_change=_sync_param,
            args=(key, n_key, s_key, step, min_val, max_val),
        )
    return st.session_state[key]


def _fhash(feat: dict) -> str:
    raw = json.dumps(feat["geometry"], sort_keys=True)
    return hashlib.md5(raw.encode()).hexdigest()[:10]


def _poly_label(feat: dict) -> str:
    p = feat.get("properties", {})
    tid = p.get("talhao_id", 0)
    pid = p.get("_pid", 0)
    area = p.get("area_m2", 0)
    return f"T{tid + 1} · P{pid + 1} — {area:.0f} m² ({area / 10_000:.4f} ha)"


def _parse_streamlit_cli_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--daninhas", "-d", action="append", default=[])
    parser.add_argument("--talhoes", "-t", action="append", default=[])
    parser.add_argument("--obstaculos", "-o", action="append", default=[])
    args, _ = parser.parse_known_args(sys.argv[1:])
    return args


def _normalize_cli_paths(values: list[str]) -> list[Path]:
    paths: list[Path] = []
    for value in values:
        for part in value.split(","):
            candidate = part.strip()
            if candidate:
                paths.append(Path(candidate))
    return paths


def init_session_state():
    defaults = {
        "resultado": None,
        "params_usados": None,
        "removed_catacao": set(),
        "removed_daninhas": set(),
        "result_version": 0,
    }
    for key, val in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = val


def _load_default_sources(args: argparse.Namespace) -> tuple[dict, dict, dict]:
    cli_d_files = _normalize_cli_paths(args.daninhas)
    cli_t_files = _normalize_cli_paths(args.talhoes)
    cli_o_files = _normalize_cli_paths(args.obstaculos)
    default_obstacles_file = DATA_DIR / "obstaculos.geojson"

    d_files = cli_d_files if cli_d_files else sorted(DATA_DIR.glob("daninha*.geojson"))
    t_file = cli_t_files[0] if cli_t_files else (DATA_DIR / "talhoes.geojson")

    daninhas_gj_raw = _merge_fcs([_load_or_stop(f, Path(f).name) for f in d_files if Path(f).exists()])
    talhoes_raw = _load_or_stop(t_file, Path(t_file).name) or EMPTY_FC
    talhoes_gj, embedded_obstacles = _split_talhoes_and_embedded_obstacles(talhoes_raw)

    obstacle_sources: list[Path] = []
    if cli_o_files:
        obstacle_sources = [f for f in cli_o_files if Path(f).exists()]
    elif default_obstacles_file.exists():
        obstacle_sources = [default_obstacles_file]

    external_obstacles = (
        _merge_fcs([_load_or_stop(f, Path(f).name) for f in obstacle_sources if Path(f).exists()])
        if obstacle_sources
        else EMPTY_FC
    )
    obstaculos_gj = _merge_fcs([external_obstacles, embedded_obstacles])
    return daninhas_gj_raw, talhoes_gj, obstaculos_gj


def _load_uploaded_sources() -> tuple[dict, dict, dict]:
    up_d = st.file_uploader("Daninhas", type=["geojson"], accept_multiple_files=True)
    up_t = st.file_uploader("Talhões", type=["geojson"])
    up_o = st.file_uploader("Obstáculos (opcional)", type=["geojson"])

    daninhas_gj_raw = (
        _merge_fcs([_load_or_stop(f, getattr(f, "name", "upload")) for f in up_d]) if up_d else EMPTY_FC
    )
    talhoes_raw = (_load_or_stop(up_t, getattr(up_t, "name", "upload")) or EMPTY_FC) if up_t else EMPTY_FC
    talhoes_gj, embedded_obstacles = _split_talhoes_and_embedded_obstacles(talhoes_raw)

    external_obstacles = (
        _load_or_stop(up_o, getattr(up_o, "name", "upload")) or EMPTY_FC if up_o else EMPTY_FC
    )
    obstaculos_gj = _merge_fcs([external_obstacles, embedded_obstacles])
    return daninhas_gj_raw, talhoes_gj, obstaculos_gj


def _filter_removed_weeds(daninhas_gj_raw: dict) -> dict:
    if not st.session_state.removed_daninhas:
        return daninhas_gj_raw
    return {
        "type": "FeatureCollection",
        "features": [
            feature
            for feature in daninhas_gj_raw.get("features", [])
            if _fhash(feature) not in st.session_state.removed_daninhas
        ],
    }


def _render_parameter_controls() -> tuple[dict, float]:
    cfg = AlgorithmConfig()
    algorithm_options = list_algorithm_options()
    option_map = {option.key: option for option in algorithm_options}
    method_options = list(option_map)
    cfg_method = normalize_coverage_method(cfg.coverage_method)
    if cfg_method not in option_map:
        cfg_method = method_options[0]

    buffer_m = _param_slider_input("Buffer da daninha (m)", 0.0, 25.0, cfg.weed_buffer_m, 0.5, "p_buf")
    merge_m = _param_slider_input("Agrupamento (m)", 0.0, 250.0, cfg.merge_distance_m, 1.0, "p_mrg")
    # obstacle distance before choosing coverage algorithm (UX change requested)
    obs_buffer = _param_slider_input(
        "Dist. obstáculos (m)", 0.0, 25.0, cfg.obstacle_safety_buffer_m, 0.5, "p_obs"
    )

    coverage_method = st.selectbox(
        "Algoritmo de cobertura",
        options=method_options,
        index=method_options.index(cfg_method),
        format_func=lambda method: option_map[method].label,
        help="A lista é montada a partir dos métodos suportados pelo motor, sem depender de uma enumeração fixa na UI.",
    )
    selected_option = option_map[coverage_method]
    st.caption(selected_option.description)

    area_min = st.number_input(
        "Área mínima (m²)",
        min_value=0.0,
        max_value=50000.0,
        value=cfg.min_polygon_area_m2,
        step=100.0,
    )

    with st.expander("⚙️ Avançado", expanded=False):
        fill_ratio = _param_slider_input(
            "Razão min. preenchimento",
            0.05,
            0.95,
            cfg.rectangle_min_fill_ratio,
            0.05,
            "p_fill",
        )
        max_depth = st.number_input(
            "Prof. máxima de divisão",
            min_value=1,
            max_value=12,
            value=cfg.rectangle_max_depth,
            step=1,
        )
        max_sides = st.number_input(
            "Máx. lados (buffers)",
            min_value=4,
            max_value=256,
            value=cfg.max_polygon_sides,
            step=4,
            help=(
                "Controla quantos lados os arcos de buffer podem usar. "
                "Valores menores deixam o contorno mais limpo; valores maiores mais suave."
            ),
        )
        neg_buffer = _param_slider_input("Buffer negativo (m)", 0.0, 5.0, cfg.negative_buffer_m, 0.1, "p_neg")

        method_specific_keys = set(get_algorithm_parameter_keys(coverage_method))
        if "grid_cell_size_m" in method_specific_keys:
            st.markdown("###### Grade Fixa")
            grid_cell_size_m = _param_slider_input(
                "Tamanho da célula (m)",
                0.5,
                30.0,
                cfg.grid_cell_size_m,
                0.5,
                "p_grid_cell",
            )
            grid_fill_threshold = _param_slider_input(
                "Preenchimento mínimo da célula",
                0.05,
                1.0,
                cfg.grid_fill_threshold,
                0.05,
                "p_grid_fill",
            )
        else:
            grid_cell_size_m = cfg.grid_cell_size_m
            grid_fill_threshold = cfg.grid_fill_threshold

        if "quadtree_min_cell_size_m" in method_specific_keys:
            st.markdown("###### Quadtree")
            quadtree_min_cell_size_m = _param_slider_input(
                "Menor célula (m)",
                0.5,
                30.0,
                cfg.quadtree_min_cell_size_m,
                0.5,
                "p_qt_min_cell",
            )
            quadtree_fill_threshold = _param_slider_input(
                "Preenchimento mínimo da célula",
                0.05,
                1.0,
                cfg.quadtree_fill_threshold,
                0.05,
                "p_qt_fill",
            )
        else:
            quadtree_min_cell_size_m = cfg.quadtree_min_cell_size_m
            quadtree_fill_threshold = cfg.quadtree_fill_threshold

        if "alpha_shape_radius_m" in method_specific_keys:
            st.markdown("###### Concave Hull")
            alpha_shape_radius_m = _param_slider_input(
                "Raio alfa (m)",
                1.0,
                100.0,
                cfg.alpha_shape_radius_m,
                1.0,
                "p_alpha_radius",
            )
        else:
            alpha_shape_radius_m = cfg.alpha_shape_radius_m

        if "strip_width_m" in method_specific_keys:
            st.markdown("###### Faixas")
            strip_width_m = _param_slider_input(
                "Largura da faixa (m)",
                0.5,
                30.0,
                cfg.strip_width_m,
                0.5,
                "p_strip_width",
            )
            strip_fill_threshold = _param_slider_input(
                "Preenchimento mínimo da faixa",
                0.05,
                1.0,
                cfg.strip_fill_threshold,
                0.05,
                "p_strip_fill",
            )
        else:
            strip_width_m = cfg.strip_width_m
            strip_fill_threshold = cfg.strip_fill_threshold

        if "dbscan_min_samples" in method_specific_keys:
            st.markdown("###### DBSCAN")
            dbscan_min_samples = st.number_input(
                "Mínimo de amostras",
                min_value=1,
                max_value=20,
                value=cfg.dbscan_min_samples,
                step=1,
            )
        else:
            dbscan_min_samples = cfg.dbscan_min_samples

        if coverage_method == "bp-mops":
            st.caption("No BP-MOPS, o buffer da daninha também define o raio operacional dos discos.")
        elif coverage_method == "morph-closing":
            st.caption("No fechamento morfológico, o buffer da daninha atua como raio de suavização.")

    algo_config = {
        "weed_buffer_m": buffer_m,
        "merge_distance_m": merge_m,
        "obstacle_safety_buffer_m": obs_buffer,
        "negative_buffer_m": neg_buffer,
        "min_polygon_area_m2": area_min,
        "fix_invalid_geometries": True,
        "rectangle_min_fill_ratio": float(fill_ratio),
        "rectangle_max_depth": int(max_depth),
        "max_polygon_sides": int(max_sides),
        "coverage_method": coverage_method,
        "grid_cell_size_m": float(grid_cell_size_m),
        "grid_fill_threshold": float(grid_fill_threshold),
        "quadtree_min_cell_size_m": float(quadtree_min_cell_size_m),
        "quadtree_fill_threshold": float(quadtree_fill_threshold),
        "alpha_shape_radius_m": float(alpha_shape_radius_m),
        "strip_width_m": float(strip_width_m),
        "strip_fill_threshold": float(strip_fill_threshold),
        "dbscan_min_samples": int(dbscan_min_samples),
    }
    return algo_config, float(area_min)


def render_sidebar() -> tuple:
    with st.sidebar:
        render_sidebar_header()
        st.divider()
        st.markdown("##### 📁 Dados de entrada")

        args = _parse_streamlit_cli_args()
        usar_padrao = st.toggle("Usar arquivos de exemplo", value=True)

        if usar_padrao:
            daninhas_gj_raw, talhoes_gj, obstaculos_gj = _load_default_sources(args)
        else:
            daninhas_gj_raw, talhoes_gj, obstaculos_gj = _load_uploaded_sources()

        n_obstacles = len(obstaculos_gj.get("features", []))
        st.caption(f"Obstáculos carregados: {n_obstacles}")

        daninhas_gj = _filter_removed_weeds(daninhas_gj_raw)

        st.divider()
        st.markdown("##### 🔧 Parâmetros")
        algo_config, area_min = _render_parameter_controls()

        st.divider()
        st.markdown("##### 🗺️ Visualização")
        map_size = st.selectbox("Tamanho do mapa", options=list(MAP_SIZES.keys()), index=1)
        map_height = MAP_SIZES[map_size]

        st.divider()
        gerar_btn = st.button("🚀 Gerar Polígonos", type="primary", use_container_width=True)

        return daninhas_gj, talhoes_gj, obstaculos_gj, algo_config, gerar_btn, map_height, area_min


def process_generation(daninhas_gj: dict, talhoes_gj: dict, obstaculos_gj: dict, config: dict):
    if not daninhas_gj.get("features") or not talhoes_gj.get("features"):
        st.toast("⚠️ Carregue os arquivos de daninhas e talhões.", icon="⚠️")
        return

    with st.spinner("Processando talhões…"):
        try:
            result = generate_catacao_per_talhao(
                weeds_geojson=daninhas_gj,
                obstacles_geojson=obstaculos_gj,
                talhoes_geojson=talhoes_gj,
                config=config,
            )
            counters: dict[int, int] = {}
            for feat in result.get("features", []):
                feat["properties"]["_hash"] = _fhash(feat)
                tid = feat["properties"].get("talhao_id", 0)
                pid = counters.get(tid, 0)
                feat["properties"]["_pid"] = pid
                counters[tid] = pid + 1

            st.session_state.resultado = result
            st.session_state.removed_catacao = set()
            st.session_state.result_version = int(st.session_state.get("result_version", 0)) + 1
            st.session_state.params_usados = {
                "Buffer daninha": f"{config['weed_buffer_m']} m",
                "Agrupamento": f"{config['merge_distance_m']} m",
                "Dist. obstáculo": f"{config['obstacle_safety_buffer_m']} m",
                "Área mín.": f"{config['min_polygon_area_m2']} m²",
                "Algoritmo": str(config["coverage_method"]).upper(),
                "Fill ratio": f"{config['rectangle_min_fill_ratio']:.2f}",
                "Prof. max": str(int(config["rectangle_max_depth"])),
                "Máx. lados": str(int(config["max_polygon_sides"])),
            }
            st.toast("✅ Polígonos gerados!", icon="✅")
        except (ValueError, RuntimeError, GEOSException, TopologicalError) as exc:
            st.toast(f"Erro: {exc}", icon="❌")
            st.error(f"Erro no processamento: {exc}")
            st.session_state.resultado = None


def _fc_light_signature(fc: dict | None) -> str:
    if not fc:
        return "none"
    feats = fc.get("features", [])
    if not feats:
        return "0"

    indices = [0, len(feats) // 2, len(feats) - 1]
    samples: list[str] = [str(len(feats))]
    for idx in indices:
        geometry = feats[idx].get("geometry", {}) if isinstance(feats[idx], dict) else {}
        raw = json.dumps(geometry, sort_keys=True, default=str)
        samples.append(hashlib.md5(raw.encode()).hexdigest()[:8])
    return ":".join(samples)


def _removed_signature(values: set[str]) -> str:
    if not values:
        return "0"
    raw = "|".join(sorted(values))
    return hashlib.md5(raw.encode()).hexdigest()[:10]


def _map_cache_signature(
    daninhas_gj: dict,
    talhoes_gj: dict,
    obstaculos_gj: dict,
    resultado: dict | None,
    talhao_info: list[dict],
    area_min: float,
    map_height: int,
) -> str:
    result_count = len(resultado.get("features", [])) if resultado else 0
    info_count = len(talhao_info or [])
    result_version = int(st.session_state.get("result_version", 0))

    parts = [
        _fc_light_signature(daninhas_gj),
        _fc_light_signature(talhoes_gj),
        _fc_light_signature(obstaculos_gj),
        str(result_version),
        str(result_count),
        str(info_count),
        f"{float(area_min):.2f}",
        str(map_height),
        _removed_signature(st.session_state.removed_catacao),
    ]
    return "|".join(parts)


def render_map_section(
    daninhas_gj: dict,
    talhoes_gj: dict,
    obstaculos_gj: dict,
    talhao_info: list[dict],
    map_height: int,
    area_min: float,
):
    resultado = None
    if st.session_state.resultado:
        all_feats = st.session_state.resultado.get("features", [])
        visible = (
            [
                f
                for f in all_feats
                if f["properties"].get("_hash") not in st.session_state.removed_catacao
            ]
            if st.session_state.removed_catacao
            else all_feats
        )
        resultado = {"type": "FeatureCollection", "features": visible}

    _map_inputs = (daninhas_gj, talhoes_gj, obstaculos_gj, resultado, talhao_info)
    _map_hash = _map_cache_signature(
        daninhas_gj,
        talhoes_gj,
        obstaculos_gj,
        resultado,
        talhao_info,
        area_min,
        map_height,
    )

    if st.session_state.get("_map_hash") != _map_hash:
        st.session_state["_map_html"] = render_map(*_map_inputs, min_area_m2=float(area_min))
        st.session_state["_map_hash"] = _map_hash

    st.markdown('<div class="map-container">', unsafe_allow_html=True)
    components.html(st.session_state["_map_html"], height=map_height, scrolling=False)
    st.markdown("</div>", unsafe_allow_html=True)
    return resultado


def render_dashboard(
    resultado: dict, daninhas_gj: dict, talhoes_gj: dict, talhao_info: list[dict], area_min: float
):
    context = _compute_dashboard_context(resultado, daninhas_gj, talhoes_gj)

    st.markdown('<p class="section-label">Resumo</p>', unsafe_allow_html=True)
    _render_metrics_row(context)

    dl_fc, n_small_filtered = _build_download_feature_collection(context["features"], area_min)

    col_left, col_right = st.columns([1.2, 1])
    with col_left:
        _render_talhao_details(
            context["by_talhao"],
            context["total_talhoes"],
            talhao_info,
        )
    with col_right:
        _render_edit_panel(context["features"], daninhas_gj)

    _render_parameters_panel()

    if n_small_filtered:
        st.caption(
            f"ℹ️ {n_small_filtered} polígono(s) abaixo de {area_min} m² excluídos do download."
        )

    st.download_button(
        label="⬇️ Baixar GeoJSON",
        data=json.dumps(dl_fc, indent=2, ensure_ascii=False),
        file_name="catacao.geojson",
        mime="application/geo+json",
        use_container_width=True,
        type="primary",
    )


def _compute_dashboard_context(resultado: dict, daninhas_gj: dict, talhoes_gj: dict) -> dict:
    feats = resultado.get("features", [])
    areas = [f["properties"].get("area_m2", 0) for f in feats]
    by_talhao: dict[int, list] = {}
    for feat in feats:
        tid = feat["properties"].get("talhao_id", 0)
        by_talhao.setdefault(tid, []).append(feat)

    return {
        "features": feats,
        "n_daninhas": len(daninhas_gj.get("features", [])),
        "total_talhoes": len(talhoes_gj.get("features", [])),
        "n_rem_d": len(st.session_state.removed_daninhas),
        "n_rem_c": len(st.session_state.removed_catacao),
        "total_area": sum(areas),
        "by_talhao": by_talhao,
    }


def _render_metrics_row(context: dict) -> None:
    features = context["features"]
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Daninhas", f"{context['n_daninhas']}" + (f" (−{context['n_rem_d']})" if context["n_rem_d"] else ""))
    c2.metric("Polígonos", f"{len(features)}" + (f" (−{context['n_rem_c']})" if context["n_rem_c"] else ""))
    c3.metric("Área total", f"{context['total_area'] / 10_000:.3f} ha")
    c4.metric("Área média", f"{context['total_area'] / max(len(features), 1):.0f} m²")
    c5.metric("Talhões", context["total_talhoes"])


def _build_download_feature_collection(feats: list[dict], area_min: float) -> tuple[dict, int]:
    clean_feats: list[dict] = []
    for feature in feats:
        area_m2 = feature["properties"].get("area_m2", 0)
        if area_min > 0 and area_m2 < area_min:
            continue
        props = {k: v for k, v in feature["properties"].items() if not k.startswith("_")}
        clean_feats.append({**feature, "properties": props})

    fc = {"type": "FeatureCollection", "features": clean_feats}
    return fc, len(feats) - len(clean_feats)


def _render_talhao_details(by_talhao: dict[int, list], total_talhoes: int, talhao_info: list[dict]) -> None:
    with st.expander(f"📊 Detalhes por talhão ({total_talhoes})", expanded=False):
        talhao_info_sorted = (
            sorted(talhao_info, key=lambda i: i.get("id", 0))
            if talhao_info
            else [{"id": talhao_id} for talhao_id in range(total_talhoes)]
        )
        for info in talhao_info_sorted:
            tid = info.get("id", 0)
            tf = by_talhao.get(tid, [])
            ta = [f["properties"].get("area_m2", 0) for f in tf]
            color = TALHAO_COLORS[tid % len(TALHAO_COLORS)]
            cols = st.columns([0.3, 1.5, 1, 1, 1])
            cols[0].markdown(f'<span style="color:{color};font-size:18px;">●</span>', unsafe_allow_html=True)
            cols[1].markdown(f"**Talhão {tid + 1}**")
            cols[2].caption(f"{len(tf)} pol.")
            cols[3].caption(f"{sum(ta) / 10_000:.3f} ha")
            cols[4].caption(f"μ {sum(ta) / max(len(tf), 1):.0f} m²")


def _render_edit_panel(feats: list[dict], daninhas_gj: dict) -> None:
    with st.expander("✂️ Editar polígonos", expanded=False):
        cat_options = ["— selecionar catação —"] + [_poly_label(f) for f in feats]
        with st.form("form_remove_cat"):
            cat_sel = st.selectbox("Catação", options=cat_options, key="sel_cat", label_visibility="collapsed")
            rm_cat_submitted = st.form_submit_button("🗑️ Remover catação", use_container_width=True)
        if rm_cat_submitted and cat_sel != "— selecionar catação —":
            st.session_state.removed_catacao.add(
                feats[cat_options.index(cat_sel) - 1]["properties"].get("_hash", "")
            )
            st.rerun()

        dan_feats = daninhas_gj.get("features", [])
        dan_options = ["— selecionar daninha —"] + [f"Daninha {idx + 1}" for idx in range(len(dan_feats))]
        with st.form("form_remove_dan"):
            dan_sel = st.selectbox("Daninha", options=dan_options, key="sel_dan", label_visibility="collapsed")
            rm_dan_submitted = st.form_submit_button("🗑️ Remover daninha", use_container_width=True)
        if rm_dan_submitted and dan_sel != "— selecionar daninha —":
            st.session_state.removed_daninhas.add(_fhash(dan_feats[dan_options.index(dan_sel) - 1]))
            st.rerun()

        removed_total = len(st.session_state.removed_catacao) + len(st.session_state.removed_daninhas)
        if removed_total and st.button(f"🔄 Restaurar {removed_total} removidos", use_container_width=True):
            st.session_state.removed_catacao = set()
            st.session_state.removed_daninhas = set()
            st.rerun()


def _render_parameters_panel() -> None:
    if not st.session_state.params_usados:
        return

    with st.expander("⚙️ Parâmetros utilizados", expanded=False):
        cols = st.columns(len(st.session_state.params_usados))
        for col, (key, value) in zip(cols, st.session_state.params_usados.items()):
            col.markdown(f"**{key}**")
            col.code(value)


def main():
    init_session_state()
    daninhas_gj, talhoes_gj, obstaculos_gj, algo_config, gerar_btn, map_height, area_min = (
        render_sidebar()
    )

    talhao_info = []
    if daninhas_gj.get("features") and talhoes_gj.get("features"):
        talhao_info = get_talhao_info(daninhas_gj, talhoes_gj)

    if gerar_btn:
        process_generation(daninhas_gj, talhoes_gj, obstaculos_gj, algo_config)

    resultado = render_map_section(
        daninhas_gj,
        talhoes_gj,
        obstaculos_gj,
        talhao_info,
        map_height,
        area_min,
    )

    if resultado and resultado.get("features"):
        render_dashboard(resultado, daninhas_gj, talhoes_gj, talhao_info, area_min)
    else:
        st.caption("Ajuste os parâmetros e clique em **Gerar Polígonos**.")


if __name__ == "__main__":
    main()
