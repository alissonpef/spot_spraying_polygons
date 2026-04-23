import html
import json
import sys

# Folium only uses pandas/pyarrow as optional helpers. In this environment,
# importing pyarrow crashes the interpreter, so we force it to behave as
# unavailable before Folium pulls pandas in.
sys.modules.setdefault("pyarrow", None)
import folium  # noqa: E402

from ui.theme import MAP_CSS, MAP_JS_TEMPLATE, TALHAO_COLORS  # noqa: E402


def _sanitize(value) -> str:
    # Any value interpolated into custom HTML must pass through strict escaping.
    return html.escape(str(value), quote=True)


def _flat_coords(geom: dict):
    geom_type = geom.get("type", "")
    coords = geom.get("coordinates", [])
    if geom_type == "Point":
        yield coords[:2]
    elif geom_type in ("MultiPoint", "LineString"):
        for point in coords:
            yield point[:2]
    elif geom_type == "Polygon":
        for ring in coords:
            for point in ring:
                yield point[:2]
    elif geom_type == "MultiPolygon":
        for poly in coords:
            for ring in poly:
                for point in ring:
                    yield point[:2]


def _bbox(geojson: dict) -> list[list[float]] | None:
    lons, lats = [], []
    for feature in geojson.get("features", []):
        geometry = feature.get("geometry")
        if not geometry:
            continue
        for lon, lat in _flat_coords(geometry):
            lons.append(lon)
            lats.append(lat)
    if not lons:
        return None
    return [[min(lats), min(lons)], [max(lats), max(lons)]]


def _center(geojson: dict) -> list[float]:
    bounds = _bbox(geojson)
    if not bounds:
        return [-15.0, -47.0]
    return [
        (bounds[0][0] + bounds[1][0]) / 2,
        (bounds[0][1] + bounds[1][1]) / 2,
    ]


def _add_talhoes(map_obj: folium.Map, talhoes: dict, talhao_info: list[dict] | None) -> None:
    group = folium.FeatureGroup(name="Talhões")
    for i, feat in enumerate(talhoes.get("features", [])):
        field_id = feat.get("properties", {}).get("field_id", i + 1)
        safe_field_id = _sanitize(field_id)
        folium.GeoJson(
            feat,
            style_function=lambda _: {
                "color": "#2ecc71",
                "weight": 2,
                "fillColor": "#27ae60",
                "fillOpacity": 0.06,
                "dashArray": "6,4",
            },
            tooltip=f"Talhão {safe_field_id}",
        ).add_to(group)

    if talhao_info:
        for info in talhao_info:
            talhao_id = int(info.get("id", 0))
            daninhas_count = _sanitize(info.get("daninhas", 0))
            folium.Marker(
                location=[info["centroid_lat"], info["centroid_lon"]],
                icon=folium.DivIcon(
                    html=(
                        f'<div style="font-size:11px;font-weight:bold;'
                        f"color:#2ecc71;text-shadow:1px 1px 2px #000;"
                        f'white-space:nowrap;">T{talhao_id + 1} ({daninhas_count}d)</div>'
                    ),
                    icon_size=(80, 20),
                    icon_anchor=(40, 10),
                ),
            ).add_to(group)
    group.add_to(map_obj)


def _add_daninhas(map_obj: folium.Map, daninhas: dict) -> None:
    group = folium.FeatureGroup(name="Daninhas")
    for idx, feat in enumerate(daninhas.get("features", [])):
        folium.GeoJson(
            feat,
            style_function=lambda _: {
                "color": "#e74c3c",
                "weight": 1,
                "fillColor": "#c0392b",
                "fillOpacity": 0.65,
            },
            tooltip=f"Daninha {idx + 1}",
        ).add_to(group)
    group.add_to(map_obj)


def _add_obstaculos(map_obj: folium.Map, obstaculos: dict) -> None:
    group = folium.FeatureGroup(name="Obstáculos")
    for idx, feat in enumerate(obstaculos.get("features", [])):
        props = feat.get("properties", {})
        field_id = props.get("field_id", "?")
        note = props.get("note", "")
        tooltip = f"Obstáculo {idx + 1} · Talhão {field_id}"
        if note:
            tooltip = f"{tooltip} · {note}"

        folium.GeoJson(
            feat,
            style_function=lambda _: {
                "color": "#f39c12",
                "weight": 2,
                "fillColor": "#e67e22",
                "fillOpacity": 0.45,
                "dashArray": "4,3",
            },
            tooltip=_sanitize(tooltip),
        ).add_to(group)
    group.add_to(map_obj)


