"""API key configuration dialog."""
from __future__ import annotations

import threading
import tkinter as tk
from tkinter import ttk

import requests
import os
import digikey
from digikey.v3.productinformation import KeywordSearchRequest
from mouser.api import MouserPartSearchRequest

from core import config
from .styles import GREEN_DARK, FONT_BOLD


class SettingsDialog(tk.Toplevel):
    def __init__(self, parent: tk.Widget) -> None:
        super().__init__(parent)
        self.title("Settings")
        self.resizable(False, False)
        self.transient(parent)
        self._cfg = config.load()
        self._build()
        self.grab_set()

    # ------------------------------------------------------------------ #
    # Build
    # ------------------------------------------------------------------ #

    def _build(self) -> None:
        nb = ttk.Notebook(self)
        nb.pack(fill="both", expand=True, padx=10, pady=8)

        self._build_api_tab(nb)
        self._build_prefs_tab(nb)
        self._build_export_tab(nb)

        sep = ttk.Separator(self, orient="horizontal")
        sep.pack(fill="x", padx=10)

        self._status_var = tk.StringVar()
        ttk.Label(self, textvariable=self._status_var, foreground="#555",
                  font=("Segoe UI", 9)).pack(padx=10, pady=(4, 0))

        btn_row = ttk.Frame(self)
        btn_row.pack(pady=8)
        ttk.Button(btn_row, text="Save",   command=self._save).pack(side="left", padx=6)
        ttk.Button(btn_row, text="Cancel", command=self.destroy).pack(side="left", padx=6)

    def _build_api_tab(self, nb: ttk.Notebook) -> None:
        frame = ttk.Frame(nb)
        nb.add(frame, text="API Keys")

        pad = {"padx": 10, "pady": 5}

        # --- DigiKey ---
        ttk.Label(frame, text="DigiKey", font=FONT_BOLD).grid(
            row=0, column=0, columnspan=3, sticky="w", padx=10, pady=(10, 2))

        ttk.Label(frame, text="Client ID:").grid(
            row=1, column=0, sticky="e", **pad)
        self._dk_id = ttk.Entry(frame, width=40)
        self._dk_id.insert(0, self._cfg.get("digikey_client_id", ""))
        self._dk_id.grid(row=1, column=1, sticky="ew", **pad)

        ttk.Label(frame, text="Client Secret:").grid(
            row=2, column=0, sticky="e", **pad)
        self._dk_secret = ttk.Entry(frame, width=40, show="•")
        self._dk_secret.insert(0, self._cfg.get("digikey_client_secret", ""))
        self._dk_secret.grid(row=2, column=1, sticky="ew", **pad)

        ttk.Button(frame, text="Test", command=self._test_dk).grid(
            row=1, column=2, rowspan=2, padx=(0, 10))

        ttk.Separator(frame, orient="horizontal").grid(
            row=3, column=0, columnspan=3, sticky="ew", padx=10, pady=6)

        # --- Mouser ---
        ttk.Label(frame, text="Mouser", font=FONT_BOLD).grid(
            row=4, column=0, columnspan=3, sticky="w", padx=10, pady=(2, 2))

        ttk.Label(frame, text="API Key:").grid(
            row=5, column=0, sticky="e", **pad)
        self._mouser_key = ttk.Entry(frame, width=40, show="•")
        self._mouser_key.insert(0, self._cfg.get("mouser_api_key", ""))
        self._mouser_key.grid(row=5, column=1, sticky="ew", **pad)

        ttk.Button(frame, text="Test", command=self._test_mouser).grid(
            row=5, column=2, padx=(0, 10))

        ttk.Label(
            frame,
            text="LCSC lookups are performed automatically (no key required).",
            foreground="#777", font=("Segoe UI", 8),
        ).grid(row=6, column=0, columnspan=3, sticky="w", padx=10, pady=(6, 4))

        frame.columnconfigure(1, weight=1)

    def _build_prefs_tab(self, nb: ttk.Notebook) -> None:
        frame = ttk.Frame(nb)
        nb.add(frame, text="Preferences")

        pad = {"padx": 10, "pady": 6}

        ttk.Label(frame, text="Default packaging preference:").grid(
            row=0, column=0, sticky="e", **pad)
        self._pref_pkg = ttk.Combobox(
            frame,
            values=["Tape & Reel (TR)", "Cut Tape (CT)", "DigiReel®"],
            state="readonly", width=22,
        )
        self._pref_pkg.set(self._cfg.get("preferred_packaging", "Cut Tape (CT)"))
        self._pref_pkg.grid(row=0, column=1, sticky="w", **pad)

        ttk.Label(
            frame,
            text=(
                "When a part has multiple packaging options, the lookup will\n"
                "pre-select this packaging type if available."
            ),
            foreground="#555", font=("Segoe UI", 8),
        ).grid(row=1, column=0, columnspan=2, sticky="w", padx=10)

    def _build_export_tab(self, nb: ttk.Notebook) -> None:
        frame = ttk.Frame(nb)
        nb.add(frame, text="Export")
        
        ttk.Label(frame, text="Select columns to include in Excel export:", font=FONT_BOLD).pack(anchor="w", padx=10, pady=(10, 5))
        
        self._export_vars = {}
        defaults = config.DEFAULTS.get("export_columns", {})
        saved_cols = self._cfg.get("export_columns", {})
        
        cols_frame = ttk.Frame(frame)
        cols_frame.pack(fill="both", expand=True, padx=20, pady=5)
        
        for col_name in defaults.keys():
            var = tk.BooleanVar(value=saved_cols.get(col_name, defaults[col_name]))
            self._export_vars[col_name] = var
            ttk.Checkbutton(cols_frame, text=col_name, variable=var).pack(anchor="w", pady=2)

    # ------------------------------------------------------------------ #
    # Save
    # ------------------------------------------------------------------ #

    def _save(self) -> None:
        self._cfg["digikey_client_id"]     = self._dk_id.get().strip()
        self._cfg["digikey_client_secret"] = self._dk_secret.get().strip()
        self._cfg["mouser_api_key"]        = self._mouser_key.get().strip()
        self._cfg["preferred_packaging"]   = self._pref_pkg.get()
        
        # Save export column preferences
        self._cfg["export_columns"] = {col: var.get() for col, var in self._export_vars.items()}
        
        config.save(self._cfg)
        self.destroy()

    # ------------------------------------------------------------------ #
    # API tests
    # ------------------------------------------------------------------ #

    def _test_dk(self) -> None:
        self._status_var.set("Testing DigiKey…")
        cid  = self._dk_id.get().strip()
        csec = self._dk_secret.get().strip()

        def run() -> None:
            if not cid or not csec:
                self.after(0, lambda: self._status_var.set("✗ DigiKey FAILED — Please enter credentials"))
                return
            
            # Use digikey-api to test by searching a common keyword
            os.environ['DIGIKEY_CLIENT_ID'] = cid
            os.environ['DIGIKEY_CLIENT_SECRET'] = csec
            os.environ['DIGIKEY_CLIENT_SANDBOX'] = 'False'
            
            try:
                # Searching for "resistor" with 1 record count to validate credentials
                req = KeywordSearchRequest(keywords="resistor", record_count=1)
                result = digikey.keyword_search(body=req)
                
                # If we get here without an exception, token auth was successful
                msg = "✓ DigiKey OK" 
            except Exception as e:
                msg = "✗ DigiKey FAILED — check credentials"
                
            self.after(0, lambda: self._status_var.set(msg))

        threading.Thread(target=run, daemon=True).start()

    def _test_mouser(self) -> None:
        self._status_var.set("Testing Mouser…")
        key = self._mouser_key.get().strip()

        def run() -> None:
            if not key:
                self.after(0, lambda: self._status_var.set("✗ Mouser FAILED — Please enter API Key"))
                return
            
            os.environ['MOUSER_PART_API_KEY'] = key
            
            try:
                req = MouserPartSearchRequest('keyword')
                if req.part_search("resistor"):
                    data = req.get_response()
                    if "Errors" in data and any(e.get("Code") == "Invalid" for e in data.get("Errors", [])):
                        msg = "✗ Mouser FAILED — Invalid API Key"
                    else:
                        msg = "✓ Mouser OK"
                else:
                    msg = "✗ Mouser FAILED — connection error"
            except Exception:
                msg = "✗ Mouser FAILED — check credentials"
            self.after(0, lambda: self._status_var.set(msg))

        threading.Thread(target=run, daemon=True).start()
        self._status_var.set("Testing Mouser…")
        key = self._mouser_key.get().strip()

        def run() -> None:
            try:
                resp = requests.post(
                    f"https://api.mouser.com/api/v1/search/keyword?apiKey={key}",
                    json={"SearchByKeywordRequest": {
                        "keyword": "test", "records": 1,
                        "startingRecord": 0, "searchOptions": "",
                    }},
                    headers={"Content-Type": "application/json"},
                    timeout=8,
                )
                ok = resp.status_code == 200
                msg = "✓ Mouser OK" if ok else f"✗ Mouser FAILED ({resp.status_code})"
            except Exception as exc:
                msg = f"✗ Mouser error: {exc}"
            self.after(0, lambda: self._status_var.set(msg))

        threading.Thread(target=run, daemon=True).start()
