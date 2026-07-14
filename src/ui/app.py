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
from src.pipeline import generate_spraying_per_field
from src.ui.algorithm_catalog import get_algorithm_parameter_keys, list_algorithm_options
from src.ui.helpers import get_field_info
from src.ui.map_renderer import render_map
from src.ui.theme import FIELD_COLORS, GLOBAL_STYLES, MAP_SIZES, render_sidebar_header

st.set_page_config(
    page_title="Spot Spraying · Smart Coverage",
    page_icon="🌾",
    layout="wide",
    initial_sidebar_state="expanded",
)


st.markdown(GLOBAL_STYLES, unsafe_allow_html=True)


ROOT_DIR = Path(__file__).resolve().parents[2]


INPUT_DATA_DIR = ROOT_DIR / "data" / "input"


def _has_sample_files(data_dir: Path) -> bool:

    return (data_dir / "fields.geojson").exists() and any(data_dir.glob("weed*.geojson"))


if _has_sample_files(INPUT_DATA_DIR):
    DATA_DIR = INPUT_DATA_DIR

else:
    FALLBACK_DATA_DIR = ROOT_DIR / "data"

    DATA_DIR = FALLBACK_DATA_DIR if FALLBACK_DATA_DIR.exists() else INPUT_DATA_DIR

EMPTY_FC: dict = empty_feature_collection()

MAX_GEOJSON_MB = 200


def _validate_feature_collection(data: Any, label: str) -> dict:

    if not isinstance(data, dict):
        raise ValueError(f"{label}: Invalid root JSON.")

    if data.get("type") != "FeatureCollection":
        raise ValueError(f"{label}: Invalid GeoJSON (type must be 'FeatureCollection').")

    if not isinstance(data.get("features"), list):
        raise ValueError(f"{label}: Invalid GeoJSON (features must be a list).")

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
                raise ValueError(f"{label}: file too large ({size_mb:.1f} MB).")

        content = source.read()

        if isinstance(content, bytes):
            try:
                content = content.decode("utf-8")

            except UnicodeDecodeError as exc:
                raise ValueError(f"{label}: invalid encoding. Use UTF-8.") from exc

        if hasattr(source, "seek"):
            source.seek(0)

    else:
        p = Path(source)

        if not p.exists():
            return None

        size_mb = p.stat().st_size / (1024 * 1024)

        if size_mb > MAX_GEOJSON_MB:
            raise ValueError(f"{label}: file too large ({size_mb:.1f} MB).")

        try:
            content = p.read_text("utf-8")

        except UnicodeDecodeError as exc:
            raise ValueError(f"{label}: invalid encoding. Use UTF-8.") from exc

    try:
        parsed = json.loads(content)

    except json.JSONDecodeError as exc:
        raise ValueError(f"{label}: invalid JSON: {exc.msg}") from exc

    validated = _validate_feature_collection(parsed, label)

    if cache_key:
        cache[cache_key] = validated

    return validated


def _load_or_stop(source, label: str) -> dict | None:

    try:
        return _load_cached(source, label)

    except ValueError as exc:
        st.error(f"Error loading {label}: {exc}")

        st.stop()


def _merge_fcs(items: list[dict | None]) -> dict:

    feats: list[dict] = []

    for fc in items:
        if fc:
            feats.extend(fc.get("features", []))

    return {"type": "FeatureCollection", "features": feats}


def _split_fields_and_embedded_obstacles(fc: dict | None) -> tuple[dict, dict]:

    if not fc:
        return EMPTY_FC, EMPTY_FC

    fields_features: list[dict] = []

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
            fields_features.append(feat)

    return (
        {"type": "FeatureCollection", "features": fields_features},
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

    tid = p.get("field_id", 0)

    pid = p.get("_pid", 0)

    area = p.get("area_m2", 0)

    return f"F{tid + 1} · P{pid + 1} — {area:.0f} m² ({area / 10_000:.4f} ha)"


def _parse_streamlit_cli_args() -> argparse.Namespace:

    parser = argparse.ArgumentParser(add_help=False)

    parser.add_argument("--weeds", "-d", action="append", default=[])

    parser.add_argument("--fields", "-t", action="append", default=[])

    parser.add_argument("--obstacles", "-o", action="append", default=[])

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
        "result": None,
        "params_usados": None,
        "removed_spraying": set(),
        "removed_weeds": set(),
        "result_version": 0,
    }

    for key, val in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = val


