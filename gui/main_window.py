from __future__ import annotations

from pathlib import Path

from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QSplitter, QToolBar, QStatusBar,
    QFileDialog, QMessageBox, QTableView, QTableWidget, QTableWidgetItem,
    QHeaderView, QMenu, QToolButton, QPushButton,
    QSizePolicy, QLabel, QLineEdit,
)
from PyQt6.QtCore import QModelIndex, QUrl, Qt
from PyQt6.QtGui import QAction, QDesktopServices

from core.config_manager import load_config, save_config
from core.database import init_db, lookup_part, save_part, save_lcsc_pn
from core.bom_parser import parse_bom, expand_refs_string, _sort_refs, _compress_refs
from core.exporter import export_bom, export_csv, EXPORT_COLUMNS
from core.footprint_map import load_footprint_map, save_footprint_map
from core.status import recalc_status
from api.digikey import DigiKeyClient
from api.mouser import MouserClient
from gui.bom_table import BomTableModel, PackagingDelegate, COLUMNS
from gui.search_dialog import SearchAssignDialog
from gui.settings_dialog import SettingsDialog
from gui.workers import FetchAllWorker

_GITHUB_URL = "https://github.com/bkuhn4/kicad-bom-generator"
_MAX_RECENT = 8


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("KiCad BOM Enhancer & Procurement Tool")
        self.setMinimumSize(1280, 720)

        self.config = load_config()
        self._footprint_map: dict = load_footprint_map()
        init_db()
        self._dk = DigiKeyClient(self.config)
        self._mu = MouserClient(self.config)
        self._fetch_worker: FetchAllWorker | None = None
        self._single_workers: list[FetchAllWorker] = []
        self._recent_actions: list[QAction] = []
        self._file_recent_actions: list[QAction] = []
        self._current_csv_path: str | None = None

        self._build_ui()
        self._build_menu()
        self._build_toolbar()
        self._apply_column_visibility()
        self._restore_column_order()
        self.view.horizontalHeader().sectionMoved.connect(self._on_column_moved)

    # ── UI setup ──────────────────────────────────────────────────────────────

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        vbox = QVBoxLayout(central)
        vbox.setContentsMargins(4, 4, 4, 4)

        self.model = BomTableModel()
        self.model.key_cell_edited.connect(self._on_key_cell_edited)
        self.model.footprint_edited.connect(self._on_footprint_edited)

        self.view = QTableView()
        self.view.setModel(self.model)
        self.view.setSelectionBehavior(QTableView.SelectionBehavior.SelectRows)
        self.view.setAlternatingRowColors(False)
        self.view.setEditTriggers(
            QTableView.EditTrigger.DoubleClicked |
            QTableView.EditTrigger.EditKeyPressed |
            QTableView.EditTrigger.AnyKeyPressed |
            QTableView.EditTrigger.SelectedClicked
        )
        self.view.clicked.connect(self._on_single_click)
        self.view.doubleClicked.connect(self._on_double_click)

        hdr = self.view.horizontalHeader()
        hdr.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        hdr.setSectionsMovable(True)
        hdr.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        hdr.customContextMenuRequested.connect(self._on_header_context_menu)

        _widths = {
            "status": 28, "qty": 48, "references": 130, "value": 80,
            "description": 220, "footprint": 160, "packaging": 100,
            "mpn": 150, "manufacturer": 130, "digikey_pn": 130,
            "stock": 80, "mouser_pn": 120, "lcsc_pn": 90, "notes": 120,
        }
        for i, (key, _) in enumerate(COLUMNS):
            self.view.setColumnWidth(i, _widths.get(key, 100))

        pkg_col = next(i for i, (k, _) in enumerate(COLUMNS) if k == "packaging")
        self._pkg_delegate = PackagingDelegate()
        self.view.setItemDelegateForColumn(pkg_col, self._pkg_delegate)

        # ── Issues panel ──────────────────────────────────────────────────────
        self._issues_toggle = QPushButton("▼  Issues (0)")
        self._issues_toggle.setCheckable(True)
        self._issues_toggle.setChecked(True)
        self._issues_toggle.setStyleSheet(
            "text-align:left; padding:4px 8px; font-weight:bold; color:#1a1a1a; "
            "background:#e8e8e8; border:none; border-top:1px solid #ccc;"
        )
        self._issues_toggle.toggled.connect(self._on_issues_toggled)

        self._issues_table = QTableWidget(0, 3)
        self._issues_table.horizontalHeader().hide()
        self._issues_table.verticalHeader().hide()
        self._issues_table.setShowGrid(False)
        self._issues_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._issues_table.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        self._issues_table.setMinimumHeight(40)
        self._issues_table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.ResizeToContents)
        self._issues_table.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.ResizeMode.ResizeToContents)
        self._issues_table.horizontalHeader().setSectionResizeMode(
            2, QHeaderView.ResizeMode.Stretch)

        issues_container = QWidget()
        issues_vbox = QVBoxLayout(issues_container)
        issues_vbox.setContentsMargins(0, 0, 0, 0)
        issues_vbox.setSpacing(0)
        issues_vbox.addWidget(self._issues_toggle)
        issues_vbox.addWidget(self._issues_table)

        self._splitter = QSplitter(Qt.Orientation.Vertical)
        self._splitter.addWidget(self.view)
        self._splitter.addWidget(issues_container)
        self._splitter.setStretchFactor(0, 1)
        self._splitter.setStretchFactor(1, 0)
        self._splitter.setSizes([540, 160])
        vbox.addWidget(self._splitter)

        self.model.dataChanged.connect(self._refresh_issues)
        self.model.modelReset.connect(self._refresh_issues)

        self._status = QStatusBar()
        self.setStatusBar(self._status)
        self._status.showMessage("Ready — use File > Import CSV to begin.")

    def _build_menu(self):
        mb = self.menuBar()

        fm = mb.addMenu("File")
        self._add_action(fm, "Import CSV…", self._browse_bom, "Ctrl+O")
        self._file_recent_menu = fm.addMenu("Open Recent")
        self._file_recent_sep = self._file_recent_menu.addSeparator()
        fm.addSeparator()
        self._add_action(fm, "Save", self._save_csv, "Ctrl+S")
        self._add_action(fm, "Save As…", self._save_csv_as, "Ctrl+Shift+S")
        fm.addSeparator()
        self._add_action(fm, "Export to Excel…", self._export_excel, "Ctrl+E")
        fm.addSeparator()
        self._add_action(fm, "Quit", self.close, "Ctrl+Q")

        sm = mb.addMenu("Settings")
        self._add_action(sm, "API Credentials & Preferences…", self._open_settings)
        sm.addSeparator()
        self._use_fp_action = QAction("Use Footprint Aliases", self)
        self._use_fp_action.setCheckable(True)
        self._use_fp_action.setChecked(self.config.get("use_footprint_aliases", True))
        self._use_fp_action.toggled.connect(self._on_use_footprint_aliases_toggled)
        sm.addAction(self._use_fp_action)
        self._add_action(sm, "Edit Footprint Aliases…", self._open_footprint_aliases)

        hm = mb.addMenu("Help")
        about_act = QAction("About / GitHub", self)
        about_act.triggered.connect(lambda: QDesktopServices.openUrl(QUrl(_GITHUB_URL)))
        hm.addAction(about_act)

    def _build_toolbar(self):
        tb = QToolBar("Main")
        tb.setMovable(False)
        self.addToolBar(tb)

        self._import_btn = QToolButton()
        self._import_btn.setText("Import BOM")
        self._import_btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
        self._import_btn.setPopupMode(QToolButton.ToolButtonPopupMode.MenuButtonPopup)

        self._import_menu = QMenu(self)

        browse_act = QAction("Browse…", self)
        browse_act.setShortcut("Ctrl+O")
        browse_act.triggered.connect(self._browse_bom)
        self._import_menu.addAction(browse_act)

        self._recent_sep = self._import_menu.addSeparator()

        self._import_btn.setMenu(self._import_menu)
        self._import_btn.setDefaultAction(browse_act)
        self._import_btn.clicked.connect(self._browse_bom)

        tb.addWidget(self._import_btn)
        tb.addSeparator()

        self._fetch_selected_action = self._add_action(tb, "Fetch Selected", self._fetch_selected)
        self._fetch_action = self._add_action(tb, "Fetch All Data", self._fetch_all)
        self._cancel_action = self._add_action(tb, "Cancel", self._cancel_fetch)
        self._cancel_action.setEnabled(False)
        tb.addSeparator()
        self._add_action(tb, "Export Excel", self._export_excel)
        tb.addSeparator()
        self._add_action(tb, "Settings", self._open_settings)

        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        tb.addWidget(spacer)

        tb.addWidget(QLabel("Search: "))
        self._search_box = QLineEdit()
        self._search_box.setPlaceholderText("Filter rows…")
        self._search_box.setFixedWidth(220)
        self._search_box.textChanged.connect(self._on_search_changed)
        tb.addWidget(self._search_box)

        self._refresh_recent_menu()

    def _add_action(self, target, label: str, slot, shortcut: str = None) -> QAction:
        act = QAction(label, self)
        if shortcut:
            act.setShortcut(shortcut)
        act.triggered.connect(slot)
        target.addAction(act)
        return act

    # ── recent files menu ─────────────────────────────────────────────────────

    def _refresh_recent_menu(self):
        for act in self._recent_actions:
            self._import_menu.removeAction(act)
        for act in self._file_recent_actions:
            self._file_recent_menu.removeAction(act)
        self._recent_actions = []
        self._file_recent_actions = []

        recent = self.config.get("recent_files", [])
        if recent:
            self._recent_sep.setVisible(True)
            self._file_recent_sep.setVisible(True)
            for path in recent:
                label = Path(path).name

                tb_act = QAction(label, self)
                tb_act.setToolTip(path)
                tb_act.triggered.connect(lambda _, p=path: self._load_bom(p))
                self._import_menu.addAction(tb_act)
                self._recent_actions.append(tb_act)

                fm_act = QAction(label, self)
                fm_act.setToolTip(path)
                fm_act.triggered.connect(lambda _, p=path: self._load_bom(p))
                self._file_recent_menu.addAction(fm_act)
                self._file_recent_actions.append(fm_act)
        else:
            self._recent_sep.setVisible(False)
            self._file_recent_sep.setVisible(False)

    def _add_recent(self, path: str):
        recent: list = self.config.get("recent_files", [])
        if path in recent:
            recent.remove(path)
        recent.insert(0, path)
        self.config["recent_files"] = recent[:_MAX_RECENT]
        save_config(self.config)
        self._refresh_recent_menu()

    def _apply_column_visibility(self):
        col_cfg = self.config.get("columns", {})
        for i, (key, _) in enumerate(COLUMNS):
            if key == "status":
                continue
            show = col_cfg.get(key, {}).get("show", True)
            self.view.setColumnHidden(i, not show)

    # ── slots ─────────────────────────────────────────────────────────────────

    def _browse_bom(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Import KiCad BOM", str(Path.home()), "CSV Files (*.csv);;All Files (*)"
        )
        if path:
            self._load_bom(path)

    def _load_bom(self, path: str):
        if not Path(path).exists():
            QMessageBox.warning(self, "File Not Found", f"Could not find:\n{path}")
            recent = self.config.get("recent_files", [])
            if path in recent:
                recent.remove(path)
            self.config["recent_files"] = recent
            save_config(self.config)
            self._refresh_recent_menu()
            return
        try:
            use_aliases = self.config.get("use_footprint_aliases", True)
            if use_aliases:
                fp_map = self._footprint_map
            else:
                fp_map = {v: k for k, v in self._footprint_map.items()} if self._footprint_map else None

            rows = parse_bom(
                path,
                footprint_map=fp_map,
                compress_refs=self.config.get("compress_references", True),
                default_packaging=self.config.get("default_packaging", "Cut Tape"),
            )
            threshold = self.config.get("low_stock_threshold", 10)
            for row in rows:
                match = lookup_part(row["value"], row["footprint"])
                if match:
                    for key in ("mpn", "manufacturer", "digikey_pn", "mouser_pn", "lcsc_pn", "description"):
                        if not row.get(key):
                            row[key] = match.get(key, "")
                recalc_status(row, threshold)
            self.model.set_rows(rows)
            self._current_csv_path = path
            self._add_recent(path)
            self._status.showMessage(f"Loaded {len(rows)} groups from {Path(path).name}")
        except Exception as e:
            QMessageBox.critical(self, "Import Error", str(e))

    def _fetch_selected(self):
        selected_rows = sorted({idx.row() for idx in self.view.selectedIndexes()})
        if not selected_rows:
            QMessageBox.information(self, "No Selection", "Select one or more rows first.")
            return
        if not self._dk.is_configured() and not self._mu.is_configured():
            QMessageBox.warning(self, "No API Configured",
                "Configure at least one API in Settings before fetching.")
            return
        self._fetch_action.setEnabled(False)
        self._fetch_selected_action.setEnabled(False)
        self._cancel_action.setEnabled(True)
        self._status.showMessage("Fetching selected rows…")

        all_rows = self.model.get_all_rows()
        subset = [all_rows[i] for i in selected_rows]

        self._fetch_worker = FetchAllWorker(subset, self._dk, self._mu, self.config)
        self._fetch_worker.progress.connect(
            lambda local_idx, data: self.model.update_row(selected_rows[local_idx], data)
        )
        self._fetch_worker.finished.connect(self._on_fetch_done)
        self._fetch_worker.error.connect(self._on_fetch_error)
        self._fetch_worker.start()

    def _fetch_all(self):
        rows = self.model.get_all_rows()
        if not rows:
            QMessageBox.information(self, "No Data", "Import a BOM first.")
            return
        if not self._dk.is_configured() and not self._mu.is_configured():
            QMessageBox.warning(self, "No API Configured",
                "Configure at least one API in Settings before fetching.")
            return
        self._fetch_action.setEnabled(False)
        self._cancel_action.setEnabled(True)
        self._status.showMessage("Fetching…")

        self._fetch_worker = FetchAllWorker(rows, self._dk, self._mu, self.config)
        self._fetch_worker.progress.connect(self._on_fetch_progress)
        self._fetch_worker.finished.connect(self._on_fetch_done)
        self._fetch_worker.error.connect(self._on_fetch_error)
        self._fetch_worker.start()

    def _cancel_fetch(self):
        if self._fetch_worker:
            self._fetch_worker.cancel()

    def _on_fetch_progress(self, row_idx: int, data: dict):
        self.model.update_row(row_idx, data)
        self._status.showMessage(f"Fetching… {row_idx + 1}/{self.model.rowCount()}")

    def _on_fetch_done(self):
        self._fetch_action.setEnabled(True)
        self._fetch_selected_action.setEnabled(True)
        self._cancel_action.setEnabled(False)
        self._status.showMessage("Fetch complete.")

    def _on_fetch_error(self, msg: str):
        self._fetch_action.setEnabled(True)
        self._fetch_selected_action.setEnabled(True)
        self._cancel_action.setEnabled(False)
        self._status.showMessage(f"Fetch error: {msg}")
        QMessageBox.warning(self, "Fetch Error", msg)

    def _on_key_cell_edited(self, row_idx: int, key: str):
        row = self.model.get_row(row_idx)
        threshold = self.config.get("low_stock_threshold", 10)

        if key == "lcsc_pn":
            lcsc = (row.get("lcsc_pn") or "").strip()
            if lcsc and row.get("value") and row.get("footprint"):
                save_lcsc_pn(row["value"], row["footprint"], lcsc)
                self._status.showMessage(f"Row {row_idx + 1}: LCSC PN saved to Part Dictionary.")
            return

        if key in ("mpn", "digikey_pn", "mouser_pn"):
            recalc_status(row, threshold)
            self.model.update_row(row_idx, {
                "status": row["status"],
                "status_reason": row.get("status_reason", ""),
            })
            return

        if key == "references":
            raw = expand_refs_string(row.get("references", ""))
            raw = _sort_refs(raw)
            self.model._rows[row_idx]["_raw_refs"] = raw
            ref_count = len(raw)
            try:
                qty_val = int(row.get("qty", 0))
            except (ValueError, TypeError):
                qty_val = 0
            if qty_val != ref_count:
                QMessageBox.warning(
                    self, "Quantity Mismatch",
                    f"References contain {ref_count} component(s) but Quantity is {qty_val}.\n"
                    "Update the Quantity to match, or correct the References.",
                )
            return

        if key == "qty":
            raw = self.model._rows[row_idx].get("_raw_refs") or \
                  expand_refs_string(row.get("references", ""))
            ref_count = len(raw)
            try:
                qty_val = int(row.get("qty", 0))
            except (ValueError, TypeError):
                qty_val = 0
            if qty_val != ref_count:
                QMessageBox.warning(
                    self, "Quantity Mismatch",
                    f"Quantity set to {qty_val} but References contain {ref_count} component(s).\n"
                    "Update the References to match, or correct the Quantity.",
                )
            return

        # "value" edit — look up new value+footprint combo in DB and auto-fill
        match = lookup_part(row.get("value", ""), row.get("footprint", ""))
        if match:
            update = {}
            for k in ("mpn", "manufacturer", "digikey_pn", "mouser_pn", "lcsc_pn", "description"):
                if not row.get(k) and match.get(k):
                    update[k] = match[k]
            if update:
                row.update(update)
                recalc_status(row, threshold)
                update["status"] = row["status"]
                update["status_reason"] = row.get("status_reason", "")
                self.model.update_row(row_idx, update)
                self._status.showMessage(
                    f"Row {row_idx + 1}: auto-filled from Part Dictionary after {key} edit."
                )

    _SEARCH_FIELDS = (
        "references", "value", "description", "footprint",
        "mpn", "manufacturer", "digikey_pn", "mouser_pn", "lcsc_pn", "notes",
    )

    def _on_search_changed(self, text: str):
        needle = text.strip().lower()
        if not needle:
            self.view.clearSelection()
            return
        rows = self.model.get_all_rows()
        for i, row in enumerate(rows):
            for field in self._SEARCH_FIELDS:
                if needle in str(row.get(field, "")).lower():
                    self.view.selectRow(i)
                    self.view.scrollTo(self.model.index(i, 0))
                    return
        self.view.clearSelection()

    def _on_footprint_edited(self, row_idx: int, old_fp: str, new_fp: str):
        if old_fp == new_fp or not old_fp or not new_fp:
            return
        if self._footprint_map.get(old_fp) == new_fp:
            return

        msg = QMessageBox(self)
        msg.setWindowTitle("Save Footprint Substitution?")
        msg.setText(
            f"<b>{old_fp}</b><br>→ <b>{new_fp}</b><br><br>"
            "Save this substitution so future BOM imports apply it automatically?"
        )
        msg.setTextFormat(Qt.TextFormat.RichText)
        once_btn   = msg.addButton("Apply Once",    QMessageBox.ButtonRole.NoRole)
        always_btn = msg.addButton("Always Apply",  QMessageBox.ButtonRole.YesRole)
        msg.setDefaultButton(always_btn)
        msg.exec()

        if msg.clickedButton() == always_btn:
            self._footprint_map[old_fp] = new_fp
            save_footprint_map(self._footprint_map)
            rows = self.model.get_all_rows()
            for i, row in enumerate(rows):
                if i != row_idx and row.get("footprint") == old_fp:
                    self.model.update_row(i, {"footprint": new_fp})
            self._status.showMessage(f"Footprint alias saved: {old_fp} → {new_fp}")

    def _on_single_click(self, index: QModelIndex):
        if 0 <= index.column() < len(COLUMNS):
            if COLUMNS[index.column()][0] == "packaging":
                self.view.edit(index)

    def _on_double_click(self, index: QModelIndex):
        if 0 <= index.column() < len(COLUMNS):
            if COLUMNS[index.column()][0] == "packaging":
                return

        row_idx = index.row()
        row = self.model.get_row(row_idx)
        dlg = SearchAssignDialog(row, self._dk, self._mu, save_part, self)
        if dlg.exec() == SearchAssignDialog.DialogCode.Accepted and dlg.selected_result:
            result = dlg.selected_result
            update = {
                "mpn":          result.get("mpn", row.get("mpn", "")),
                "manufacturer": result.get("manufacturer", row.get("manufacturer", "")),
                "description":  result.get("description", ""),
                "digikey_pn":   result.get("digikey_pn", ""),
                "mouser_pn":    result.get("mouser_pn", ""),
                "stock":        result.get("stock", ""),
            }
            merged = {**row, **update}
            recalc_status(merged, self.config.get("low_stock_threshold", 10))
            update["status"] = merged["status"]
            update["status_reason"] = merged.get("status_reason", "")
            self.model.update_row(row_idx, update)

    def _save_csv(self):
        if not self._current_csv_path:
            self._save_csv_as()
            return

        rows = self.model.get_all_rows()
        if not rows:
            QMessageBox.information(self, "No Data", "Nothing to save.")
            return

        try:
            export_csv(rows, self._current_csv_path)
            self._status.showMessage(f"Saved → {self._current_csv_path}")
        except Exception as e:
            QMessageBox.critical(self, "Save Error", f"Error saving CSV: {e}")

    def _save_csv_as(self):
        rows = self.model.get_all_rows()
        if not rows:
            QMessageBox.information(self, "No Data", "Nothing to save.")
            return

        path, _ = QFileDialog.getSaveFileName(
            self, "Save BOM as CSV",
            str(Path(self._current_csv_path).parent if self._current_csv_path else Path.home()),
            "CSV Files (*.csv)"
        )
        if not path:
            return

        self._current_csv_path = path
        self._add_recent(path)
        self._save_csv()

    def _export_excel(self):
        rows = self.model.get_all_rows()
        if not rows:
            QMessageBox.information(self, "No Data", "Import a BOM first.")
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Export BOM to Excel",
            str(Path.home() / "bom_export.xlsx"),
            "Excel Files (*.xlsx)",
        )
        if not path:
            return
        try:
            exp = self.config.get("export", {})
            export_bom(
                rows, path,
                header_color=exp.get("header_color", "4F6228"),
                columns=self._get_export_columns(),
                project_name=exp.get("project_name", ""),
                revision=exp.get("revision", ""),
                show_title=exp.get("show_title", True),
                show_footer=exp.get("show_footer", True),
            )
            self._status.showMessage(f"Exported → {path}")
            QMessageBox.information(self, "Export Complete", f"Saved to:\n{path}")
        except Exception as e:
            QMessageBox.critical(self, "Export Error", str(e))

    def _open_settings(self):
        dlg = SettingsDialog(self.config, self)
        if dlg.exec() == SettingsDialog.DialogCode.Accepted:
            old_compress = self.config.get("compress_references", True)
            self.config.update(dlg.get_config())
            save_config(self.config)
            self._dk = DigiKeyClient(self.config)
            self._mu = MouserClient(self.config)
            self._apply_column_visibility()
            new_compress = self.config.get("compress_references", True)
            if new_compress != old_compress:
                self._toggle_compress_references(new_compress)
            self._status.showMessage("Settings saved.")

    def _open_footprint_aliases(self):
        from gui.footprint_dialog import FootprintAliasDialog
        fps = list({row.get("footprint", "") for row in self.model.get_all_rows() if row.get("footprint")})
        dlg = FootprintAliasDialog(bom_footprints=fps, parent=self)
        if dlg.exec() == FootprintAliasDialog.DialogCode.Accepted:
            self._footprint_map = load_footprint_map()
            self._status.showMessage("Footprint aliases saved.")

    def _on_issues_toggled(self, checked: bool):
        self._issues_table.setVisible(checked)
        total = sum(self._splitter.sizes())
        btn_h = self._issues_toggle.sizeHint().height() + 2
        if checked:
            self._splitter.setSizes([total - 160, 160])
        else:
            self._splitter.setSizes([total - btn_h, btn_h])

    def _refresh_issues(self):
        from gui.bom_table import _STATUS_SYMBOL
        rows = [r for r in self.model.get_all_rows() if r.get("status") != "green"]
        self._issues_table.setRowCount(len(rows))
        for ri, row in enumerate(rows):
            status = row.get("status", "red")
            refs_item   = QTableWidgetItem(row.get("references", ""))
            sym_item    = QTableWidgetItem(_STATUS_SYMBOL.get(status, "○"))
            reason_item = QTableWidgetItem(row.get("status_reason", ""))
            sym_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            for item in (refs_item, sym_item, reason_item):
                item.setFlags(Qt.ItemFlag.ItemIsEnabled)
            self._issues_table.setItem(ri, 0, refs_item)
            self._issues_table.setItem(ri, 1, sym_item)
            self._issues_table.setItem(ri, 2, reason_item)
            self._issues_table.setRowHeight(ri, 22)
        n = len(rows)
        arrow = "▼" if self._issues_toggle.isChecked() else "▶"
        self._issues_toggle.setText(f"{arrow}  Issues ({n})")

    def _apply_footprint_alias_toggle(self, checked: bool):
        self.config["use_footprint_aliases"] = checked
        save_config(self.config)

        self._use_fp_action.blockSignals(True)
        self._use_fp_action.setChecked(checked)
        self._use_fp_action.blockSignals(False)

        if not self._footprint_map:
            return

        fp_map = self._footprint_map if checked else {v: k for k, v in self._footprint_map.items()}
        changed = False
        for row in self.model._rows:
            fp = row.get("footprint", "")
            new_fp = fp_map.get(fp)
            if new_fp and new_fp != fp:
                row["footprint"] = new_fp
                changed = True

        if changed:
            row_count = self.model.rowCount()
            self.model.dataChanged.emit(
                self.model.index(0, 0),
                self.model.index(row_count - 1, len(COLUMNS) - 1),
            )

    def _on_use_footprint_aliases_toggled(self, checked: bool):
        self._apply_footprint_alias_toggle(checked)

    # ── column management ─────────────────────────────────────────────────────

    def _restore_column_order(self):
        order = self.config.get("column_order", [])
        if not order:
            return
        hdr = self.view.horizontalHeader()
        key_to_logical = {key: i for i, (key, _) in enumerate(COLUMNS)}
        for target_visual, key in enumerate(order):
            logical = key_to_logical.get(key)
            if logical is None:
                continue
            current_visual = hdr.visualIndex(logical)
            if current_visual != target_visual:
                hdr.moveSection(current_visual, target_visual)

    def _save_column_order(self):
        hdr = self.view.horizontalHeader()
        order = [COLUMNS[hdr.logicalIndex(vi)][0] for vi in range(hdr.count())]
        self.config["column_order"] = order
        save_config(self.config)

    def _on_column_moved(self, _logical: int, _old: int, _new: int):
        self._save_column_order()

    def _get_export_columns(self) -> list[tuple]:
        """Columns in current visual order, skipping hidden and export-excluded ones."""
        hdr = self.view.horizontalHeader()
        col_cfg = self.config.get("columns", {})
        result = []
        for vi in range(hdr.count()):
            li = hdr.logicalIndex(vi)
            if li < 0 or li >= len(COLUMNS):
                continue
            key, label = COLUMNS[li]
            if key == "status":
                continue
            if hdr.isSectionHidden(li):
                continue
            if not col_cfg.get(key, {}).get("export", True):
                continue
            result.append((key, label))
        return result or EXPORT_COLUMNS

    def _on_header_context_menu(self, pos):
        hdr = self.view.horizontalHeader()
        logical = hdr.logicalIndexAt(pos)
        if logical < 0 or logical >= len(COLUMNS):
            return
        key, label = COLUMNS[logical]
        if key == "status":
            return

        col_cfg = self.config.setdefault("columns", {})
        is_excluded = not col_cfg.get(key, {}).get("export", True)

        menu = QMenu(self)

        hide_act = QAction("Hide", self)
        hide_act.triggered.connect(
            lambda _=False, li=logical, k=key: self._col_set_show(li, k, False)
        )
        menu.addAction(hide_act)

        if key == "references":
            compress_act = QAction("Compress References", self)
            compress_act.setCheckable(True)
            compress_act.setChecked(self.config.get("compress_references", True))
            compress_act.triggered.connect(self._toggle_compress_references)
            menu.addAction(compress_act)

        if key == "footprint":
            fp_alias_act = QAction("Use Footprint Aliases", self)
            fp_alias_act.setCheckable(True)
            fp_alias_act.setChecked(self.config.get("use_footprint_aliases", True))
            fp_alias_act.triggered.connect(self._apply_footprint_alias_toggle)
            menu.addAction(fp_alias_act)

        exclude_act = QAction("Exclude from Export", self)
        exclude_act.setCheckable(True)
        exclude_act.setChecked(is_excluded)
        exclude_act.triggered.connect(
            lambda checked, k=key: self._col_set_export(k, not checked)
        )
        menu.addAction(exclude_act)

        menu.addSeparator()

        fit_act = QAction("Auto Fit", self)
        fit_act.triggered.connect(lambda _=False, li=logical: self._autofit_column(li))
        menu.addAction(fit_act)

        fit_all_act = QAction("Auto Fit All", self)
        fit_all_act.triggered.connect(self._autofit_all_columns)
        menu.addAction(fit_all_act)

        menu.exec(hdr.mapToGlobal(pos))

    def _col_set_show(self, logical_idx: int, key: str, show: bool):
        self.view.setColumnHidden(logical_idx, not show)
        self.config.setdefault("columns", {}).setdefault(key, {})["show"] = show
        save_config(self.config)

    def _toggle_compress_references(self, checked: bool):
        self.config["compress_references"] = checked
        save_config(self.config)
        for row in self.model._rows:
            raw = row.get("_raw_refs", [])
            if raw:
                row["references"] = _compress_refs(raw) if checked else ", ".join(raw)
        row_count = self.model.rowCount()
        if row_count:
            self.model.dataChanged.emit(
                self.model.index(0, 0),
                self.model.index(row_count - 1, len(COLUMNS) - 1),
            )

    def _col_set_export(self, key: str, export: bool):
        self.config.setdefault("columns", {}).setdefault(key, {})["export"] = export
        save_config(self.config)

    def _autofit_column(self, logical: int):
        self.view.resizeColumnToContents(logical)

    def _autofit_all_columns(self):
        self.view.resizeColumnsToContents()
