import streamlit as st

MAP_SIZES = {"Normal": 650, "Grande": 850, "Máximo": 1080}

TALHAO_COLORS = [
    "#5fa8a3",
    "#6fb08f",
    "#84b678",
    "#6d93c4",
    "#8f83c4",
    "#b08bc0",
    "#be9e78",
    "#78aebe",
    "#be7f7f",
    "#95ad70",
    "#73a6b8",
    "#9e8fc7",
    "#b59f72",
    "#7da996",
    "#8fa5cb",
]

GLOBAL_STYLES = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');

:root {
    --agro-primary: #5fa8a3;
    --agro-primary-dark: #4a8f8b;
    --agro-bg-primary: #1f232b;
    --agro-bg-secondary: #262c36;
    --agro-bg-tertiary: #1a2029;
    --agro-text-primary: #e8edf2;
    --agro-text-secondary: #bcc6d1;
    --agro-text-tertiary: #8d98a6;
    --agro-success: #5ebd74;
    --agro-warning: #c5a04d;
    --agro-danger: #c95a5a;
    --agro-border: rgba(95, 168, 163, 0.22);
    --agro-accent: rgba(95, 168, 163, 0.1);
}

* { font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; }
.block-container { padding-top: 0.5rem; padding-bottom: 0.5rem; }
header[data-testid="stHeader"] { height: 0; }

[data-testid="stSidebar"] {
    background: var(--agro-bg-secondary);
    border-right: 1px solid var(--agro-border);
}

div[data-testid="stMetric"] {
    background: linear-gradient(135deg, var(--agro-bg-secondary) 0%, var(--agro-bg-tertiary) 100%);
    border-radius: 12px;
    padding: 16px 18px;
    border: 1px solid var(--agro-border);
    box-shadow: 0 2px 8px rgba(0, 0, 0, 0.3);
    transition: all 0.3s ease;
}
div[data-testid="stMetric"]:hover {
    border-color: var(--agro-primary);
    box-shadow: 0 4px 12px rgba(77, 166, 166, 0.2);
    transform: translateY(-2px);
}
div[data-testid="stMetric"] label {
    font-size: 11px; text-transform: uppercase; letter-spacing: 1px;
    color: var(--agro-text-tertiary); font-weight: 600;
}
div[data-testid="stMetric"] [data-testid="stMetricValue"] {
    font-size: 24px; color: var(--agro-primary); font-weight: 700; text-shadow: none;
}

.map-container {
    border-radius: 16px; overflow: hidden; border: 2px solid var(--agro-border);
    margin-bottom: 12px; box-shadow: 0 4px 16px rgba(0, 0, 0, 0.4);
}
.map-container iframe { border: none !important; display: block; }

.section-label {
    font-size: 13px; text-transform: uppercase; letter-spacing: 1.2px;
    color: var(--agro-primary); margin: 14px 0 8px 0; font-weight: 700;
    border-bottom: 2px solid var(--agro-border); padding-bottom: 6px;
}

