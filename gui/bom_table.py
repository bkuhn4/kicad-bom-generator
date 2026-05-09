"""Scrollable, in-place-editable BOM preview table built on ttk.Treeview."""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Callable, List, Optional

from core.models import BomRow, PackagingVariant
from .styles import GREEN_LIGHT, WHITE, YELLOW_BG, RED_BG, ORANGE_BG, ROW_HEIGHT

# ------------------------------------------------------------------ #
# Column definitions
# (id, header, default_width, exportable, cell_type)
# cell_type: "text" | "combo_dk" | "combo_mouser" | "readonly"
# ------------------------------------------------------------------ #
COL_DEFS = [
    ("references",   "Reference(s)",  200, True,  "text"),
    ("description",  "Description",   260, True,  "text"),
    ("package",      "Package",       110, True,  "text"),
    ("mf_pn",        "MF Part #",     170, True,  "text"),
    ("manufacturer", "Manufacturer",  150, True,  "text"),
    ("dk_pn",        "DigiKey PN",    195, True,  "text"),
    ("dk_pkg",       "DK Pkg",        135, True,  "combo_dk"),
    ("dk_stock",     "DK Stock",       78, False, "readonly"),
    ("mouser_pn",    "Mouser PN",     195, True,  "text"),
    ("mouser_pkg",   "Mouser Pkg",    135, True,  "combo_mouser"),
    ("mouser_stock", "Mouser Stock",   78, False, "readonly"),
    ("lcsc_pn",      "LCSC PN",       105, True,  "text"),
    ("notes",        "Notes",         150, True,  "text"),
]

_COL_IDS = [c[0] for c in COL_DEFS]
_COL_IDX = {c[0]: i for i, c in enumerate(COL_DEFS)}

# Columns where the user edits plain text via an Entry overlay
_TEXT_FIELD_MAP = {
    "references":   "references",
    "description":  "description",
    "package":      "package",
    "mf_pn":        "mf_part_number",
    "manufacturer": "manufacturer",
    "lcsc_pn":      "lcsc_pn",
    "notes":        "notes",
}


