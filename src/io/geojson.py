from __future__ import annotations

import json
import logging
import os
import tempfile
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def empty_feature_collection() -> dict:
    return {"type": "FeatureCollection", "features": []}


def is_valid_feature_collection(data: Any) -> bool:
    return isinstance(data, dict) and isinstance(data.get("features"), list)


def load_geojson(file_path: str | Path) -> dict:
    path = Path(file_path)
    if not path.is_file():
        raise FileNotFoundError(f"Arquivo não encontrado: {file_path}")
    with open(path, "r", encoding="utf-8") as file_handle:
        return json.load(file_handle)


def save_geojson(data: dict, file_path: str | Path) -> None:
    path = Path(file_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    fd, temp_path = tempfile.mkstemp(prefix=f".{path.stem}-", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as file_handle:
            json.dump(data, file_handle, indent=2, ensure_ascii=False)
            file_handle.flush()
            os.fsync(file_handle.fileno())
        os.replace(temp_path, str(path))
    except Exception:
        try:
            os.unlink(temp_path)
        except OSError:
            pass
        raise


def load_geojsons(file_paths: list[str | Path], allow_missing: bool = False) -> dict:
    merged = empty_feature_collection()
    has_any_valid = False

    for file_path in file_paths:
        try:
            data = load_geojson(file_path)
        except FileNotFoundError:
            if allow_missing:
                logger.warning("Arquivo não encontrado: %s. Ignorando.", file_path)
                continue
            raise
        except json.JSONDecodeError as exc:
            raise ValueError(f"Arquivo {file_path} não é um JSON válido.") from exc

        if not is_valid_feature_collection(data):
            logger.warning("Arquivo sem FeatureCollection válida. Ignorando: %s", file_path)
            continue

        has_any_valid = True
        merged["features"].extend(data.get("features", []))

    return merged if has_any_valid else empty_feature_collection()
