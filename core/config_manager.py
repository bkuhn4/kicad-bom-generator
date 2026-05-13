import json
from pathlib import Path

CONFIG_PATH = Path.home() / ".kicad_bom_enhancer" / "config.json"

_ALL_COLUMN_KEYS = [
    "qty", "references", "value", "description", "footprint",
    "packaging", "mpn", "manufacturer", "digikey_pn", "stock",
    "mouser_pn", "lcsc_pn", "notes",
]

DEFAULT_CONFIG = {
    "digikey": {"client_id": "", "client_secret": "", "sandbox": False},
    "mouser": {"api_key": ""},
    "default_packaging": "Cut Tape",
    "low_stock_threshold": 10,
    "export": {
        "header_color": "4F6228",
        "project_name": "",
        "revision": "",
        "show_title": True,
        "show_footer": True,
    },
    "columns": {k: {"show": True, "export": True} for k in _ALL_COLUMN_KEYS},
    "recent_files": [],
    "use_footprint_aliases": True,
    "compress_references": True,
}


def load_config() -> dict:
    if CONFIG_PATH.exists():
        with open(CONFIG_PATH) as f:
            cfg = json.load(f)
        for k, v in DEFAULT_CONFIG.items():
            cfg.setdefault(k, v)
        # ensure nested sub-keys exist too
        for k in ("export",):
            for sub, val in DEFAULT_CONFIG[k].items():
                cfg[k].setdefault(sub, val)
        # back-fill any new column keys added after initial setup
        for col_key in _ALL_COLUMN_KEYS:
            cfg["columns"].setdefault(col_key, {"show": True, "export": True})
        return cfg
    return DEFAULT_CONFIG.copy()


def save_config(config: dict):
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_PATH, "w") as f:
        json.dump(config, f, indent=2)
