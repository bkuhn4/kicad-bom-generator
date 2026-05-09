import re
from pathlib import Path
import pandas as pd


def _strip_prefix(footprint: str) -> str:
    return footprint.split(":", 1)[1] if ":" in footprint else footprint


def _sort_refs(refs: list[str]) -> list[str]:
    def key(r):
        m = re.match(r"([A-Za-z]+)(\d+)", r.strip())
        return (m.group(1), int(m.group(2))) if m else (r, 0)
    return sorted(refs, key=key)


def parse_bom(filepath: str | Path) -> list[dict]:
    df = pd.read_csv(filepath)
    df.columns = [c.strip() for c in df.columns]

    # Flexible column detection
    rename = {}
    for col in df.columns:
        cl = col.lower()
        if "ref" in cl and "references" not in rename.values():
            rename[col] = "references"
        elif cl in ("qty", "quantity", "count") and "qty" not in rename.values():
            rename[col] = "qty"
        elif cl == "value" and "value" not in rename.values():
            rename[col] = "value"
        elif "foot" in cl and "footprint" not in rename.values():
            rename[col] = "footprint"
        elif ("mpn" in cl or ("mfr" in cl and "pn" in cl)) and "mpn" not in rename.values():
            rename[col] = "mpn"
        elif ("manufacturer" in cl or cl == "mfr") and "manufacturer" not in rename.values():
            rename[col] = "manufacturer"

    df = df.rename(columns=rename)

    for req in ("references", "value", "footprint"):
        if req not in df.columns:
            raise ValueError(
                f"Required column '{req}' not found. Detected columns: {list(df.columns)}"
            )

    df["footprint"] = df["footprint"].astype(str).apply(_strip_prefix).str.strip()
    df["value"] = df["value"].astype(str).str.strip()

    rows = []
    for (value, footprint), grp in df.groupby(["value", "footprint"], sort=False):
        all_refs = []
        for cell in grp["references"].astype(str):
            all_refs.extend(r.strip() for r in cell.split(",") if r.strip())

        qty = int(grp["qty"].sum()) if "qty" in grp.columns else len(all_refs)

        def _first(col):
            if col in grp.columns:
                v = grp[col].iloc[0]
                return "" if pd.isna(v) else str(v).strip()
            return ""

        rows.append({
            "references": ", ".join(_sort_refs(all_refs)),
            "qty": qty,
            "value": value,
            "footprint": footprint,
            "mpn": _first("mpn"),
            "manufacturer": _first("manufacturer"),
            "packaging": "Cut Tape",
            "description": "",
            "stock": "",
            "digikey_pn": "",
            "mouser_pn": "",
            "lcsc_pn": "",
            "notes": "",
            "status": "red",
        })

    return rows
