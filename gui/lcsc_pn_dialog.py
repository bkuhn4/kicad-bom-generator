from __future__ import annotations

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QLineEdit,
    QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView,
)
from PyQt6.QtCore import Qt

from core.database import get_all_lcsc_assignments, save_lcsc_pn, clear_lcsc_pn


class LcscPnDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("LCSC Part Numbers")
        self.setMinimumSize(680, 420)
        self._to_clear: set[tuple[str, str]] = set()

        layout = QVBoxLayout(self)

        self._search = QLineEdit()
        self._search.setPlaceholderText("Filter…")
        self._search.setClearButtonEnabled(True)
        self._search.textChanged.connect(self._filter_rows)
        layout.addWidget(self._search)

        self._table = QTableWidget(0, 3)
        self._table.setHorizontalHeaderLabels(["Value", "Footprint", "LCSC PN"])
        hdr = self._table.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        hdr.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        hdr.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setEditTriggers(
            QAbstractItemView.EditTrigger.DoubleClicked |
            QAbstractItemView.EditTrigger.EditKeyPressed |
            QAbstractItemView.EditTrigger.AnyKeyPressed
        )
        layout.addWidget(self._table)

        btn_row = QHBoxLayout()
        del_btn = QPushButton("Remove Selected")
        del_btn.clicked.connect(self._delete_selected)
        btn_row.addWidget(del_btn)
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
        for entry in get_all_lcsc_assignments():
            self._insert_row(entry["value"], entry["footprint"], entry["lcsc_pn"])

    def _insert_row(self, value: str, footprint: str, lcsc_pn: str):
        row = self._table.rowCount()
        self._table.insertRow(row)

        value_item = QTableWidgetItem(value)
        value_item.setFlags(value_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        fp_item = QTableWidgetItem(footprint)
        fp_item.setFlags(fp_item.flags() & ~Qt.ItemFlag.ItemIsEditable)

        self._table.setItem(row, 0, value_item)
        self._table.setItem(row, 1, fp_item)
        self._table.setItem(row, 2, QTableWidgetItem(lcsc_pn))

    def _filter_rows(self, text: str):
        needle = text.lower()
        for r in range(self._table.rowCount()):
            visible = not needle or any(
                needle in (self._table.item(r, c).text() if self._table.item(r, c) else "").lower()
                for c in range(3)
            )
            self._table.setRowHidden(r, not visible)

    def _delete_selected(self):
        rows = sorted({idx.row() for idx in self._table.selectedIndexes()}, reverse=True)
        for r in rows:
            v_item = self._table.item(r, 0)
            f_item = self._table.item(r, 1)
            if v_item and f_item:
                self._to_clear.add((v_item.text(), f_item.text()))
            self._table.removeRow(r)

    def _save(self):
        for r in range(self._table.rowCount()):
            v_item = self._table.item(r, 0)
            f_item = self._table.item(r, 1)
            lcsc_item = self._table.item(r, 2)
            value = v_item.text() if v_item else ""
            footprint = f_item.text() if f_item else ""
            lcsc_pn = lcsc_item.text().strip() if lcsc_item else ""
            if value and footprint and lcsc_pn:
                save_lcsc_pn(value, footprint, lcsc_pn)
        for value, footprint in self._to_clear:
            clear_lcsc_pn(value, footprint)
        self.accept()
