from __future__ import annotations
import csv
import re
from typing import List

from .models import BomRow, PackagingVariant


def format_references(ref_str: str) -> str:
    """Collapse consecutive designator runs: C38,C39,C40 → C38-C40 (threshold: 3+)."""
    if not ref_str:
        return ""

    parts = [p.strip() for p in ref_str.split(",") if p.strip()]

    parsed = []
    for p in parts:
        m = re.match(r"^([A-Za-z]+)(\d+)$", p)
        parsed.append((m.group(1), int(m.group(2)), p) if m else (None, None, p))

    result: List[str] = []
    group: List[tuple] = []

    def flush(g: List[tuple]) -> None:
        if len(g) >= 3:
            result.append(f"{g[0][2]}-{g[-1][2]}")
        else:
            result.extend(x[2] for x in g)

    for item in parsed:
        if item[0] is None:
            flush(group)
            group = []
            result.append(item[2])
        elif not group or (item[0] == group[-1][0] and item[1] == group[-1][1] + 1):
            group.append(item)
        else:
            flush(group)
            group = [item]

    flush(group)
    return ", ".join(result)


def _get(row: dict, *keys: str) -> str:
    for k in keys:
        v = row.get(k, "").strip()
        if v:
            return v
    return ""


def parse_csv(path: str) -> List[BomRow]:
    rows: List[BomRow] = []
    with open(path, encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for csv_row in reader:
            mf_pn = _get(csv_row,
                         "Manufacturer PN", "MPN", "Manufacturer Part Number",
                         "MF Part Number", "Part Number")
            dk_pn_raw = _get(csv_row,
                             "Digikey PN", "DigiKey PN", "Digi-Key PN",
                             "Digikey", "DigiKey")
            mouser_pn_raw = _get(csv_row, "Mouser PN", "Mouser")

            bom_row = BomRow(
                references=format_references(
                    _get(csv_row, "Reference", "References", "Ref", "Designator")),
                description=_get(csv_row, "Description", "Value", "Comment"),
                package=_get(csv_row, "Package", "Footprint", "Case/Package"),
                mf_part_number=mf_pn,
                manufacturer=_get(csv_row, "Manufacturer", "Mfr", "Mfg"),
                lcsc_pn=_get(csv_row, "LCSC PN", "LCSC"),
                notes=_get(csv_row, "Notes", "Note"),
            )

            if dk_pn_raw:
                bom_row.digikey_variants = [PackagingVariant("Cut Tape (CT)", dk_pn_raw)]
                bom_row.digikey_selected_packaging = "Cut Tape (CT)"

            if mouser_pn_raw:
                bom_row.mouser_variants = [PackagingVariant("Cut Tape", mouser_pn_raw)]
                bom_row.mouser_selected_packaging = "Cut Tape"

            rows.append(bom_row)
    return rows