def _load_default_sources(args: argparse.Namespace) -> tuple[dict, dict, dict]:

    cli_d_files = _normalize_cli_paths(args.weeds)

    cli_t_files = _normalize_cli_paths(args.fields)

    cli_o_files = _normalize_cli_paths(args.obstacles)

    default_obstacles_file = DATA_DIR / "obstacles.geojson"

    d_files = cli_d_files if cli_d_files else sorted(DATA_DIR.glob("weed*.geojson"))

    t_file = cli_t_files[0] if cli_t_files else (DATA_DIR / "fields.geojson")

    weeds_gj_raw = _merge_fcs([_load_or_stop(f, Path(f).name) for f in d_files if Path(f).exists()])

    fields_raw = _load_or_stop(t_file, Path(t_file).name) or EMPTY_FC

    fields_gj, embedded_obstacles = _split_fields_and_embedded_obstacles(fields_raw)

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

    obstacles_gj = _merge_fcs([external_obstacles, embedded_obstacles])

    return weeds_gj_raw, fields_gj, obstacles_gj


def _load_uploaded_sources() -> tuple[dict, dict, dict]:

    up_d = st.file_uploader("Weeds", type=["geojson"], accept_multiple_files=True)

    up_t = st.file_uploader("Fields", type=["geojson"])

    up_o = st.file_uploader("Obstacles (optional)", type=["geojson"])

    weeds_gj_raw = (
        _merge_fcs([_load_or_stop(f, getattr(f, "name", "upload")) for f in up_d])
        if up_d
        else EMPTY_FC
    )

    fields_raw = (
        (_load_or_stop(up_t, getattr(up_t, "name", "upload")) or EMPTY_FC) if up_t else EMPTY_FC
    )

    fields_gj, embedded_obstacles = _split_fields_and_embedded_obstacles(fields_raw)

    external_obstacles = (
        _load_or_stop(up_o, getattr(up_o, "name", "upload")) or EMPTY_FC if up_o else EMPTY_FC
    )

    obstacles_gj = _merge_fcs([external_obstacles, embedded_obstacles])

    return weeds_gj_raw, fields_gj, obstacles_gj


