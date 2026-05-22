import argparse
import json
import logging
from pathlib import Path

from pyproj import CRS, Transformer
from shapely.geometry import shape
from shapely.ops import transform, unary_union
from shapely.validation import make_valid

logging.basicConfig(level=logging.INFO, format="%(message)s")


def load_and_union_geometries(filepath: Path):
    with open(filepath, "r", encoding="utf-8") as f:
        data = json.load(f)
    geoms = []
    for feature in data.get("features", []):
        geom = shape(feature["geometry"])
        if not geom.is_valid:
            geom = make_valid(geom)
        geoms.append(geom)
    unioned = unary_union(geoms)
    if not unioned.is_valid:
        unioned = make_valid(unioned)
    return unioned


def project_to_metric(geom):
    crs_wgs84 = CRS.from_epsg(4326)
    centroid = geom.centroid
    lon, lat = centroid.x, centroid.y
    zone_number = int((lon + 180) / 6) + 1
    hemisphere = "6" if lat >= 0 else "7"
    target_crs = CRS.from_user_input(f"EPSG:32{hemisphere}{zone_number:02d}")
    transformer = Transformer.from_crs(crs_wgs84, target_crs, always_xy=True)
    return transform(transformer.transform, geom)


def calculate_metrics(geom1, geom2):
    intersection = geom1.intersection(geom2)
    union = geom1.union(geom2)
    area1 = geom1.area
    area2 = geom2.area
    a_int = intersection.area
    a_uni = union.area
    iou = a_int / a_uni if a_uni > 0 else 0
    p_cov_1 = (a_int / area1 * 100) if area1 > 0 else 0
    p_cov_2 = (a_int / area2 * 100) if area2 > 0 else 0
    return {
        "area1": area1,
        "area2": area2,
        "intersection": a_int,
        "union": a_uni,
        "iou": iou,
        "cov1": p_cov_1,
        "cov2": p_cov_2,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--weeds", nargs="*", default=["weed1.geojson", "weed2.geojson", "weed3.geojson"]
    )
    parser.add_argument("--output-dir", type=Path, default=Path("data/output"))
    parser.add_argument("--input-dir", type=Path, default=Path("data/input"))
    args = parser.parse_args()
    results = []

    def log_print(msg):
        print(msg)
        results.append(msg)

    weed_geoms_raw = []
    for wf in args.weeds:
        path = args.input_dir / wf
        if path.exists():
            weed_geoms_raw.append(load_and_union_geometries(path))
    if not weed_geoms_raw:
        log_print(f"ERROR: No weed file found in {args.input_dir}")
        return

    full_weed_geom = project_to_metric(unary_union(weed_geoms_raw))
    total_weed_area = full_weed_geom.area
    log_print(f"Total area of weeds detected: {total_weed_area:.1f} m2\n")

    method_geoms = {}
    method_weed_coverage = {}

    polygons_dir = args.output_dir / "polygons" if (args.output_dir / "polygons").exists() else args.output_dir
    for filepath in polygons_dir.glob("*.geojson"):
        method_name = filepath.stem
        geom = project_to_metric(load_and_union_geometries(filepath))
        method_geoms[method_name] = geom
        capture_area = geom.intersection(full_weed_geom).area
        method_weed_coverage[method_name] = (
            (capture_area / total_weed_area * 100) if total_weed_area > 0 else 0
        )

    log_print("--- Weed Capture per Method ---")
    methods = list(method_geoms.keys())
    for method in methods:
        log_print(f"  * {method}: {method_weed_coverage[method]:.2f}%")

    import pandas as pd

    rows = []
    log_print("\n--- Pairwise Inter-Method Comparison ---")
    for m1 in methods:
        for m2 in methods:
            if m1 >= m2:
                continue
            m = calculate_metrics(method_geoms[m1], method_geoms[m2])
            log_print(f"{m1} vs {m2}:")
            log_print(f"    - IoU: {m['iou']:.2%} ({(m['iou']):.4f})")
            log_print(f"    - Agreement: {m['cov1']:.1f}% of {m1} is in {m2}")
            log_print(f"    - Area {m1}: {m['area1']:.1f} m2")
            log_print(f"    - Area {m2}: {m['area2']:.1f} m2\n")
            rows.append(
                {
                    "method1": m1,
                    "method2": m2,
                    "iou": m["iou"],
                    "agreement_m1_in_m2_pct": m["cov1"],
                    "area1_m2": m["area1"],
                    "area2_m2": m["area2"],
                }
            )

    metrics_dir = args.output_dir / "metrics"
    metrics_dir.mkdir(parents=True, exist_ok=True)

    df = pd.DataFrame(rows)
    if not df.empty:
        df.to_csv(metrics_dir / "iou_analysis.csv", index=False)
        metrics_dir.joinpath("iou_analysis.md").write_text(
            df.to_markdown(index=False), encoding="utf-8"
        )


if __name__ == "__main__":
    main()
