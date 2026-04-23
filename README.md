<a id="readme-top"></a>

[![Contributors][contributors-shield]][contributors-url]
[![Forks][forks-shield]][forks-url]
[![Stars][stars-shield]][stars-url]
[![Issues][issues-shield]][issues-url]
[![MIT License][license-shield]][license-url]

# Spot Spraying Polygons

Automatic generation of spot spraying polygons from georeferenced weed detections, field boundaries, and obstacles.

The project combines geospatial processing, clustering algorithms, and coverage strategies to produce operational GeoJSON files in WGS84, with a CLI for automation and a Streamlit UI for visual inspection of the results.

## Table of Contents

- [Spot Spraying Polygons](#spot-spraying-polygons)
  - [Table of Contents](#table-of-contents)
  - [About the Project](#about-the-project)
  - [Technologies](#technologies)
    - [Built With](#built-with)
  - [Getting Started](#getting-started)
    - [Prerequisites](#prerequisites)
    - [Installation](#installation)
  - [Usage](#usage)
    - [CLI](#cli)
    - [UI](#ui)
  - [Contributors](#contributors)
  - [Project Structure](#project-structure)
  - [Contributing](#contributing)
  - [License](#license)
  - [Contact](#contact)
  - [Acknowledgements](#acknowledgements)

## About the Project

The main pipeline:

- projects geometries into a metric CRS suitable for the input data;
- clips weeds by field and handles obstacles when provided;
- groups detections by proximity and applies buffers;
- generates polygons with different coverage methods;
- repairs geometries when needed before export;
- returns the final result in WGS84.

## Technologies

### Built With

[![Python][python-shield]][python-url]
[![Shapely][shapely-shield]][shapely-url]
[![PyProj][pyproj-shield]][pyproj-url]
[![Streamlit][streamlit-shield]][streamlit-url]
[![Folium][folium-shield]][folium-url]
[![Hatchling][hatchling-shield]][hatchling-url]
[![Ruff][ruff-shield]][ruff-url]
[![Pytest][pytest-shield]][pytest-url]

The main dependencies are declared in [pyproject.toml](pyproject.toml), with `shapely` and `pyproj` in the core and `streamlit`/`folium` as optional UI extras.

## Getting Started

### Prerequisites

- Python 3.11 or later
- Git

### Installation

1. Clone the repository:
   ```sh
   git clone https://github.com/alissonpef/Spot-Spraying-Polygons.git
   cd Spot-Spraying-Polygons/Catacao
   ```
2. Create and activate the virtual environment:
   ```sh
   python -m venv .venv
   source .venv/bin/activate
   ```
3. Install the base package and, if you want the visual interface, the UI extras:
   ```sh
   pip install -e .
   pip install -e ".[ui]"
   ```

## Usage

### CLI

After installation, the `catacao` command is available.

```sh
catacao --help
```

Example using the sample data included in the repository:

```sh
catacao \
  --daninhas data/input/daninha1.geojson data/input/daninha2.geojson data/input/daninha3.geojson \
  --talhoes data/input/talhoes.geojson \
  --saida data/output/catacao-mrr.geojson \
  --coverage_method mrr
```

The `--obstaculos` option is optional. If there is no obstacle GeoJSON, it can be omitted.

Supported coverage methods:

- `mrr`
- `bcd`
- `bp-mops`
- `fixed-grid`
- `quadtree`
- `convex-hull`
- `concave-hull`
- `aabb`
- `morph-closing`
- `dbscan-buffer`
- `strip-based`

### UI

```sh
streamlit run ui/app.py
```

The interface opens with the sample files by default and allows manual GeoJSON uploads. From there you can adjust parameters, inspect the map, remove weeds or generated polygons, and download the final result.

## Contributors

<a href="https://github.com/alissonpef/Spot-Spraying-Polygons/graphs/contributors">
  <img src="https://contrib.rocks/image?repo=alissonpef/Spot-Spraying-Polygons" alt="Top contributors" />
</a>

The collaborators above are automatically updated by GitHub and contrib.rocks.

## Project Structure

- `src/` - processing engine, geometry, projection, algorithms, CLI, and pipeline.
- `ui/` - Streamlit interface and visual components.
- `data/input/` - sample inputs.

## Contributing

Contributions are welcome. If you want to help:

1. Fork the repository.
2. Create a branch for your change.
3. Keep commits small and focused.
4. Open a pull request describing what changed.

If the change is larger, open an issue first so we can align on scope.

## License

This project is licensed under the MIT License. See [LICENSE.txt](LICENSE.txt) for the full text.

## Contact

Alisson Pereira Ferreira - alissonpef@gmail.com

Project: https://github.com/alissonpef/Spot-Spraying-Polygons

## Acknowledgements

- [Shapely](https://shapely.readthedocs.io/)
- [PyProj](https://pyproj4.github.io/pyproj/stable/)
- [Streamlit](https://streamlit.io/)
- [Folium](https://python-visualization.github.io/folium/)

<p align="right">(<a href="#readme-top">back to top</a>)</p>

<!-- MARKDOWN LINKS & IMAGES -->
[contributors-shield]: https://img.shields.io/github/contributors/alissonpef/Spot-Spraying-Polygons.svg?style=for-the-badge
[contributors-url]: https://github.com/alissonpef/Spot-Spraying-Polygons/graphs/contributors
[forks-shield]: https://img.shields.io/github/forks/alissonpef/Spot-Spraying-Polygons.svg?style=for-the-badge
[forks-url]: https://github.com/alissonpef/Spot-Spraying-Polygons/network/members
[stars-shield]: https://img.shields.io/github/stars/alissonpef/Spot-Spraying-Polygons.svg?style=for-the-badge
[stars-url]: https://github.com/alissonpef/Spot-Spraying-Polygons/stargazers
[issues-shield]: https://img.shields.io/github/issues/alissonpef/Spot-Spraying-Polygons.svg?style=for-the-badge
[issues-url]: https://github.com/alissonpef/Spot-Spraying-Polygons/issues
[license-shield]: https://img.shields.io/github/license/alissonpef/Spot-Spraying-Polygons.svg?style=for-the-badge
[license-url]: LICENSE.txt
[python-shield]: https://img.shields.io/badge/Python-3776AB?style=for-the-badge&logo=python&logoColor=white
[python-url]: https://www.python.org/
[shapely-shield]: https://img.shields.io/badge/Shapely-2E8B57?style=for-the-badge
[shapely-url]: https://shapely.readthedocs.io/
[pyproj-shield]: https://img.shields.io/badge/PyProj-1F6FEB?style=for-the-badge
[pyproj-url]: https://pyproj4.github.io/pyproj/stable/
[streamlit-shield]: https://img.shields.io/badge/Streamlit-FF4B4B?style=for-the-badge&logo=streamlit&logoColor=white
[streamlit-url]: https://streamlit.io/
[folium-shield]: https://img.shields.io/badge/Folium-77B829?style=for-the-badge
[folium-url]: https://python-visualization.github.io/folium/
[hatchling-shield]: https://img.shields.io/badge/Hatchling-111111?style=for-the-badge
[hatchling-url]: https://hatch.pypa.io/latest/
[ruff-shield]: https://img.shields.io/badge/Ruff-111111?style=for-the-badge&logo=ruff&logoColor=white
[ruff-url]: https://docs.astral.sh/ruff/
[pytest-shield]: https://img.shields.io/badge/Pytest-0A9EDC?style=for-the-badge&logo=pytest&logoColor=white
[pytest-url]: https://docs.pytest.org/