def _filter_removed_weeds(weeds_gj_raw: dict) -> dict:

    if not st.session_state.removed_weeds:
        return weeds_gj_raw

    return {
        "type": "FeatureCollection",
        "features": [
            feature
            for feature in weeds_gj_raw.get("features", [])
            if _fhash(feature) not in st.session_state.removed_weeds
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

    buffer_m = _param_slider_input("Weed buffer (m)", 0.0, 25.0, cfg.weed_buffer_m, 0.5, "p_buf")

    merge_m = _param_slider_input(
        "Clustering distance (m)", 0.0, 250.0, cfg.merge_distance_m, 1.0, "p_mrg"
    )

    obs_buffer = _param_slider_input(
        "Obstacle safety distance (m)", 0.0, 25.0, cfg.obstacle_safety_buffer_m, 0.5, "p_obs"
    )

    coverage_method = st.selectbox(
        "Coverage algorithm",
        options=method_options,
        index=method_options.index(cfg_method),
        format_func=lambda method: option_map[method].label,
        help="The list is built from the methods supported by the engine, independent of a fixed UI enumeration.",
    )

    selected_option = option_map[coverage_method]

    st.caption(selected_option.description)

    area_min = st.number_input(
        "Minimum area (m²)",
        min_value=0.0,
        max_value=50000.0,
        value=cfg.min_polygon_area_m2,
        step=100.0,
    )

    with st.expander("⚙️ Advanced", expanded=False):
        fill_ratio = _param_slider_input(
            "Min. fill ratio",
            0.05,
            0.95,
            cfg.rectangle_min_fill_ratio,
            0.05,
            "p_fill",
        )

        max_depth = st.number_input(
            "Max division depth",
            min_value=1,
            max_value=12,
            value=cfg.rectangle_max_depth,
            step=1,
        )

        max_sides = st.number_input(
            "Max sides (buffers)",
            min_value=4,
            max_value=256,
            value=cfg.max_polygon_sides,
            step=4,
            help=(
                "Controls how many sides the buffer arcs can use. "
                "Smaller values keep the boundary cleaner; larger values make it smoother."
            ),
        )

        neg_buffer = _param_slider_input(
            "Negative buffer (m)", 0.0, 5.0, cfg.negative_buffer_m, 0.1, "p_neg"
        )

        method_specific_keys = set(get_algorithm_parameter_keys(coverage_method))

        if "grid_cell_size_m" in method_specific_keys:
            st.markdown("###### Fixed Grid")

            grid_cell_size_m = _param_slider_input(
                "Cell size (m)",
                0.5,
                30.0,
                cfg.grid_cell_size_m,
                0.5,
                "p_grid_cell",
            )

            grid_fill_threshold = _param_slider_input(
                "Minimum cell fill ratio",
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
                "Minimum cell size (m)",
                0.5,
                30.0,
                cfg.quadtree_min_cell_size_m,
                0.5,
                "p_qt_min_cell",
            )

            quadtree_fill_threshold = _param_slider_input(
                "Minimum cell fill ratio",
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
                "Alpha radius (m)",
                1.0,
                100.0,
                cfg.alpha_shape_radius_m,
                1.0,
                "p_alpha_radius",
            )

        else:
            alpha_shape_radius_m = cfg.alpha_shape_radius_m

        if "strip_width_m" in method_specific_keys:
            st.markdown("###### Strips")

            strip_width_m = _param_slider_input(
                "Strip width (m)",
                0.5,
                30.0,
                cfg.strip_width_m,
                0.5,
                "p_strip_width",
            )

            strip_fill_threshold = _param_slider_input(
                "Minimum strip fill ratio",
                0.05,
                1.0,
                cfg.strip_fill_threshold,
                0.05,
                "p_strip_fill",
            )

        else:
            strip_width_m = cfg.strip_width_m

            strip_fill_threshold = cfg.strip_fill_threshold

        if coverage_method == "morph-closing":
            st.caption("In morphological closing, the weed buffer acts as the smoothing radius.")

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
    }

    return algo_config, float(area_min)


def render_sidebar() -> tuple:

    with st.sidebar:
        render_sidebar_header()

        st.divider()

        st.markdown("##### 📁 Input Data")

        args = _parse_streamlit_cli_args()

        cli_d = _normalize_cli_paths(args.weeds)

        cli_t = _normalize_cli_paths(args.fields)

        if cli_d or cli_t:
            weeds_gj_raw, fields_gj, obstacles_gj = _load_default_sources(args)

        else:
            weeds_gj_raw, fields_gj, obstacles_gj = _load_uploaded_sources()

        n_obstacles = len(obstacles_gj.get("features", []))

        st.caption(f"Obstacles loaded: {n_obstacles}")

        weeds_gj = _filter_removed_weeds(weeds_gj_raw)

        st.divider()

        st.markdown("##### 🔧 Parameters")

        algo_config, area_min = _render_parameter_controls()

        st.divider()

        st.markdown("##### 🗺️ Visualization")

        map_size = st.selectbox("Map size", options=list(MAP_SIZES.keys()), index=1)

        map_height = MAP_SIZES[map_size]

        st.divider()

        generate_btn = st.button("🚀 Generate Polygons", type="primary", use_container_width=True)

        return weeds_gj, fields_gj, obstacles_gj, algo_config, generate_btn, map_height, area_min


def process_generation(weeds_gj: dict, fields_gj: dict, obstacles_gj: dict, config: dict):

    if not weeds_gj.get("features") or not fields_gj.get("features"):
        st.toast("⚠️ Please load weed and field files.", icon="⚠️")

        return

    with st.spinner("Processing fields..."):
        try:
            result = generate_spraying_per_field(
                weeds_geojson=weeds_gj,
                obstacles_geojson=obstacles_gj,
                fields_geojson=fields_gj,
                config=config,
            )

            counters: dict[int, int] = {}

            for feat in result.get("features", []):
                feat["properties"]["_hash"] = _fhash(feat)

                tid = feat["properties"].get("field_id", 0)

                pid = counters.get(tid, 0)

                feat["properties"]["_pid"] = pid

                counters[tid] = pid + 1

            st.session_state.result = result

            st.session_state.removed_spraying = set()

            st.session_state.result_version = int(st.session_state.get("result_version", 0)) + 1

            st.session_state.params_usados = {
                "Weed buffer": f"{config['weed_buffer_m']} m",
                "Clustering": f"{config['merge_distance_m']} m",
                "Obstacle safety": f"{config['obstacle_safety_buffer_m']} m",
                "Min area": f"{config['min_polygon_area_m2']} m²",
                "Algorithm": str(config["coverage_method"]).upper(),
                "Fill ratio": f"{config['rectangle_min_fill_ratio']:.2f}",
                "Max depth": str(int(config["rectangle_max_depth"])),
                "Max sides": str(int(config["max_polygon_sides"])),
            }

            st.toast("✅ Polygons generated!", icon="✅")

        except (ValueError, RuntimeError, GEOSException, TopologicalError) as exc:
            st.toast(f"Error: {exc}", icon="❌")

            st.error(f"Processing error: {exc}")

            st.session_state.result = None


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
    weeds_gj: dict,
    fields_gj: dict,
    obstacles_gj: dict,
    result: dict | None,
    field_info: list[dict],
    area_min: float,
    map_height: int,
) -> str:

    result_count = len(result.get("features", [])) if result else 0

    info_count = len(field_info or [])

    result_version = int(st.session_state.get("result_version", 0))

    parts = [
        _fc_light_signature(weeds_gj),
        _fc_light_signature(fields_gj),
        _fc_light_signature(obstacles_gj),
        str(result_version),
        str(result_count),
        str(info_count),
        f"{float(area_min):.2f}",
        str(map_height),
        _removed_signature(st.session_state.removed_spraying),
    ]

    return "|".join(parts)


