from __future__ import annotations

from datetime import datetime
from pathlib import Path
import openpyxl
import csv
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

EXPORT_COLUMNS = [
    ("qty",          "Quantity"),
    ("references",   "References"),
    ("value",        "Value"),
    ("description",  "Description"),
    ("footprint",    "Footprint"),
    ("packaging",    "Packaging"),
    ("mpn",          "MPN"),
    ("manufacturer", "Manufacturer"),
    ("digikey_pn",   "DigiKey PN"),
    ("stock",        "DigiKey Stock"),
    ("mouser_pn",    "Mouser PN"),
    ("lcsc_pn",      "LCSC PN"),
    ("notes",        "Notes"),
]


# ── color helpers ────────────────────────────────────────────────────────────

def _lighten(hex6: str, factor: float) -> str:
    """Blend hex6 toward white by factor (0 = unchanged, 1 = white)."""
    r, g, b = int(hex6[0:2], 16), int(hex6[2:4], 16), int(hex6[4:6], 16)
    r = min(255, int(r + (255 - r) * factor))
    g = min(255, int(g + (255 - g) * factor))
    b = min(255, int(b + (255 - b) * factor))
    return f"{r:02X}{g:02X}{b:02X}"


def _text_on(hex6: str) -> str:
    """Return FFFFFF or 000000 for legible text on a background."""
    r, g, b = int(hex6[0:2], 16), int(hex6[2:4], 16), int(hex6[4:6], 16)
    return "FFFFFF" if (0.299 * r + 0.587 * g + 0.114 * b) < 140 else "000000"


# ── main export ──────────────────────────────────────────────────────────────

def export_bom(rows: list[dict], filepath: str | Path, header_color: str = "4F6228",
               columns: list[tuple] | None = None,
               project_name: str = "", revision: str = "",
               show_title: bool = True, show_footer: bool = True):
    cols = columns if columns is not None else EXPORT_COLUMNS
    n_cols = len(cols)
    hex6 = header_color.lstrip("#").upper()
    stripe_hex = _lighten(hex6, 0.72)

    bside = Side(style="thin", color=hex6)
    cell_border = Border(left=bside, right=bside, top=bside, bottom=bside)

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "BOM"

    row_offset = 0

    # ── title row ────────────────────────────────────────────────
    if show_title and (project_name or revision):
        row_offset = 1
        if n_cols > 1:
            ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=n_cols - 1)
        tc = ws.cell(row=1, column=1, value=project_name)
        tc.font = Font(bold=True, size=14)
        tc.alignment = Alignment(horizontal="center", vertical="center")
        if revision:
            rc = ws.cell(row=1, column=n_cols, value=f"Rev {revision}")
            rc.font = Font(bold=True, size=11)
            rc.alignment = Alignment(horizontal="right", vertical="center")
        ws.row_dimensions[1].height = 28

    # ── column header row ────────────────────────────────────────
    hdr_row   = row_offset + 1
    hdr_fill  = PatternFill("solid", fgColor=hex6)
    hdr_font  = Font(bold=True, color=_text_on(hex6), size=11)
    hdr_align = Alignment(horizontal="left", vertical="center")

    for col, (_, label) in enumerate(cols, 1):
        c = ws.cell(row=hdr_row, column=col, value=label)
        c.fill      = hdr_fill
        c.font      = hdr_font
        c.alignment = hdr_align
        c.border    = cell_border

    ws.row_dimensions[hdr_row].height = 22

    # ── data rows ────────────────────────────────────────────────
    stripe_fill  = PatternFill("solid", fgColor=stripe_hex)
    white_fill   = PatternFill("solid", fgColor="FFFFFF")
    data_align   = Alignment(vertical="center", wrap_text=False)
    center_align = Alignment(horizontal="center", vertical="center", wrap_text=False)
    data_font    = Font(size=10)

    for ri, row in enumerate(rows, hdr_row + 1):
        fill = stripe_fill if ri % 2 == 0 else white_fill
        for ci, (key, _) in enumerate(cols, 1):
            c = ws.cell(row=ri, column=ci, value=row.get(key, ""))
            c.fill      = fill
            c.border    = cell_border
            c.alignment = center_align if key == "qty" else data_align
            c.font      = data_font

    # ── footer row ───────────────────────────────────────────────
    if show_footer:
        now = datetime.now()
        t = now.strftime("%I:%M %p").lstrip("0")
        date_str = f"{now.month}/{now.day}/{now.year}"
        footer_row = hdr_row + len(rows) + 1
        if n_cols > 1:
            ws.merge_cells(start_row=footer_row, start_column=1,
                           end_row=footer_row, end_column=n_cols)
        fc = ws.cell(row=footer_row, column=1, value=f"Created: {t} {date_str}")
        fc.font = Font(italic=True, size=9, color="666666")
        fc.alignment = Alignment(horizontal="left", vertical="center")

    # ── auto-width ───────────────────────────────────────────────
    for ci in range(1, n_cols + 1):
        col_letter = get_column_letter(ci)
        max_len = max(
            (len(str(ws.cell(row=r, column=ci).value or "")) for r in range(1, ws.max_row + 1)),
            default=0,
        )
        ws.column_dimensions[col_letter].width = min(max_len * 1.1 + 4, 80)

    ws.freeze_panes = f"A{hdr_row + 1}"
    wb.save(filepath)

def export_csv(rows: list[dict], filepath: str | Path, columns: list[tuple] | None = None):
    cols = columns if columns is not None else EXPORT_COLUMNS
    keys = [k for k, _ in cols]
    labels = [l for _, l in cols]
    
    with open(filepath, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(labels)
        for row in rows:
            writer.writerow([row.get(k, "") for k in keys])