def _add_resultado(map_obj: folium.Map, resultado: dict, min_area_m2: float) -> None:
    by_talhao: dict[int, list] = {}
    for feat in resultado.get("features", []):
        talhao_id = feat.get("properties", {}).get("talhao_id", 0)
        by_talhao.setdefault(talhao_id, []).append(feat)

    for tid, feats in sorted(by_talhao.items()):
        color = TALHAO_COLORS[tid % len(TALHAO_COLORS)]
        group = folium.FeatureGroup(name=f"Catação T{tid + 1}")
        for feat in feats:
            props = feat.get("properties", {})
            pid = int(props.get("_pid", 0))
            area = float(props.get("area_m2", 0))
            is_small = bool(min_area_m2 > 0 and area < min_area_m2)
            label = _sanitize(f"T{tid + 1} · P{pid + 1}")
            area_text = _sanitize(f"{area:.0f}")
            area_ha_text = _sanitize(f"{area / 10_000:.4f}")

            small_warning = (
                '<br><span style="font-size:11px;color:#e67e22;font-weight:bold;">'
                "⚠️ Área abaixo do mínimo</span>"
                if is_small
                else ""
            )
            popup_html = (
                f'<div style="min-width:140px;font-family:sans-serif;">'
                f'<b style="font-size:14px;">{label}</b><br>'
                f'<span style="font-size:12px;">Área: {area_text} m² ({area_ha_text} ha)</span>'
                f"{small_warning}<br>"
                f'<span style="font-size:11px;color:#888;">Selecione '
                f"<b>{label}</b> abaixo do mapa para remover</span>"
                f"</div>"
            )

            poly_color = "#e67e22" if is_small else color
            dash = "6,4" if is_small else None

            def get_style(c=poly_color, d=dash):
                s = {"color": c, "weight": 2, "fillColor": c, "fillOpacity": 0.30}
                if d:
                    s["dashArray"] = d
                return s

            geo = folium.GeoJson(
                feat,
                style_function=lambda _, st=get_style(): st,
                tooltip=f"{label} — {area_text} m²" + (" ⚠️" if is_small else ""),
            )
            geo.add_child(folium.Popup(popup_html, max_width=220))
            geo.add_to(group)
        group.add_to(map_obj)


def render_map(
    daninhas: dict | None,
    talhoes: dict | None,
    obstaculos: dict | None = None,
    resultado: dict | None = None,
    talhao_info: list[dict] | None = None,
    min_area_m2: float = 0.0,
) -> str:
    ref = talhoes if talhoes and talhoes.get("features") else daninhas
    center = _center(ref) if ref else [-15.0, -47.0]
    bounds = _bbox(ref) if ref else None

    map_obj = folium.Map(location=center, zoom_start=15, tiles=None)

    folium.TileLayer("CartoDB positron", name="Claro").add_to(map_obj)
    folium.TileLayer("CartoDB dark_matter", name="Escuro").add_to(map_obj)
    folium.TileLayer(
        tiles=(
            "https://server.arcgisonline.com/ArcGIS/rest/services/"
            "World_Imagery/MapServer/tile/{z}/{y}/{x}"
        ),
        attr="Esri",
        name="Satélite",
    ).add_to(map_obj)

    if talhoes and talhoes.get("features"):
        _add_talhoes(map_obj, talhoes, talhao_info)

    if daninhas and daninhas.get("features"):
        _add_daninhas(map_obj, daninhas)

    if obstaculos and obstaculos.get("features"):
        _add_obstaculos(map_obj, obstaculos)

    if resultado and resultado.get("features"):
        _add_resultado(map_obj, resultado, min_area_m2)

    folium.LayerControl(collapsed=True).add_to(map_obj)

    rendered_html = map_obj.get_root().render()
    bounds_json = json.dumps(bounds) if bounds else "null"
    inject = MAP_CSS + MAP_JS_TEMPLATE.format(bounds_json=bounds_json)
    return rendered_html.replace("</body>", inject + "</body>")