def render_map_section(
    weeds_gj: dict,
    fields_gj: dict,
    obstacles_gj: dict,
    field_info: list[dict],
    map_height: int,
    area_min: float,
):

    result = None

    if st.session_state.result:
        all_feats = st.session_state.result.get("features", [])

        visible = (
            [
                f
                for f in all_feats
                if f["properties"].get("_hash") not in st.session_state.removed_spraying
            ]
            if st.session_state.removed_spraying
            else all_feats
        )

        result = {"type": "FeatureCollection", "features": visible}

    _map_inputs = (weeds_gj, fields_gj, obstacles_gj, result, field_info)

    _map_hash = _map_cache_signature(
        weeds_gj,
        fields_gj,
        obstacles_gj,
        result,
        field_info,
        area_min,
        map_height,
    )

    if st.session_state.get("_map_hash") != _map_hash:
        st.session_state["_map_html"] = render_map(*_map_inputs, min_area_m2=float(area_min))

        st.session_state["_map_hash"] = _map_hash

    st.markdown('<div class="map-container">', unsafe_allow_html=True)

    components.html(st.session_state["_map_html"], height=map_height, scrolling=False)

    st.markdown("</div>", unsafe_allow_html=True)

    return result


def render_dashboard(
    result: dict, weeds_gj: dict, fields_gj: dict, field_info: list[dict], area_min: float
):

    context = _compute_dashboard_context(result, weeds_gj, fields_gj)

    st.markdown('<p class="section-label">Summary</p>', unsafe_allow_html=True)

    _render_metrics_row(context)

    dl_fc, n_small_filtered = _build_download_feature_collection(context["features"], area_min)

    col_left, col_right = st.columns([1.2, 1])

    with col_left:
        _render_field_details(
            context["by_field"],
            context["total_fields"],
            field_info,
        )

    with col_right:
        _render_edit_panel(context["features"], weeds_gj)

    _render_parameters_panel()

    if n_small_filtered:
        st.caption(f"ℹ️ {n_small_filtered} polygon(s) under {area_min} m² excluded from download.")

    st.download_button(
        label="⬇️ Download GeoJSON",
        data=json.dumps(dl_fc, indent=2, ensure_ascii=False),
        file_name="spraying.geojson",
        mime="application/geo+json",
        use_container_width=True,
        type="primary",
    )


def _compute_dashboard_context(result: dict, weeds_gj: dict, fields_gj: dict) -> dict:

    feats = result.get("features", [])

    areas = [f["properties"].get("area_m2", 0) for f in feats]

    by_field: dict[int, list] = {}

    for feat in feats:
        tid = feat["properties"].get("field_id", 0)

        by_field.setdefault(tid, []).append(feat)

    return {
        "features": feats,
        "n_weeds": len(weeds_gj.get("features", [])),
        "total_fields": len(fields_gj.get("features", [])),
        "n_rem_w": len(st.session_state.removed_weeds),
        "n_rem_s": len(st.session_state.removed_spraying),
        "total_area": sum(areas),
        "by_field": by_field,
    }


