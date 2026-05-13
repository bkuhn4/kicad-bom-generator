from __future__ import annotations

import sqlite3
from pathlib import Path
from datetime import datetime

DB_PATH = Path.home() / ".kicad_bom_enhancer" / "part_dictionary.db"


def _connect():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with _connect() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS part_mappings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                value TEXT NOT NULL,
                footprint TEXT NOT NULL,
                mpn TEXT,
                manufacturer TEXT,
                digikey_pn TEXT,
                mouser_pn TEXT,
                lcsc_pn TEXT,
                description TEXT,
                last_updated TEXT,
                UNIQUE(value, footprint)
            )
        """)
        conn.commit()


def lookup_part(value: str, footprint: str) -> dict | None:
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM part_mappings WHERE value=? AND footprint=?",
            (value, footprint),
        ).fetchone()
        return dict(row) if row else None


def save_part(value: str, footprint: str, data: dict):
    now = datetime.now().isoformat()
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO part_mappings
                (value, footprint, mpn, manufacturer, digikey_pn, mouser_pn, lcsc_pn, description, last_updated)
            VALUES (?,?,?,?,?,?,?,?,?)
            ON CONFLICT(value, footprint) DO UPDATE SET
                mpn=excluded.mpn,
                manufacturer=excluded.manufacturer,
                digikey_pn=excluded.digikey_pn,
                mouser_pn=excluded.mouser_pn,
                lcsc_pn=CASE WHEN excluded.lcsc_pn != '' THEN excluded.lcsc_pn ELSE lcsc_pn END,
                description=excluded.description,
                last_updated=excluded.last_updated
            """,
            (
                value, footprint,
                data.get("mpn", ""),
                data.get("manufacturer", ""),
                data.get("digikey_pn", ""),
                data.get("mouser_pn", ""),
                data.get("lcsc_pn", ""),
                data.get("description", ""),
                now,
            ),
        )
        conn.commit()


def save_lcsc_pn(value: str, footprint: str, lcsc_pn: str):
    now = datetime.now().isoformat()
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO part_mappings (value, footprint, lcsc_pn, last_updated)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(value, footprint) DO UPDATE SET
                lcsc_pn = excluded.lcsc_pn,
                last_updated = excluded.last_updated
            """,
            (value, footprint, lcsc_pn, now),
        )
        conn.commit()
