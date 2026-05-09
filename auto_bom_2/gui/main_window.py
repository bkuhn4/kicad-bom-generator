from pathlib import Path

from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QToolBar, QStatusBar,
    QFileDialog, QMessageBox, QTableView, QHeaderView, QMenu, QToolButton,
)
from PyQt6.QtCore import QModelIndex, QUrl, Qt
from PyQt6.QtGui import QAction, QDesktopServices

from config_manager import load_config, save_config
from database import init_db, lookup_part, save_part
from bom_parser import parse_bom
from exporter import export_bom
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
        init_db()
        self._dk = DigiKeyClient(self.config)
        self._mu = MouserClient(self.config)
        self._fetch_worker: FetchAllWorker | None = None
        self._single_workers: list[FetchAllWorker] = []
        self._recent_actions: list[QAction] = []

        self._build_ui()
        self._build_menu()
        self._build_toolbar()

    # ── UI setup ──────────────────────────────────────────────────────────────

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        vbox = QVBoxLayout(central)
        vbox.setContentsMargins(4, 4, 4, 4)

        self.model = BomTableModel()
        self.model.packaging_changed.connect(self._on_packaging_changed)
        self.model.key_cell_edited.connect(self._on_key_cell_edited)

        self.view = QTableView()
        self.view.setModel(self.model)
        self.view.setSelectionBehavior(QTableView.SelectionBehavior.SelectRows)
        self.view.setAlternatingRowColors(False)
        self.view.doubleClicked.connect(self._on_double_click)

        hdr = self.view.horizontalHeader()
        hdr.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)

        _widths = {
            "status": 28, "references": 130, "qty": 38, "value": 80,
            "footprint": 160, "packaging": 100, "manufacturer": 120,
            "mpn": 150, "description": 210, "stock": 58,
            "digikey_pn": 120, "mouser_pn": 120, "lcsc_pn": 90, "notes": 120,
        }
        for i, (key, _) in enumerate(COLUMNS):
            self.view.setColumnWidth(i, _widths.get(key, 100))

        pkg_col = next(i for i, (k, _) in enumerate(COLUMNS) if k == "packaging")
        self._pkg_delegate = PackagingDelegate()
        self._pkg_delegate.packaging_changed.connect(self._on_packaging_changed)
        self.view.setItemDelegateForColumn(pkg_col, self._pkg_delegate)

        vbox.addWidget(self.view)

        self._status = QStatusBar()
        self.setStatusBar(self._status)
        self._status.showMessage("Ready — use File > Import CSV to begin.")

    def _build_menu(self):
        mb = self.menuBar()

        fm = mb.addMenu("File")
        self._add_action(fm, "Import CSV", self._browse_bom, "Ctrl+O")
        fm.addSeparator()
        self._add_action(fm, "Export to Excel…", self._export_excel, "Ctrl+E")
        fm.addSeparator()
        self._add_action(fm, "Quit", self.close, "Ctrl+Q")

        sm = mb.addMenu("Settings")
        self._add_action(sm, "API Credentials & Preferences…", self._open_settings)

        hm = mb.addMenu("Help")
        about_act = QAction("About / GitHub", self)
        about_act.triggered.connect(lambda: QDesktopServices.openUrl(QUrl(_GITHUB_URL)))
        hm.addAction(about_act)

    def _build_toolbar(self):
        tb = QToolBar("Main")
        tb.setMovable(False)
        self.addToolBar(tb)

        # ── Import BOM with recent-files dropdown ──────────────────────────
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
        # Override: clicking the label itself also opens the file dialog
        self._import_btn.clicked.connect(self._browse_bom)

        tb.addWidget(self._import_btn)
        tb.addSeparator()

        self._fetch_action = self._add_action(tb, "Fetch All Data", self._fetch_all)
        self._cancel_action = self._add_action(tb, "Cancel", self._cancel_fetch)
        self._cancel_action.setEnabled(False)
        tb.addSeparator()
        self._add_action(tb, "Export Excel", self._export_excel)
        tb.addSeparator()
        self._add_action(tb, "Settings", self._open_settings)

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
        self._recent_actions = []

        recent = self.config.get("recent_files", [])
        if recent:
            self._recent_sep.setVisible(True)
            for path in recent:
                label = Path(path).name
                act = QAction(label, self)
                act.setToolTip(path)
                act.triggered.connect(lambda _, p=path: self._load_bom(p))
                self._import_menu.addAction(act)
                self._recent_actions.append(act)
        else:
            self._recent_sep.setVisible(False)

    def _add_recent(self, path: str):
        recent: list = self.config.get("recent_files", [])
        if path in recent:
            recent.remove(path)
        recent.insert(0, path)
        self.config["recent_files"] = recent[:_MAX_RECENT]
        save_config(self.config)
        self._refresh_recent_menu()

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
            rows = parse_bom(path)
            for row in rows:
                match = lookup_part(row["value"], row["footprint"])
                if match:
                    for key in ("mpn", "manufacturer", "digikey_pn", "mouser_pn", "lcsc_pn", "description"):
                        if not row.get(key):
                            row[key] = match.get(key, "")
                _recalc_status(row, self.config.get("low_stock_threshold", 10))
            self.model.set_rows(rows)
            self._add_recent(path)
            self._status.showMessage(f"Loaded {len(rows)} groups from {Path(path).name}")
        except Exception as e:
            QMessageBox.critical(self, "Import Error", str(e))

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
        self._cancel_action.setEnabled(False)
        self._status.showMessage("Fetch complete.")

    def _on_fetch_error(self, msg: str):
        self._fetch_action.setEnabled(True)
        self._cancel_action.setEnabled(False)
        self._status.showMessage(f"Fetch error: {msg}")
        QMessageBox.warning(self, "Fetch Error", msg)

    def _on_packaging_changed(self, row_idx: int, packaging: str):
        row = self.model.get_row(row_idx)
        if not row.get("mpn", "").strip() or not self._dk.is_configured():
            return
        row["packaging"] = packaging
        w = FetchAllWorker([row], self._dk, self._mu, self.config)
        w.progress.connect(lambda _, data: self.model.update_row(row_idx, data))
        w.start()
        self._single_workers.append(w)
        self._single_workers = [x for x in self._single_workers if x.isRunning()]

    def _on_key_cell_edited(self, row_idx: int, key: str):
        row = self.model.get_row(row_idx)
        match = lookup_part(row.get("value", ""), row.get("footprint", ""))
        if match:
            update = {}
            for k in ("mpn", "manufacturer", "digikey_pn", "mouser_pn", "lcsc_pn", "description"):
                if not row.get(k) and match.get(k):
                    update[k] = match[k]
            if update:
                row.update(update)
                _recalc_status(row, self.config.get("low_stock_threshold", 10))
                update["status"] = row["status"]
                self.model.update_row(row_idx, update)
                self._status.showMessage(
                    f"Row {row_idx + 1}: auto-filled from Part Dictionary after {key} edit."
                )

    def _on_double_click(self, index: QModelIndex):
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
            _recalc_status(merged, self.config.get("low_stock_threshold", 10))
            update["status"] = merged["status"]
            self.model.update_row(row_idx, update)

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
            header_color = self.config.get("export", {}).get("header_color", "4F6228")
            export_bom(rows, path, header_color=header_color)
            self._status.showMessage(f"Exported → {path}")
            QMessageBox.information(self, "Export Complete", f"Saved to:\n{path}")
        except Exception as e:
            QMessageBox.critical(self, "Export Error", str(e))

    def _open_settings(self):
        dlg = SettingsDialog(self.config, self)
        if dlg.exec() == SettingsDialog.DialogCode.Accepted:
            self.config.update(dlg.get_config())
            save_config(self.config)
            self._dk = DigiKeyClient(self.config)
            self._mu = MouserClient(self.config)
            self._status.showMessage("Settings saved.")


# ── helpers ───────────────────────────────────────────────────────────────────

def _recalc_status(row: dict, threshold: int):
    if not row.get("mpn", "").strip():
        row["status"] = "red"
        return
    has_dist = row.get("digikey_pn") or row.get("mouser_pn")
    if not has_dist:
        row["status"] = "yellow"
        return
    stock = row.get("stock", 0)
    row["status"] = "green" if isinstance(stock, int) and stock > threshold else "yellow"