.stButton > button {
    background: linear-gradient(135deg, var(--agro-primary) 0%, var(--agro-primary-dark) 100%);
    color: var(--agro-text-primary); border: none; border-radius: 8px;
    font-weight: 600; transition: all 0.3s ease;
    box-shadow: 0 2px 8px rgba(95, 168, 163, 0.22);
}
.stButton > button:hover {
    transform: translateY(-2px); box-shadow: 0 4px 16px rgba(95, 168, 163, 0.3);
}
.stDownloadButton > button {
    background: linear-gradient(135deg, var(--agro-success) 0%, #4fa163 100%);
    color: var(--agro-text-primary); font-weight: 700; border-radius: 10px;
    padding: 12px 24px; box-shadow: 0 4px 12px rgba(94, 189, 116, 0.28);
}

.streamlit-expanderHeader {
    background: var(--agro-bg-secondary); border: 1px solid var(--agro-border);
    border-radius: 8px; color: var(--agro-text-primary); font-weight: 600;
}
.streamlit-expanderHeader:hover {
    border-color: var(--agro-primary); background: var(--agro-accent);
}

hr { border-color: var(--agro-border) !important; opacity: 0.6; }
.caption { color: var(--agro-text-tertiary); }
input[type="number"], input[type="text"] {
    background: var(--agro-bg-tertiary) !important; border: 1px solid var(--agro-border) !important;
    color: var(--agro-text-primary) !important; border-radius: 6px !important;
}
input[type="number"]:focus, input[type="text"]:focus {
    border-color: var(--agro-primary) !important; box-shadow: 0 0 0 1px var(--agro-primary) !important;
}
.stSlider > div > div > div > div { background: var(--agro-primary) !important; }
.stSlider [data-baseweb="slider"] div[role="slider"] {
    background: #ffffff !important; border: 2px solid var(--agro-primary) !important;
}
.stSlider p, .stSlider span, .stSlider [data-testid="stSliderValue"] { color: #ffffff !important; }

[data-testid="stToggle"] button[role="switch"], [data-testid="stToggle"] div[role="switch"] {
    border: 1px solid var(--agro-border) !important; box-shadow: none !important;
}
[data-testid="stToggle"] button[role="switch"][aria-checked="true"],
[data-testid="stToggle"] div[role="switch"][aria-checked="true"] {
    background: var(--agro-primary) !important; border-color: var(--agro-primary) !important;
}

.stSelectbox > div > div {
    background: var(--agro-bg-tertiary); border-color: var(--agro-border); color: var(--agro-text-primary);
}
[data-testid="stFileUploader"] {
    background: var(--agro-bg-secondary); border: 2px dashed var(--agro-border);
    border-radius: 10px; padding: 1rem;
}
[data-testid="stFileUploader"]:hover {
    border-color: var(--agro-primary); background: var(--agro-accent);
}
.stSuccess { background: rgba(94, 189, 116, 0.1); border-left: 4px solid var(--agro-success); }
.stWarning { background: rgba(197, 160, 77, 0.1); border-left: 4px solid var(--agro-warning); }
.stError { background: rgba(201, 90, 90, 0.1); border-left: 4px solid var(--agro-danger); }
</style>
"""

MAP_CSS = """
<style>
    .leaflet-top.leaflet-left { top: 16px !important; }
    .leaflet-top.leaflet-right { top: 16px !important; }
    .recenter-control { margin-top: 6px !important; }
    .recenter-control a.recenter-btn {
        display: block; text-align: center; text-decoration: none;
        color: #333; font-size: 17px; background: #fff; cursor: pointer;
    }
    .recenter-control a.recenter-btn:hover { background: #f4f4f4; }
</style>
"""

MAP_JS_TEMPLATE = """
<script>
(function() {{
    var KEY = '__catacao_mv';

    function _read() {{
        try {{ var s = localStorage.getItem(KEY); if (s) return JSON.parse(s); }} catch(e) {{}}
        try {{ if (window.parent && window.parent[KEY]) return window.parent[KEY]; }} catch(e) {{}}
        return null;
    }}
    function _write(o) {{
        try {{ localStorage.setItem(KEY, JSON.stringify(o)); }} catch(e) {{}}
        try {{ window.parent[KEY] = o; }} catch(e) {{}}
    }}

    function fixOffsets() {{
        var l = document.querySelector('.leaflet-top.leaflet-left');
        var r = document.querySelector('.leaflet-top.leaflet-right');
        if (l) l.style.top = '16px';
        if (r) r.style.top = '16px';
    }}

    var poll = setInterval(function() {{
        var els = document.querySelectorAll('.folium-map');
        if (!els.length) return;
        var el = els[els.length - 1];
        if (!el || !el._leaflet_id) return;
        var map = null;
        for (var k in window) {{
            if (window[k] && window[k]._container === el) {{ map = window[k]; break; }}
        }}
        if (!map) return;
        clearInterval(poll);

        var bounds = {bounds_json};
        fixOffsets();

        var saved = _read();
        if (saved && typeof saved.lat === 'number') {{
            map.setView([saved.lat, saved.lng], saved.zoom, {{animate:false}});
        }} else if (bounds) {{
            map.fitBounds(bounds, {{padding:[30,30]}});
        }}

        map.on('moveend zoomend', function() {{
            var c = map.getCenter();
            _write({{lat:c.lat, lng:c.lng, zoom:map.getZoom()}});
            fixOffsets();
        }});

        var ctrl = document.querySelector('.leaflet-top.leaflet-left');
        if (ctrl && !document.getElementById('rc-wrap')) {{
            var za = document.querySelector('.leaflet-control-zoom a');
            var cw = za ? za.offsetWidth : 30, ch = za ? za.offsetHeight : 30;
            var w = document.createElement('div');
            w.id = 'rc-wrap';
            w.className = 'leaflet-control leaflet-bar recenter-control';
            var b = document.createElement('a');
            b.title = 'Recentralizar'; b.innerHTML = '\u2295'; b.href = '#';
            b.className = 'recenter-btn';
            b.style.width = cw+'px'; b.style.height = ch+'px'; b.style.lineHeight = ch+'px';
            b.onclick = function(e) {{
                if (e) e.preventDefault();
                try {{ localStorage.removeItem(KEY); }} catch(x) {{}}
                try {{ delete window.parent[KEY]; }} catch(x) {{}}
                if (bounds) map.fitBounds(bounds, {{padding:[30,30], animate:true}});
            }};
            w.appendChild(b); ctrl.appendChild(w);
        }}
        setTimeout(fixOffsets, 80);
        setTimeout(fixOffsets, 350);
    }}, 60);
}})();
</script>
"""


def render_sidebar_header():
    st.markdown(
        """
        <div style="text-align: left; padding: 0.75rem 0;">
            <div style="display:flex; align-items:center; gap:0.75rem;">
                <div style="
                    background: linear-gradient(135deg, #5fa8a3 0%, #4a8f8b 100%);
                    width: 48px; height: 48px; border-radius: 10px;
                    display: inline-flex; align-items: center; justify-content: center;
                    font-size: 24px; box-shadow: 0 4px 10px rgba(95, 168, 163, 0.28);
                ">🌾</div>
                <div>
                    <h2 style="margin:0;color:#e8edf2;font-weight:700;font-size:1.1rem;">Catação · Pulverização Localizada</h2>
                    <p style="margin:0.15rem 0 0 0;color:#5fa8a3;font-size:0.8rem;">GlobalDrones · Automação Agrícola Inteligente</p>
                </div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
