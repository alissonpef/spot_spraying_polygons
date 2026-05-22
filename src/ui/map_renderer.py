import html
import json
import sys

sys.modules.setdefault("pyarrow", None)
import folium

from .theme import FIELD_COLORS, MAP_CSS, MAP_JS_TEMPLATE


def _sanitize(value) -> str:

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


def _add_fields(map_obj: folium.Map, fields: dict, field_info: list[dict] | None) -> None:
    group = folium.FeatureGroup(name="Fields")
    for i, feat in enumerate(fields.get("features", [])):
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
            tooltip=f"Field {safe_field_id}",
        ).add_to(group)

    if field_info:
        for info in field_info:
            field_id = int(info.get("id", 0))
            weeds_count = _sanitize(info.get("weeds", 0))
            folium.Marker(
                location=[info["centroid_lat"], info["centroid_lon"]],
                icon=folium.DivIcon(
                    html=(
                        f'<div style="font-size:11px;font-weight:bold;'
                        f"color:#2ecc71;text-shadow:1px 1px 2px #000;"
                        f'white-space:nowrap;">F{field_id + 1} ({weeds_count}w)</div>'
                    ),
                    icon_size=(80, 20),
                    icon_anchor=(40, 10),
                ),
            ).add_to(group)
    group.add_to(map_obj)


def _add_weeds(map_obj: folium.Map, weeds: dict) -> None:
    group = folium.FeatureGroup(name="Weeds")
    for idx, feat in enumerate(weeds.get("features", [])):
        folium.GeoJson(
            feat,
            style_function=lambda _: {
                "color": "#e74c3c",
                "weight": 1,
                "fillColor": "#c0392b",
                "fillOpacity": 0.65,
            },
            tooltip=f"Weed {idx + 1}",
        ).add_to(group)
    group.add_to(map_obj)


def _add_obstacles(map_obj: folium.Map, obstacles: dict) -> None:
    group = folium.FeatureGroup(name="Obstacles")
    for idx, feat in enumerate(obstacles.get("features", [])):
        props = feat.get("properties", {})
        field_id = props.get("field_id", "?")
        note = props.get("note", "")
        tooltip = f"Obstacle {idx + 1} · Field {field_id}"
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


def _add_result(map_obj: folium.Map, result: dict, min_area_m2: float) -> None:
    by_field: dict[int, list] = {}
    for feat in result.get("features", []):
        field_id = feat.get("properties", {}).get("field_id", 0)
        by_field.setdefault(field_id, []).append(feat)

    for tid, feats in sorted(by_field.items()):
        color = FIELD_COLORS[tid % len(FIELD_COLORS)]
        group = folium.FeatureGroup(name=f"Spraying F{tid + 1}")
        for feat in feats:
            props = feat.get("properties", {})
            pid = int(props.get("_pid", 0))
            area = float(props.get("area_m2", 0))
            is_small = bool(min_area_m2 > 0 and area < min_area_m2)
            label = _sanitize(f"F{tid + 1} · P{pid + 1}")
            area_text = _sanitize(f"{area:.0f}")
            area_ha_text = _sanitize(f"{area / 10_000:.4f}")

            small_warning = (
                '<br><span style="font-size:11px;color:#e67e22;font-weight:bold;">'
                "⚠️ Area below minimum</span>"
                if is_small
                else ""
            )
            popup_html = (
                f'<div style="min-width:140px;font-family:sans-serif;">'
                f'<b style="font-size:14px;">{label}</b><br>'
                f'<span style="font-size:12px;">Area: {area_text} m² ({area_ha_text} ha)</span>'
                f"{small_warning}<br>"
                f'<span style="font-size:11px;color:#888;">Select '
                f"<b>{label}</b> below the map to remove</span>"
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
    weeds: dict | None,
    fields: dict | None,
    obstacles: dict | None = None,
    result: dict | None = None,
    field_info: list[dict] | None = None,
    min_area_m2: float = 0.0,
) -> str:
    ref = fields if fields and fields.get("features") else weeds
    center = _center(ref) if ref else [-15.0, -47.0]
    bounds = _bbox(ref) if ref else None

    map_obj = folium.Map(location=center, zoom_start=15, tiles=None)

    folium.TileLayer("CartoDB positron", name="Light").add_to(map_obj)
    folium.TileLayer("CartoDB dark_matter", name="Dark").add_to(map_obj)
    folium.TileLayer(
        tiles=(
            "https://server.arcgisonline.com/ArcGIS/rest/services/"
            "World_Imagery/MapServer/tile/{z}/{y}/{x}"
        ),
        attr="Esri",
        name="Satellite",
    ).add_to(map_obj)

    if fields and fields.get("features"):
        _add_fields(map_obj, fields, field_info)

    if weeds and weeds.get("features"):
        _add_weeds(map_obj, weeds)

    if obstacles and obstacles.get("features"):
        _add_obstacles(map_obj, obstacles)

    if result and result.get("features"):
        _add_result(map_obj, result, min_area_m2)

    folium.LayerControl(collapsed=True).add_to(map_obj)

    rendered_html = map_obj.get_root().render()
    bounds_json = json.dumps(bounds) if bounds else "null"
    inject = MAP_CSS + MAP_JS_TEMPLATE.format(bounds_json=bounds_json)
    return rendered_html.replace("</body>", inject + "</body>")
