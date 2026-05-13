import json
from pathlib import Path

_MAP_PATH = Path(__file__).resolve().parent.parent / "footprint_map.json"


def load_footprint_map() -> dict:
    try:
        with open(_MAP_PATH) as f:
            return json.load(f)
    except Exception:
        return {}


def save_footprint_map(mapping: dict):
    _MAP_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(_MAP_PATH, "w") as f:
        json.dump(mapping, f, indent=2)
