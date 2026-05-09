import json
from pathlib import Path

CONFIG_PATH = Path.home() / ".kicad_bom_enhancer" / "config.json"

DEFAULT_CONFIG = {
    "digikey": {"client_id": "", "client_secret": "", "sandbox": False},
    "mouser": {"api_key": ""},
    "default_packaging": "Cut Tape",
    "low_stock_threshold": 10,
    "export": {"header_color": "4F6228"},
    "recent_files": [],
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
        return cfg
    return DEFAULT_CONFIG.copy()


def save_config(config: dict):
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_PATH, "w") as f:
        json.dump(config, f, indent=2)