class BomTable(ttk.Frame):
    """Treeview-based BOM table with inline entry / combobox editing."""

    def __init__(
        self,
        parent: tk.Widget,
        on_change: Optional[Callable] = None,
        **kw,
    ) -> None:
        super().__init__(parent, **kw)
        self._rows: List[BomRow] = []
        self._on_change = on_change
        self._active: Optional[tk.Widget] = None
        self._sort_reverse: dict = {}
        self._build()

    # ------------------------------------------------------------------ #
    # Construction
    # ------------------------------------------------------------------ #

    def _build(self) -> None:
        style = ttk.Style()
        style.configure("BOM.Treeview",
                        rowheight=ROW_HEIGHT,
                        font=("Segoe UI", 9))
        style.configure("BOM.Treeview.Heading",
                        font=("Segoe UI", 9, "bold"))
        style.map("BOM.Treeview",
                  background=[("selected", "#C8E6C9")])

        self.tree = ttk.Treeview(
            self, columns=_COL_IDS, show="headings",
            selectmode="extended", style="BOM.Treeview",
        )

        for col_id, header, width, _, _ in COL_DEFS:
            self.tree.heading(
                col_id, text=header,
                command=lambda c=col_id: self._sort_by(c),
            )
            self.tree.column(col_id, width=width, minwidth=40, stretch=False)

        self.tree.tag_configure("even",      background=GREEN_LIGHT)
        self.tree.tag_configure("odd",       background=WHITE)
        self.tree.tag_configure("loading",   background=YELLOW_BG)
        self.tree.tag_configure("not_found", background=RED_BG)
        self.tree.tag_configure("error",     background=ORANGE_BG)
        self.tree.tag_configure("readonly",  foreground="#777777")

        vsb = ttk.Scrollbar(self, orient="vertical",   command=self.tree.yview)
        hsb = ttk.Scrollbar(self, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)

        self.tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")
        self.rowconfigure(0, weight=1)
        self.columnconfigure(0, weight=1)

        self.tree.bind("<Button-1>",        self._on_click)
        self.tree.bind("<Double-Button-1>", self._on_dblclick)
        self.tree.bind("<Escape>",          lambda _: self._close())
        self.tree.bind("<Delete>",          self._on_delete_key)

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #

    def load(self, rows: List[BomRow]) -> None:
        self._rows = rows
        self.refresh_all()

    def refresh_all(self) -> None:
        self._close()
        for iid in self.tree.get_children():
            self.tree.delete(iid)
        for idx, row in enumerate(self._rows):
            self.tree.insert(
                "", "end",
                iid=str(idx),
                values=self._to_values(row),
                tags=(self._row_tag(idx, row),),
            )

    def refresh_row(self, idx: int) -> None:
        iid = str(idx)
        if self.tree.exists(iid):
            row = self._rows[idx]
            self.tree.item(iid,
                           values=self._to_values(row),
                           tags=(self._row_tag(idx, row),))

    def get_rows(self) -> List[BomRow]:
        return self._rows

    def row_count(self) -> int:
        return len(self._rows)

    def missing_lookup_count(self) -> int:
        return sum(
            1 for r in self._rows
            if r.mf_part_number and not r.digikey_variants and not r.mouser_variants
        )

    def selected_indices(self) -> List[int]:
        return [int(iid) for iid in self.tree.selection() if iid.isdigit()]

    # ------------------------------------------------------------------ #
    # Row ↔ values conversion
    # ------------------------------------------------------------------ #

    def _to_values(self, row: BomRow) -> tuple:
        dk_pkg = row.digikey_selected_packaging or (
            row.digikey_variants[0].packaging_type if row.digikey_variants else "")
        m_pkg = row.mouser_selected_packaging or (
            row.mouser_variants[0].packaging_type if row.mouser_variants else "")
        dk_stock = f"{row.digikey_stock:,}" if row.digikey_variants else "—"
        m_stock  = f"{row.mouser_stock:,}"  if row.mouser_variants  else "—"
        return (
            row.references, row.description, row.package,
            row.mf_part_number, row.manufacturer,
            row.digikey_pn, dk_pkg, dk_stock,
            row.mouser_pn,  m_pkg,  m_stock,
            row.lcsc_pn, row.notes,
        )

    def _row_tag(self, idx: int, row: BomRow) -> str:
        status_tags = {
            "loading":   "loading",
            "not_found": "not_found",
            "error":     "error",
        }
        return status_tags.get(row.lookup_status, "even" if idx % 2 == 0 else "odd")

    # ------------------------------------------------------------------ #
    # Click handling
    # ------------------------------------------------------------------ #

    def _on_click(self, event: tk.Event) -> None:
        self._close()
        if self.tree.identify("region", event.x, event.y) != "cell":
            return
        col_sym = self.tree.identify_column(event.x)
        row_iid = self.tree.identify_row(event.y)
        if not row_iid:
            return
        col_idx   = int(col_sym[1:]) - 1
        cell_type = COL_DEFS[col_idx][4]
        if cell_type in ("combo_dk", "combo_mouser"):
            self._open_combo(row_iid, col_sym, col_idx, cell_type)

    def _on_dblclick(self, event: tk.Event) -> None:
        self._close()
        if self.tree.identify("region", event.x, event.y) != "cell":
            return
        col_sym = self.tree.identify_column(event.x)
        row_iid = self.tree.identify_row(event.y)
        if not row_iid:
            return
        col_idx   = int(col_sym[1:]) - 1
        cell_type = COL_DEFS[col_idx][4]
        if cell_type == "text":
            self._open_entry(row_iid, col_sym, col_idx)

    def _on_delete_key(self, event: tk.Event) -> None:
        """Remove selected rows."""
        indices = sorted(self.selected_indices(), reverse=True)
        for idx in indices:
            self._rows.pop(idx)
        # Rebuild with corrected iids
        self.refresh_all()
        if self._on_change:
            self._on_change()

    # ------------------------------------------------------------------ #
    # Overlay: Combobox for packaging columns
    # ------------------------------------------------------------------ #

    def _open_combo(
        self, row_iid: str, col_sym: str, col_idx: int, cell_type: str
    ) -> None:
        bbox = self.tree.bbox(row_iid, col_sym)
        if not bbox:
            return
        x, y, w, h = bbox
        idx = int(row_iid)
        row = self._rows[idx]

        if cell_type == "combo_dk":
            options = row.digikey_packaging_options()
            current = row.digikey_selected_packaging
        else:
            options = row.mouser_packaging_options()
            current = row.mouser_selected_packaging

        if not options:
            return  # no variants fetched yet — user must do a lookup first

        combo = ttk.Combobox(self.tree, values=options, state="readonly")
        combo.set(current if current in options else options[0])
        combo.place(x=x, y=y, width=w, height=h)
        combo.focus_set()
        combo.event_generate("<Button-1>")   # auto-open the dropdown
        self._active = combo

        def on_select(_evt=None) -> None:
            chosen = combo.get()
            if cell_type == "combo_dk":
                row.digikey_selected_packaging = chosen
            else:
                row.mouser_selected_packaging = chosen
            self._sync_tree_row(row_iid)
            self._close()
            if self._on_change:
                self._on_change()

        combo.bind("<<ComboboxSelected>>", on_select)
        combo.bind("<FocusOut>",           lambda _: self._close())

    # ------------------------------------------------------------------ #
    # Overlay: Entry for text columns
    # ------------------------------------------------------------------ #

    def _open_entry(self, row_iid: str, col_sym: str, col_idx: int) -> None:
        bbox = self.tree.bbox(row_iid, col_sym)
        if not bbox:
            return
        x, y, w, h = bbox
        idx     = int(row_iid)
        col_key = COL_DEFS[col_idx][0]
        current = self.tree.item(row_iid, "values")[col_idx]

        var   = tk.StringVar(value=current)
        entry = ttk.Entry(self.tree, textvariable=var, font=("Segoe UI", 9))
        entry.place(x=x, y=y, width=w, height=h)
        entry.focus_set()
        entry.select_range(0, "end")
        self._active = entry

        def commit(_evt=None) -> None:
            self._apply_edit(self._rows[idx], col_key, var.get())
            self._sync_tree_row(row_iid)
            self._close()
            if self._on_change:
                self._on_change()

        entry.bind("<Return>",   commit)
        entry.bind("<Tab>",      commit)
        entry.bind("<FocusOut>", lambda _: self._close())

    # ------------------------------------------------------------------ #
    # Data model writes
    # ------------------------------------------------------------------ #

    def _apply_edit(self, row: BomRow, col_key: str, val: str) -> None:
        if col_key in _TEXT_FIELD_MAP:
            setattr(row, _TEXT_FIELD_MAP[col_key], val)
        elif col_key == "dk_pn":
            self._set_variant_pn(row, "dk", val)
        elif col_key == "mouser_pn":
            self._set_variant_pn(row, "mouser", val)

    def _set_variant_pn(self, row: BomRow, supplier: str, val: str) -> None:
        if supplier == "dk":
            variants = row.digikey_variants
            pkg      = row.digikey_selected_packaging or "Cut Tape (CT)"
        else:
            variants = row.mouser_variants
            pkg      = row.mouser_selected_packaging or "Cut Tape"

        for v in variants:
            if v.packaging_type == pkg:
                v.part_number = val
                return

        new_v = PackagingVariant(pkg, val)
        if supplier == "dk":
            row.digikey_variants           = [new_v]
            row.digikey_selected_packaging = pkg
        else:
            row.mouser_variants            = [new_v]
            row.mouser_selected_packaging  = pkg

    def _sync_tree_row(self, row_iid: str) -> None:
        idx = int(row_iid)
        self.tree.item(row_iid, values=self._to_values(self._rows[idx]))

    # ------------------------------------------------------------------ #
    # Overlay cleanup
    # ------------------------------------------------------------------ #

    def _close(self) -> None:
        if self._active:
            try:
                self._active.destroy()
            except tk.TclError:
                pass
            self._active = None

    # ------------------------------------------------------------------ #
    # Column sort (click heading)
    # ------------------------------------------------------------------ #

    def _sort_by(self, col_id: str) -> None:
        col_idx  = _COL_IDX[col_id]
        rev      = self._sort_reverse.get(col_id, False)
        children = list(self.tree.get_children())

        def key(iid: str):
            v = self.tree.item(iid, "values")[col_idx]
            try:
                return (0, int(str(v).replace(",", "").replace("—", "0")))
            except ValueError:
                return (1, str(v).lower())

        children.sort(key=key, reverse=rev)
        for pos, iid in enumerate(children):
            self.tree.move(iid, "", pos)
            parity = "even" if pos % 2 == 0 else "odd"
            row_idx = int(iid)
            tag = {
                "loading":   "loading",
                "not_found": "not_found",
                "error":     "error",
            }.get(self._rows[row_idx].lookup_status, parity)
            self.tree.item(iid, tags=(tag,))

        self._sort_reverse[col_id] = not rev
        # Update heading arrow indicator
        for c_id, header, _, _, _ in COL_DEFS:
            arrow = ""
            if c_id == col_id:
                arrow = " ▲" if not rev else " ▼"
            self.tree.heading(c_id, text=header + arrow)
