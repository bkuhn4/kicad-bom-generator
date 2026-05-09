from __future__ import annotations
import json
from pathlib import Path

CONFIG_DIR = Path.home() / ".auto_bom"
CONFIG_FILE = CONFIG_DIR / "config.json"

DEFAULTS: dict = {
    "digikey_client_id": "",
    "digikey_client_secret": "",
    "mouser_api_key": "",
    "preferred_packaging": "Cut Tape (CT)",
    "recent_files": [],
    "export_columns": {
        "Reference(s)": True,
        "Description": True,
        "Package": True,
        "MF Part Number": True,
        "Manufacturer": True,
        "DigiKey PN": True,
        "DK Packaging": False,
        "Mouser PN": True,
        "Mouser Packaging": True,
        "LCSC PN": True,
        "Notes": True,
    }
}


def load() -> dict:
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, encoding="utf-8") as f:
                return {**DEFAULTS, **json.load(f)}
        except Exception:
            pass
    return DEFAULTS.copy()


def save(cfg: dict) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2)