def _render_metrics_row(context: dict) -> None:

    features = context["features"]

    c1, c2, c3, c4, c5 = st.columns(5)

    c1.metric(
        "Weeds",
        f"{context['n_weeds']}" + (f" (−{context['n_rem_w']})" if context["n_rem_w"] else ""),
    )

    c2.metric(
        "Polygons", f"{len(features)}" + (f" (−{context['n_rem_s']})" if context["n_rem_s"] else "")
    )

    c3.metric("Total area", f"{context['total_area'] / 10_000:.3f} ha")

    c4.metric("Mean area", f"{context['total_area'] / max(len(features), 1):.0f} m²")

    c5.metric("Fields", context["total_fields"])


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


def _render_field_details(
    by_field: dict[int, list], total_fields: int, field_info: list[dict]
) -> None:

    with st.expander(f"📊 Details by field ({total_fields})", expanded=False):
        field_info_sorted = (
            sorted(field_info, key=lambda i: i.get("id", 0))
            if field_info
            else [{"id": field_id} for field_id in range(total_fields)]
        )

        for info in field_info_sorted:
            tid = info.get("id", 0)

            tf = by_field.get(tid, [])

            ta = [f["properties"].get("area_m2", 0) for f in tf]

            color = FIELD_COLORS[tid % len(FIELD_COLORS)]

            cols = st.columns([0.3, 1.5, 1, 1, 1])

            cols[0].markdown(
                f'<span style="color:{color};font-size:18px;">●</span>', unsafe_allow_html=True
            )

            cols[1].markdown(f"**Field {tid + 1}**")

            cols[2].caption(f"{len(tf)} poly.")

            cols[3].caption(f"{sum(ta) / 10_000:.3f} ha")

            cols[4].caption(f"mean {sum(ta) / max(len(tf), 1):.0f} m²")


def _render_edit_panel(feats: list[dict], weeds_gj: dict) -> None:

    with st.expander("✂️ Edit polygons", expanded=False):
        cat_options = ["— select spraying —"] + [_poly_label(f) for f in feats]

        with st.form("form_remove_cat"):
            cat_sel = st.selectbox(
                "Spraying", options=cat_options, key="sel_cat", label_visibility="collapsed"
            )

            rm_cat_submitted = st.form_submit_button("🗑️ Remove spraying", use_container_width=True)

        if rm_cat_submitted and cat_sel != "— select spraying —":
            st.session_state.removed_spraying.add(
                feats[cat_options.index(cat_sel) - 1]["properties"].get("_hash", "")
            )

            st.rerun()

        dan_feats = weeds_gj.get("features", [])

        dan_options = ["— select weed —"] + [f"Weed {idx + 1}" for idx in range(len(dan_feats))]

        with st.form("form_remove_dan"):
            dan_sel = st.selectbox(
                "Weed", options=dan_options, key="sel_dan", label_visibility="collapsed"
            )

            rm_dan_submitted = st.form_submit_button("🗑️ Remove weed", use_container_width=True)

        if rm_dan_submitted and dan_sel != "— select weed —":
            st.session_state.removed_weeds.add(_fhash(dan_feats[dan_options.index(dan_sel) - 1]))

            st.rerun()

        removed_total = len(st.session_state.removed_spraying) + len(st.session_state.removed_weeds)

        if removed_total and st.button(
            f"🔄 Restore {removed_total} removed", use_container_width=True
        ):
            st.session_state.removed_spraying = set()

            st.session_state.removed_weeds = set()

            st.rerun()


def _render_parameters_panel() -> None:

    if not st.session_state.params_usados:
        return

    with st.expander("⚙️ Parameters used", expanded=False):
        cols = st.columns(len(st.session_state.params_usados))

        for col, (key, value) in zip(cols, st.session_state.params_usados.items(), strict=False):
            col.markdown(f"**{key}**")

            col.code(value)


def main():

    init_session_state()

    weeds_gj, fields_gj, obstacles_gj, algo_config, generate_btn, map_height, area_min = (
        render_sidebar()
    )

    field_info = []

    if weeds_gj.get("features") and fields_gj.get("features"):
        field_info = get_field_info(weeds_gj, fields_gj)

    if generate_btn:
        process_generation(weeds_gj, fields_gj, obstacles_gj, algo_config)

    result = render_map_section(
        weeds_gj,
        fields_gj,
        obstacles_gj,
        field_info,
        map_height,
        area_min,
    )

    if result and result.get("features"):
        render_dashboard(result, weeds_gj, fields_gj, field_info, area_min)

    else:
        st.caption("Adjust the parameters and click on **Generate Polygons**.")


if __name__ == "__main__":
    main()
