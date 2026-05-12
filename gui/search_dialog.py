from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLineEdit, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView, QLabel, QMessageBox,
)
from PyQt6.QtCore import Qt
from .workers import SearchWorker


class SearchAssignDialog(QDialog):
    def __init__(self, row: dict, digikey_client, mouser_client, save_part_fn, parent=None):
        super().__init__(parent)
        self.row = row
        self.dk = digikey_client
        self.mu = mouser_client
        self.save_part_fn = save_part_fn
        self.selected_result: dict | None = None
        self._results: list[dict] = []
        self._worker: SearchWorker | None = None

        self.setWindowTitle(
            f"Search & Assign — {row.get('value', '')}  /  {row.get('footprint', '')}"
        )
        self.setMinimumSize(920, 500)
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)

        # Search bar
        bar = QHBoxLayout()
        self.search_input = QLineEdit(self.row.get("mpn") or self.row.get("value", ""))
        self.search_input.setPlaceholderText("MPN, keyword, or description…")
        self.search_input.returnPressed.connect(self._search)
        self.search_btn = QPushButton("Search")
        self.search_btn.clicked.connect(self._search)
        bar.addWidget(QLabel("Search:"))
        bar.addWidget(self.search_input)
        bar.addWidget(self.search_btn)
        layout.addLayout(bar)

        # Results table
        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(
            ["Source", "MPN", "Manufacturer", "Description", "Stock", "Dist. PN"]
        )
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.doubleClicked.connect(self._accept_selected)
        layout.addWidget(self.table)

        # Footer
        footer = QHBoxLayout()
        self.status_lbl = QLabel("Enter a search term above.")
        footer.addWidget(self.status_lbl)
        footer.addStretch()
        select_btn = QPushButton("Select && Save")
        select_btn.setDefault(True)
        select_btn.clicked.connect(self._accept_selected)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        footer.addWidget(select_btn)
        footer.addWidget(cancel_btn)
        layout.addLayout(footer)

    def _search(self):
        kw = self.search_input.text().strip()
        if not kw:
            return
        self.search_btn.setEnabled(False)
        self.status_lbl.setText("Searching…")
        self.table.setRowCount(0)
        self._results = []

        self._worker = SearchWorker(kw, self.dk, self.mu)
        self._worker.results_ready.connect(self._on_results)
        self._worker.error.connect(self._on_error)
        self._worker.start()

    def _on_results(self, results: list):
        self.search_btn.setEnabled(True)
        self._results = results
        self.status_lbl.setText(f"{len(results)} result(s) found." if results else "No results found.")
        for r in results:
            ri = self.table.rowCount()
            self.table.insertRow(ri)
            dist_pn = r.get("digikey_pn", "") or r.get("mouser_pn", "")
            for ci, val in enumerate([
                r.get("source", ""),
                r.get("mpn", ""),
                r.get("manufacturer", ""),
                r.get("description", ""),
                str(r.get("stock", "")),
                dist_pn,
            ]):
                self.table.setItem(ri, ci, QTableWidgetItem(val))

    def _on_error(self, msg: str):
        self.search_btn.setEnabled(True)
        self.status_lbl.setText(f"Error: {msg}")

    def _accept_selected(self):
        ri = self.table.currentRow()
        if ri < 0 or ri >= len(self._results):
            QMessageBox.warning(self, "No Selection", "Select a part from the list first.")
            return
        self.selected_result = self._results[ri]
        v, f = self.row.get("value", ""), self.row.get("footprint", "")
        if v and f:
            self.save_part_fn(v, f, self.selected_result)
        self.accept()
