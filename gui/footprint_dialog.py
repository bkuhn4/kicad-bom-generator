from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView,
    QMessageBox,
)
from PyQt6.QtCore import Qt

from core.footprint_map import load_footprint_map, save_footprint_map


class FootprintAliasDialog(QDialog):
    def __init__(self, bom_footprints: list[str] | None = None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Footprint Aliases")
        self.setMinimumSize(560, 400)
        self._bom_footprints = bom_footprints or []

        layout = QVBoxLayout(self)

        self._table = QTableWidget(0, 2)
        self._table.setHorizontalHeaderLabels(["KiCad Footprint", "Alias"])
        self._table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self._table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setEditTriggers(
            QAbstractItemView.EditTrigger.DoubleClicked |
            QAbstractItemView.EditTrigger.EditKeyPressed |
            QAbstractItemView.EditTrigger.AnyKeyPressed
        )
        layout.addWidget(self._table)

        btn_row = QHBoxLayout()
        add_btn = QPushButton("Add Row")
        add_btn.clicked.connect(self._add_row)
        del_btn = QPushButton("Delete Selected")
        del_btn.clicked.connect(self._delete_selected)
        bom_btn = QPushButton("Add from Current BOM")
        bom_btn.clicked.connect(self._add_from_bom)
        btn_row.addWidget(add_btn)
        btn_row.addWidget(del_btn)
        btn_row.addWidget(bom_btn)
        btn_row.addStretch()
        layout.addLayout(btn_row)

        bottom = QHBoxLayout()
        bottom.addStretch()
        save_btn = QPushButton("Save")
        save_btn.setDefault(True)
        save_btn.clicked.connect(self._save)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        bottom.addWidget(save_btn)
        bottom.addWidget(cancel_btn)
        layout.addLayout(bottom)

        self._load()

    def _load(self):
        mapping = load_footprint_map()
        for kicad, alias in mapping.items():
            self._insert_row(kicad, alias)

    def _insert_row(self, kicad: str = "", alias: str = ""):
        row = self._table.rowCount()
        self._table.insertRow(row)
        self._table.setItem(row, 0, QTableWidgetItem(kicad))
        self._table.setItem(row, 1, QTableWidgetItem(alias))

    def _add_row(self):
        self._insert_row()
        self._table.scrollToBottom()
        self._table.setCurrentCell(self._table.rowCount() - 1, 0)
        self._table.editItem(self._table.item(self._table.rowCount() - 1, 0))

    def _delete_selected(self):
        rows = sorted({idx.row() for idx in self._table.selectedIndexes()}, reverse=True)
        for r in rows:
            self._table.removeRow(r)

    def _add_from_bom(self):
        existing = set()
        for r in range(self._table.rowCount()):
            item = self._table.item(r, 0)
            if item:
                existing.add(item.text())

        added = 0
        for fp in self._bom_footprints:
            if fp and fp not in existing:
                self._insert_row(fp, "")
                existing.add(fp)
                added += 1

        if added == 0:
            QMessageBox.information(self, "Add from BOM",
                "All current BOM footprints are already in the table.")
        else:
            self._table.scrollToBottom()

    def _save(self):
        mapping = {}
        for r in range(self._table.rowCount()):
            kicad_item = self._table.item(r, 0)
            alias_item = self._table.item(r, 1)
            kicad = (kicad_item.text().strip() if kicad_item else "")
            alias = (alias_item.text().strip() if alias_item else "")
            if kicad and alias:
                mapping[kicad] = alias
        save_footprint_map(mapping)
        self.accept()
