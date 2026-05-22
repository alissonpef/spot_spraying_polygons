# Spot Spraying Polygons

> Automatic generation of georeferenced spraying polygons for localized weed management in precision agriculture.

This tool converts georeferenced weed detection maps, field boundaries, and optional obstacle layers into operational GeoJSON prescription maps. It implements nine coverage algorithms, a spraying-line generator, a full metric suite, and an interactive Streamlit interface — supporting both a command-line pipeline and a visual inspection workflow.

---

## Table of Contents

- [Overview](#overview)
- [System Architecture](#system-architecture)
- [Coverage Algorithms](#coverage-algorithms)
- [Metric Suite](#metric-suite)
- [Technologies](#technologies)
- [Getting Started](#getting-started)
  - [Prerequisites](#prerequisites)
  - [Installation](#installation)
- [Usage](#usage)
  - [CLI — Polygon Generation](#cli--polygon-generation)
  - [CLI — Spraying Lines](#cli--spraying-lines)
  - [CLI — Batch Pipeline](#cli--batch-pipeline)
  - [CLI — Metrics](#cli--metrics)
  - [Interactive UI](#interactive-ui)
- [Configuration](#configuration)
- [Project Structure](#project-structure)

---

## Overview

The core pipeline:

1. **Projection** — Reprojects all input geometries from WGS84 into a metric CRS (UTM, automatically selected from the centroid of the field).
2. **Clipping** — Clips weed detections to the field boundary and optionally removes obstacle areas (with a configurable safety buffer).
3. **Buffering** — Expands each weed detection by a user-defined buffer, approximated as a polygon with a configurable number of sides.
4. **Clustering** — Groups nearby buffered detections into contiguous patches using spatial proximity merging.
5. **Coverage** — Applies one of nine strategies to produce minimal-area spraying polygons for each patch.
6. **Geometry repair** — Validates and optionally repairs invalid geometries at each stage using Shapely's `make_valid`.
7. **Export** — Reprojects the final polygons back to WGS84 and writes a GeoJSON `FeatureCollection`.

---

## System Architecture

```
data/input/
  weed*.geojson        ← Georeferenced weed detections (one file per field or merged)
  fields.geojson       ← Agricultural field boundaries
  obstacles.geojson    ← Optional obstacles (trees, buildings, water bodies)

src/
  core/                ← AlgorithmConfig dataclass, parameter validation, CRS resolution
  geo/                 ← Projection, geometry utilities, spatial indexing, extraction
  algorithms/
    clustering.py      ← Proximity-based patch grouping
    factory.py         ← Coverage context builder and rectangle splitting
    coverage/          ← Nine coverage strategy implementations
    engine.py          ← Main geometry engine (buffer → cluster → cover → clip → export)
  pipeline/            ← Field-by-field orchestration
  io/                  ← GeoJSON I/O utilities
  cli/
    main.py            ← spot-spray entry point
    tasks.py           ← Composite dev / lines / metrics / ui shortcuts
  utils/
    pulverization_lines.py   ← Spraying-line generator with zigzag routing and Dijkstra connectors
    metrics/
      geometric.py     ← Area, perimeter, turns, straight-line length, coverage waste
      iou.py           ← Pairwise IoU and weed-capture analysis between methods
      sensitivity.py   ← MRR sensitivity sweep over fill-ratio and depth parameters
      statistical.py   ← Likert-scale statistical tests for qualitative evaluation
  ui/
    app.py             ← Streamlit application
    map_renderer.py    ← Folium map builder
    algorithm_catalog.py ← Method metadata and parameter registry
    theme.py           ← Global CSS and sidebar styling
```

---

## Coverage Algorithms

Nine strategies are available, each suited to different field geometries and operational priorities:

| Key | Name | Description |
|-----|------|-------------|
| `mrr` | **Minimum Rotated Rectangle** | Fits the tightest possible rotated rectangle to each patch; recursively splits only when the fill ratio falls below a configurable threshold. Minimises area waste and favours long straight passes. |
| `bcd` | **Boustrophedon Cellular Decomp.** | Decomposes patches into axis-aligned cells for systematic back-and-forth coverage. Suitable for irregular shapes with complex contours. |
| `fixed-grid` | **Fixed Grid** | Overlays a regular grid on the patch and retains cells above a minimum fill ratio. Simple and repeatable. |
| `quadtree` | **Quadtree** | Recursively subdivides the bounding box, stopping when a cell is sufficiently filled or reaches a minimum size. Adapts resolution to local weed density. |
| `strip-based` | **Strip-Based** | Aligns parallel bands to the main axis of the patch. Favours long drone passes and is configurable by strip width and minimum fill. |
| `convex-hull` | **Convex Hull** | Single convex polygon enclosing all detections. Fast but may include weed-free area. |
| `concave-hull` | **Concave Hull (Alpha Shape)** | Adaptive concave polygon that follows voids and cutouts; concaveness controlled by alpha radius. |
| `aabb` | **Axis-Aligned Bounding Box** | Simplest conservative bound; zero rotational overhead for the flight controller. |
| `morph-closing` | **Morphological Closing** | Applies dilation followed by erosion to smooth patch boundaries and fill small holes; the weed buffer parameter acts as the structuring-element radius. |

All methods support:
- configurable **weed buffer** and **clustering distance**;
- configurable **obstacle safety buffer** with automatic subtraction;
- configurable **minimum polygon area** filter;
- optional **negative buffer** to shrink the final polygon inward;
- automatic **geometry repair** at every intermediate stage.

---

## Metric Suite

Four independent analysis modules are provided:

### Geometric Metrics (`geometric-metrics`)
Compares all generated methods side-by-side using spray-line data:
- Total spray area (ha) and area/perimeter ratio
- Mean and standard deviation of straight-line segment lengths
- Total number of heading changes (turns) and turns per hectare
- Target coverage percentage and clean area waste percentage

### IoU Analysis (`iou-analysis`)
- Computes **Intersection over Union** between every pair of methods
- Reports pairwise agreement percentages and absolute areas
- Outputs CSV and Markdown tables

### MRR Sensitivity Analysis (`sensitivity-analysis`)
- Sweeps the `rectangle_min_fill_ratio` parameter from 0.00 to 0.50 (step 0.01) for three recursion depths (2, 4, 8)
- Tracks total spraying area, polygon count, IoU vs. ground truth, number of turns, mean straight-line length, and total estimated flight length
- Exports a multi-panel plot and a CSV/Markdown summary

### Likert Statistical Analysis (`likert-stats`)
- Processes qualitative evaluation data (Agronomist, Agronomic Coverage, Spraying Excess, Drone Operability, General Acceptability)
- Runs non-parametric statistical tests and exports formatted tables

---

## Technologies

[![Python](https://img.shields.io/badge/Python_3.11+-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org/)
[![Shapely](https://img.shields.io/badge/Shapely-2E8B57?style=for-the-badge)](https://shapely.readthedocs.io/)
[![PyProj](https://img.shields.io/badge/PyProj-1F6FEB?style=for-the-badge)](https://pyproj4.github.io/pyproj/stable/)
[![GeoPandas](https://img.shields.io/badge/GeoPandas-139C5A?style=for-the-badge)](https://geopandas.org/)
[![SciPy](https://img.shields.io/badge/SciPy-8CAAE6?style=for-the-badge&logo=scipy&logoColor=white)](https://scipy.org/)
[![NumPy](https://img.shields.io/badge/NumPy-013243?style=for-the-badge&logo=numpy&logoColor=white)](https://numpy.org/)
[![Streamlit](https://img.shields.io/badge/Streamlit-FF4B4B?style=for-the-badge&logo=streamlit&logoColor=white)](https://streamlit.io/)
[![Folium](https://img.shields.io/badge/Folium-77B829?style=for-the-badge)](https://python-visualization.github.io/folium/)

Core dependencies are declared in [`pyproject.toml`](pyproject.toml). The package is built with [Hatchling](https://hatch.pypa.io/latest/) and managed with [uv](https://docs.astral.sh/uv/).

---

## Getting Started

### Prerequisites

- Python 3.11 or later
- [`uv`](https://docs.astral.sh/uv/) (recommended) **or** `pip`

### Installation

```sh
# Clone and enter the repository
cd Spot-Spraying-Polygons

# Create a virtual environment and install all dependencies
uv sync

# Activate the environment (Linux/macOS)
source .venv/bin/activate
```

<details>
<summary>Alternative: plain pip</summary>

```sh
python -m venv .venv
source .venv/bin/activate
pip install -e .
```
</details>

---

## Usage

### CLI — Polygon Generation

After installation, the `spot-spray` command is available:

```sh
spot-spray --help
```

**Minimal example** (MRR, three weed files, one field):

```sh
spot-spray \
  --weeds data/input/weed1.geojson data/input/weed2.geojson data/input/weed3.geojson \
  --fields data/input/fields.geojson \
  --output data/output/spraying-mrr.geojson \
  --coverage_method mrr
```

**With obstacles and custom parameters:**

```sh
spot-spray \
  --weeds data/input/weed1.geojson \
  --fields data/input/fields.geojson \
  --obstacles data/input/obstacles.geojson \
  --output data/output/spraying-bcd.geojson \
  --coverage_method bcd \
  --weed_buffer_m 1.5 \
  --merge_distance_m 8.0 \
  --obstacle_safety_buffer_m 3.0 \
  --min_polygon_area_m2 500
```

**Available `--coverage_method` values:**

| Value | Algorithm |
|-------|-----------|
| `mrr` | Minimum Rotated Rectangle |
| `bcd` | Boustrophedon Cellular Decomposition |
| `fixed-grid` | Fixed Grid |
| `quadtree` | Quadtree |
| `strip-based` | Strip-Based |
| `convex-hull` | Convex Hull |
| `concave-hull` | Concave Hull (Alpha Shape) |
| `aabb` | Axis-Aligned Bounding Box |
| `morph-closing` | Morphological Closing |

A JSON configuration file can be passed via `--config <path>` as an alternative to individual flags (CLI flags always override file values).

---

### CLI — Spraying Lines

Generates boustrophedon (zigzag) flight lines from a polygon GeoJSON. Connector segments between passes are computed via a shortest-path algorithm that stays inside the polygon boundary.

```sh
# Single file
spraying-lines <polygon.geojson> <distance_m> <angle_deg> --output-dir data/output/lines

# Batch — processes every .geojson in a directory
spraying-lines-batch data/output/polygons 2.0 0.0 --output-dir data/output/lines --recursive
```

Parameters:
- `distance_m` — spacing between parallel passes (metres)
- `angle_deg` — heading angle of the passes (0 = horizontal, 0–360)

---

### CLI — Batch Pipeline

The `dev` shortcut regenerates all nine methods with default parameters:

```sh
dev
```

The `process-method` command runs a single method with explicit parameters:

```sh
process-method mrr 1.0 5.0 3.0 --negative-buffer-m 0.3
```

Positional arguments: `coverage_method`, `weed_buffer_m`, `merge_distance_m`, `obstacle_safety_buffer_m`.

---

### CLI — Metrics

Run all metric modules in sequence:

```sh
metrics
```

Or run individual modules:

```sh
geometric-metrics --polygons-dir data/output/polygons --output-lines-dir data/output/lines
iou-analysis
sensitivity-analysis
likert-stats
```

All modules export results to `data/output/metrics/` as CSV and Markdown files.

---

### Interactive UI

```sh
ui
# or directly:
streamlit run src/ui/app.py
```

The Streamlit interface provides:

- **File inputs** — upload or use sample weed, field, and obstacle GeoJSON files; obstacles can also be embedded in the fields file via an `obstacle` property.
- **Algorithm selector** — dropdown with all nine methods and per-method descriptions.
- **Parameter panel** — sliders and number inputs for weed buffer, clustering distance, obstacle safety distance, minimum polygon area, fill ratio, recursion depth, buffer smoothness (max sides), and negative buffer.
- **Method-specific controls** — additional parameters appear automatically for Fixed Grid (cell size, fill threshold), Quadtree (minimum cell size, fill threshold), Concave Hull (alpha radius), and Strip-Based (strip width, fill threshold).
- **Interactive map** — Folium map with colour-coded fields, weed overlays, obstacle outlines, and generated spraying polygons; map size is adjustable.
- **Edit panel** — individual spraying polygons or weed detections can be removed interactively before download.
- **Dashboard** — per-field summary (polygon count, total area, mean area); overall totals.
- **GeoJSON export** — one-click download of the filtered result.

---

## Configuration

All algorithm parameters are validated at construction time. Default values:

| Parameter | Default | Description |
|-----------|---------|-------------|
| `weed_buffer_m` | `1.0` | Expansion radius applied to each weed detection (m) |
| `merge_distance_m` | `5.0` | Maximum gap for grouping buffered patches (m) |
| `obstacle_safety_buffer_m` | `3.0` | Dilation applied to obstacles before subtraction (m) |
| `negative_buffer_m` | `0.5` | Inward shrink applied to the final polygon (m) |
| `min_polygon_area_m2` | `1000.0` | Polygons below this area are discarded (m²) |
| `rectangle_min_fill_ratio` | `0.45` | Minimum weed fill ratio before an MRR is split |
| `rectangle_max_depth` | `6` | Maximum recursion depth for MRR splitting |
| `max_polygon_sides` | `16` | Arc resolution for buffer approximation |
| `coverage_method` | `mrr` | Active coverage strategy |
| `grid_cell_size_m` | `2.0` | Fixed-grid and quadtree base cell size (m) |
| `grid_fill_threshold` | `0.35` | Minimum weed fill ratio to retain a grid cell |
| `quadtree_min_cell_size_m` | `1.0` | Minimum quadtree cell size (m) |
| `quadtree_fill_threshold` | `0.35` | Minimum fill ratio to retain a quadtree cell |
| `alpha_shape_radius_m` | `20.0` | Alpha radius for the concave hull (m) |
| `strip_width_m` | `3.0` | Width of each spraying strip (m) |
| `strip_fill_threshold` | `0.30` | Minimum fill ratio to retain a strip |
| `working_crs` | `None` | Override for the projected CRS (auto-selected from UTM otherwise) |
| `fix_invalid_geometries` | `True` | Apply `make_valid` whenever an invalid geometry is detected |

---

## Project Structure

```
Spot-Spraying-Polygons/
├── data/
│   ├── input/          ← Sample weed, field, and obstacle GeoJSON files
│   └── output/
│       ├── polygons/   ← Generated spraying polygons (one file per method)
│       ├── lines/      ← Generated spraying-line GeoJSON files
│       ├── metrics/    ← CSV and Markdown metric reports
│       └── plots/      ← Sensitivity analysis plots
├── src/
│   ├── algorithms/     ← Clustering, factory, engine, and nine coverage strategies
│   ├── cli/            ← CLI entry points and composite task shortcuts
│   ├── core/           ← Configuration dataclass and constants
│   ├── geo/            ← Projection, geometry, spatial indexing, extraction
│   ├── io/             ← GeoJSON I/O
│   ├── pipeline/       ← Field-by-field pipeline orchestration
│   ├── ui/             ← Streamlit application and map renderer
│   └── utils/
│       ├── pulverization_lines.py   ← Spraying-line generator
│       └── metrics/                 ← Geometric, IoU, sensitivity, statistical modules
└── pyproject.toml
```

---

<p align="right">(<a href="#spot-spraying-polygons">back to top</a>)</p>

<!-- MARKDOWN LINKS -->
[python-shield]: https://img.shields.io/badge/Python_3.11+-3776AB?style=for-the-badge&logo=python&logoColor=white
[python-url]: https://www.python.org/
[shapely-shield]: https://img.shields.io/badge/Shapely-2E8B57?style=for-the-badge
[shapely-url]: https://shapely.readthedocs.io/
[pyproj-shield]: https://img.shields.io/badge/PyProj-1F6FEB?style=for-the-badge
[pyproj-url]: https://pyproj4.github.io/pyproj/stable/
[streamlit-shield]: https://img.shields.io/badge/Streamlit-FF4B4B?style=for-the-badge&logo=streamlit&logoColor=white
[streamlit-url]: https://streamlit.io/
[folium-shield]: https://img.shields.io/badge/Folium-77B829?style=for-the-badge
[folium-url]: https://python-visualization.github.io/folium/