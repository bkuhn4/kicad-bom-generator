"""Main application window for Auto BOM Generator."""
from __future__ import annotations

import os
import queue
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from typing import List

from core import bom_parser, config, excel_exporter, part_lookup
from core.models import BomRow, PackagingVariant
from .bom_table import BomTable
from .settings_dialog import SettingsDialog
from .styles import GREEN_DARK, GREEN_BTN_FG, FONT_BOLD


class App(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("Auto BOM Generator")
        self.geometry("1340x740")
        self.minsize(900, 520)

        self._csv_path    = ""
        self._lookup_q: queue.Queue = queue.Queue()
        self._lookup_total = 0
        self._lookup_done  = 0

        self._build_menu()
        self._build_toolbar()
        self._build_table()
        self._build_statusbar()
        self._poll_queue()

    # ------------------------------------------------------------------ #
    # Menu
    # ------------------------------------------------------------------ #

    def _build_menu(self) -> None:
        bar = tk.Menu(self)
        self.configure(menu=bar)

        file_m = tk.Menu(bar, tearoff=False)
        
        self._recent_menu = tk.Menu(file_m, tearoff=False)
        self._update_recent_menu()
        file_m.add_cascade(label="Load CSV…", menu=self._recent_menu)
        
        file_m.add_command(label="Export to Excel…", command=self._export,    accelerator="Ctrl+E")
        file_m.add_separator()
        file_m.add_command(label="Settings…",        command=self._settings)
        file_m.add_separator()
        file_m.add_command(label="Exit",             command=self.destroy)
        bar.add_cascade(label="File", menu=file_m)

        tools_m = tk.Menu(bar, tearoff=False)
        tools_m.add_command(label="Lookup All Missing Parts", command=self._lookup_all)
        tools_m.add_command(label="Lookup Selected Rows",     command=self._lookup_selected)
        tools_m.add_separator()
        tools_m.add_command(label="Clear All Supplier PNs",   command=self._clear_pns)
        bar.add_cascade(label="Tools", menu=tools_m)

        help_m = tk.Menu(bar, tearoff=False)
        help_m.add_command(label="About", command=self._about)
        bar.add_cascade(label="Help", menu=help_m)

        self.bind("<Control-o>", lambda _: self._load_csv())
        self.bind("<Control-e>", lambda _: self._export())

    def _update_recent_menu(self) -> None:
        self._recent_menu.delete(0, "end")
        self._recent_menu.add_command(label="Browse…", command=self._load_csv, accelerator="Ctrl+O")
        
        cfg = config.load()
        recent = cfg.get("recent_files", [])
        
        # Only add files that still exist and clean up the list
        valid_recent = []
        for p in recent:
            if os.path.exists(p):
                valid_recent.append(p)
                
        if valid_recent != recent:
            cfg["recent_files"] = valid_recent
            config.save(cfg)
            recent = valid_recent
            
        if recent:
            self._recent_menu.add_separator()
            for p in recent:
                self._recent_menu.add_command(label=p, command=lambda p=p: self._load_csv(p))

    # ------------------------------------------------------------------ #
    # Toolbar
    # ------------------------------------------------------------------ #

    def _build_toolbar(self) -> None:
        bar = ttk.Frame(self, relief="flat")
        bar.pack(side="top", fill="x", padx=6, pady=(6, 2))

        self._btn_load = ttk.Button(bar, text="Load CSV…", command=self._load_csv)
        self._btn_load.pack(side="left", padx=2)

        ttk.Separator(bar, orient="vertical").pack(side="left", fill="y", padx=5, pady=2)

        self._btn_lookup = ttk.Button(
            bar, text="Lookup Parts", command=self._lookup_all, state="disabled")
        self._btn_lookup.pack(side="left", padx=2)

        self._btn_lookup_sel = ttk.Button(
            bar, text="Lookup Selected", command=self._lookup_selected, state="disabled")
        self._btn_lookup_sel.pack(side="left", padx=2)

        ttk.Separator(bar, orient="vertical").pack(side="left", fill="y", padx=5, pady=2)

        self._btn_export = ttk.Button(
            bar, text="Export to Excel…", command=self._export, state="disabled")
        self._btn_export.pack(side="left", padx=2)

        ttk.Separator(bar, orient="vertical").pack(side="left", fill="y", padx=5, pady=2)

        ttk.Button(bar, text="Settings…", command=self._settings).pack(side="left", padx=2)

        self._file_lbl = ttk.Label(bar, text="No file loaded", foreground="#888")
        self._file_lbl.pack(side="left", padx=14)

        # API key status dots (right side)
        indicator_frame = ttk.Frame(bar)
        indicator_frame.pack(side="right", padx=10)
        ttk.Label(indicator_frame, text="DK:").pack(side="left")
        self._dk_dot = ttk.Label(indicator_frame, text="●", foreground="gray")
        self._dk_dot.pack(side="left", padx=(1, 8))
        ttk.Label(indicator_frame, text="Mouser:").pack(side="left")
        self._mouser_dot = ttk.Label(indicator_frame, text="●", foreground="gray")
        self._mouser_dot.pack(side="left", padx=(1, 0))
        self._refresh_dots()

    # ------------------------------------------------------------------ #
    # Table
    # ------------------------------------------------------------------ #

    def _build_table(self) -> None:
        self._table = BomTable(self, on_change=self._on_change)
        self._table.pack(fill="both", expand=True, padx=6, pady=2)

    # ------------------------------------------------------------------ #
    # Status bar
    # ------------------------------------------------------------------ #

    def _build_statusbar(self) -> None:
        bar = ttk.Frame(self, relief="groove", border=1)
        bar.pack(side="bottom", fill="x")

        self._status_var = tk.StringVar(value="Ready — load a KiCad BOM CSV to begin.")
        ttk.Label(bar, textvariable=self._status_var, anchor="w").pack(
            side="left", padx=8, pady=2)

        self._prog_lbl = ttk.Label(bar, text="", foreground="#555")
        self._prog_lbl.pack(side="right", padx=4)

        self._progress = ttk.Progressbar(bar, length=180, mode="determinate")
        self._progress.pack(side="right", padx=(0, 4), pady=2)

    # ------------------------------------------------------------------ #
    # File actions
    # ------------------------------------------------------------------ #

    def _load_csv(self, path: str | None = None) -> None:
        if not path:
            path = filedialog.askopenfilename(
                title="Select KiCad BOM CSV",
                filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
            )
        if not path:
            return
        
        # Verify file exists if passed from recent files
        if not os.path.exists(path):
            messagebox.showerror("File Not Found", f"The file no longer exists at:\n{path}")
            self._update_recent_menu() # cleans up the missing file
            return
            
        try:
            rows = bom_parser.parse_csv(path)
        except Exception as exc:
            messagebox.showerror("Parse Error", f"Could not read CSV:\n{exc}")
            return

        self._csv_path = path
        self._table.load(rows)
        self._btn_lookup["state"]     = "normal"
        self._btn_lookup_sel["state"] = "normal"
        self._btn_export["state"]     = "normal"
        self._file_lbl["text"]        = os.path.basename(path)

        n       = self._table.row_count()
        missing = self._table.missing_lookup_count()
        self._set_status(
            f"{n} row{'s' if n != 1 else ''} loaded  •  "
            f"{missing} part{'s' if missing != 1 else ''} missing supplier PNs  •  "
            "Double-click a cell to edit"
        )
        
        # Add to recents
        cfg = config.load()
        recent = cfg.get("recent_files", [])
        if path in recent:
            recent.remove(path)
        recent.insert(0, path)
        recent = recent[:10]  # Keep 10 max
        cfg["recent_files"] = recent
        config.save(cfg)
        self._update_recent_menu()

    def _export(self) -> None:
        rows = self._table.get_rows()
        if not rows:
            messagebox.showwarning("No Data", "Load a CSV first.")
            return
        stem = (os.path.splitext(os.path.basename(self._csv_path))[0]
                if self._csv_path else "BOM")
        path = filedialog.asksaveasfilename(
            title="Export BOM to Excel",
            initialfile=f"{stem}_formatted.xlsx",
            defaultextension=".xlsx",
            filetypes=[("Excel files", "*.xlsx"), ("All files", "*.*")],
        )
        if not path:
            return
        try:
            excel_exporter.export(rows, path)
            self._set_status(f"Exported → {os.path.basename(path)}")
        except Exception as exc:
            messagebox.showerror("Export Error", str(exc))

    # ------------------------------------------------------------------ #
    # Part lookup
    # ------------------------------------------------------------------ #

    def _lookup_all(self) -> None:
        rows   = self._table.get_rows()
        targets = [
            (i, r) for i, r in enumerate(rows)
            if r.mf_part_number and (not r.digikey_variants or not r.mouser_variants)
        ]
        self._run_lookup(targets)

    def _lookup_selected(self) -> None:
        rows    = self._table.get_rows()
        indices = self._table.selected_indices()
        targets = [(i, rows[i]) for i in indices if rows[i].mf_part_number]
        self._run_lookup(targets)

    def _run_lookup(self, targets: list) -> None:
        if not targets:
            messagebox.showinfo("Lookup", "Nothing to look up.")
            return

        cfg      = config.load()
        dk_id    = cfg.get("digikey_client_id", "")
        dk_sec   = cfg.get("digikey_client_secret", "")
        m_key    = cfg.get("mouser_api_key", "")
        pref_pkg = cfg.get("preferred_packaging", "Tape & Reel (TR)")

        if not dk_id and not m_key:
            if messagebox.askyesno("No API Keys",
                                   "No API keys configured.\nOpen Settings to add them?"):
                self._settings()
            return

        self._lookup_total = len(targets)
        self._lookup_done  = 0
        self._progress["maximum"] = self._lookup_total
        self._progress["value"]   = 0
        self._btn_lookup["state"]     = "disabled"
        self._btn_lookup_sel["state"] = "disabled"
        self._set_status(f"Looking up {self._lookup_total} part(s)…")

        for _, row in targets:
            row.lookup_status = "loading"
        self._table.refresh_all()

        def worker(idx: int, row: BomRow) -> None:
            try:
                if dk_id and not row.digikey_variants:
                    dk_variants = part_lookup.lookup_digikey(
                        row.mf_part_number, dk_id, dk_sec, pref_pkg)
                    if dk_variants:
                        row.digikey_variants = dk_variants
                        row.digikey_selected_packaging = (
                            next((v.packaging_type for v in dk_variants
                                  if v.packaging_type == pref_pkg),
                                 dk_variants[0].packaging_type)
                        )

                if m_key and not row.mouser_variants:
                    m_variants = part_lookup.lookup_mouser(
                        row.mf_part_number, m_key, pref_pkg)
                    if m_variants:
                        row.mouser_variants = m_variants
                        row.mouser_selected_packaging = (
                            next((v.packaging_type for v in m_variants
                                  if "reel" in v.packaging_type.lower()),
                                 m_variants[0].packaging_type)
                        )

                if not row.lcsc_pn:
                    lcsc_pn, lcsc_stock = part_lookup.lookup_lcsc(row.mf_part_number)
                    if lcsc_pn:
                        row.lcsc_pn    = lcsc_pn
                        row.lcsc_stock = lcsc_stock

                row.lookup_status = (
                    "found" if (row.digikey_variants or row.mouser_variants) else "not_found"
                )
            except Exception as exc:
                row.lookup_status = "error"
                row.lookup_error  = str(exc)

            self._lookup_q.put(idx)

        for idx, row in targets:
            threading.Thread(target=worker, args=(idx, row), daemon=True).start()

    def _poll_queue(self) -> None:
        try:
            while True:
                idx = self._lookup_q.get_nowait()
                self._table.refresh_row(idx)
                self._lookup_done += 1
                self._progress["value"] = self._lookup_done
                self._prog_lbl["text"]  = f"{self._lookup_done}/{self._lookup_total}"

                if self._lookup_done >= self._lookup_total:
                    self._btn_lookup["state"]     = "normal"
                    self._btn_lookup_sel["state"] = "normal"
                    missing = self._table.missing_lookup_count()
                    self._prog_lbl["text"] = ""
                    self._progress["value"] = 0
                    self._set_status(
                        f"Lookup complete — {self._lookup_total} checked, "
                        f"{missing} part(s) still not found"
                    )
        except queue.Empty:
            pass
        self.after(80, self._poll_queue)

    # ------------------------------------------------------------------ #
    # Other toolbar actions
    # ------------------------------------------------------------------ #

    def _clear_pns(self) -> None:
        if not self._table.get_rows():
            return
        if not messagebox.askyesno("Clear", "Clear all DigiKey / Mouser / LCSC part numbers?"):
            return
        for row in self._table.get_rows():
            row.digikey_variants           = []
            row.digikey_selected_packaging = ""
            row.mouser_variants            = []
            row.mouser_selected_packaging  = ""
            row.lcsc_pn    = ""
            row.lcsc_stock = 0
            row.lookup_status = "idle"
        self._table.refresh_all()

    def _settings(self) -> None:
        dlg = SettingsDialog(self)
        self.wait_window(dlg)
        self._refresh_dots()

    def _about(self) -> None:
        messagebox.showinfo(
            "About Auto BOM Generator",
            "Auto BOM Generator\n\n"
            "Converts KiCad BOM CSVs into formatted Excel spreadsheets.\n"
            "Supports automatic DigiKey, Mouser, and LCSC part number lookup.\n\n"
            "• Double-click any cell to edit\n"
            "• Click a packaging cell to open its dropdown\n"
            "• Delete key removes selected rows\n"
            "• Click any column header to sort",
        )

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #

    def _on_change(self) -> None:
        pass  # hook for dirty-state tracking if needed

    def _set_status(self, msg: str) -> None:
        self._status_var.set(msg)

    def _refresh_dots(self) -> None:
        cfg = config.load()
        self._dk_dot["foreground"]    = GREEN_DARK if cfg.get("digikey_client_id")  else "gray"
        self._mouser_dot["foreground"]= GREEN_DARK if cfg.get("mouser_api_key")     else "gray"
