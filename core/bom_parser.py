import re
from itertools import groupby
from pathlib import Path
import pandas as pd


def _strip_prefix(footprint: str) -> str:
    return footprint.split(":", 1)[1] if ":" in footprint else footprint


def _sort_refs(refs: list[str]) -> list[str]:
    def key(r):
        m = re.match(r"([A-Za-z]+)(\d+)", r.strip())
        return (m.group(1), int(m.group(2))) if m else (r, 0)
    return sorted(refs, key=key)


def _compress_refs(refs: list[str]) -> str:
    """Join refs with range compression: R1,R2,R3,R5 → 'R1-R3, R5'."""
    parsed, non_std = [], []
    for r in refs:
        m = re.match(r"^([A-Za-z]+)(\d+)$", r.strip())
        if m:
            parsed.append((m.group(1), int(m.group(2))))
        else:
            non_std.append(r.strip())

    result = []
    for prefix, grp in groupby(sorted(parsed), key=lambda x: x[0]):
        nums = sorted(n for _, n in grp)
        start = end = nums[0]
        for n in nums[1:]:
            if n == end + 1:
                end = n
            else:
                result.append(f"{prefix}{start}-{prefix}{end}" if end > start else f"{prefix}{start}")
                start = end = n
        result.append(f"{prefix}{start}-{prefix}{end}" if end > start else f"{prefix}{start}")

    return ", ".join(result + non_std)


def parse_bom(filepath: str | Path, footprint_map: dict | None = None,
              compress_refs: bool = True) -> list[dict]:
    df = pd.read_csv(filepath)
    df.columns = [c.strip() for c in df.columns]

    # Flexible column detection
    rename = {}
    for col in df.columns:
        cl = col.lower().strip()
        if "ref" in cl and "references" not in rename.values():
            rename[col] = "references"
        elif cl in ("qty", "quantity", "count") and "qty" not in rename.values():
            rename[col] = "qty"
        elif cl == "value" and "value" not in rename.values():
            rename[col] = "value"
        elif "foot" in cl and "footprint" not in rename.values():
            rename[col] = "footprint"
        # MPN: "Manufacturer PN", "MPN", "MFR PN", "Part Number" — must check before manufacturer
        elif (cl in ("mpn", "manufacturer pn", "mfr pn", "mfr. pn", "part number", "part no")
              or ("mpn" in cl)
              or ("mfr" in cl and "pn" in cl)
              or (("manufacturer" in cl or "manuf" in cl) and "pn" in cl)
              ) and "mpn" not in rename.values():
            rename[col] = "mpn"
        elif ("manufacturer" in cl or cl in ("mfr", "mfr.")) and "manufacturer" not in rename.values():
            rename[col] = "manufacturer"
        elif ("digikey" in cl or "digi-key" in cl) and "pn" in cl and "digikey_pn" not in rename.values():
            rename[col] = "digikey_pn"
        elif "mouser" in cl and "pn" in cl and "mouser_pn" not in rename.values():
            rename[col] = "mouser_pn"
        elif "lcsc" in cl and "lcsc_pn" not in rename.values():
            rename[col] = "lcsc_pn"
        elif "description" in cl and "description" not in rename.values():
            rename[col] = "description"

    df = df.rename(columns=rename)

    for req in ("references", "value", "footprint"):
        if req not in df.columns:
            raise ValueError(
                f"Required column '{req}' not found. Detected columns: {list(df.columns)}"
            )

    def _apply_map(fp: str) -> str:
        s = _strip_prefix(fp).strip()
        if footprint_map:
            return footprint_map.get(s, s)
        return s

    df["footprint"] = df["footprint"].astype(str).apply(_apply_map)
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

        sorted_refs = _sort_refs(all_refs)
        refs_str = _compress_refs(sorted_refs) if compress_refs else ", ".join(sorted_refs)
        rows.append({
            "references":   refs_str,
            "qty":          qty,
            "value":        value,
            "footprint":    footprint,
            "mpn":          _first("mpn"),
            "manufacturer": _first("manufacturer"),
            "packaging":    "Cut Tape",
            "description":  _first("description"),
            "stock":        "",
            "digikey_pn":   _first("digikey_pn"),
            "mouser_pn":    _first("mouser_pn"),
            "lcsc_pn":      _first("lcsc_pn"),
            "notes":        _first("notes"),
            "status":       "red",
            "status_reason": "",
        })

    return rows
