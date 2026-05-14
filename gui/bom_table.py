from PyQt6.QtCore import Qt, QAbstractTableModel, QModelIndex, pyqtSignal, QTimer
from PyQt6.QtGui import QColor, QBrush
from PyQt6.QtWidgets import QApplication, QComboBox, QStyledItemDelegate, QTableView

PACKAGING_OPTIONS = ["Cut Tape", "Tape & Reel", "Digi-Reel/MouseReel"]

COLUMNS = [
    ("status",       ""),
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

_COL_KEYS = [k for k, _ in COLUMNS]

_STATUS_BG = {
    "green":  QColor("#92D050"),
    "yellow": QColor("#FFEB9C"),
    "red":    QColor("#FFC7CE"),
}
_STATUS_FG = {
    "green":  QColor("#1E7E34"),
    "yellow": QColor("#856404"),
    "red":    QColor("#721C24"),
}
_STATUS_SYMBOL = {"green": "●", "yellow": "◑", "red": "○"}

_EDITABLE = {
    "qty", "references",
    "value", "footprint", "mpn", "manufacturer",
    "digikey_pn", "mouser_pn", "lcsc_pn", "notes", "packaging",
}

# Keys whose edits should trigger a part-dictionary lookup / status recalc
_KEY_CELL_SIGNAL_KEYS = {"value", "lcsc_pn", "mpn", "digikey_pn", "mouser_pn", "qty", "references"}


class BomTableModel(QAbstractTableModel):
    packaging_changed = pyqtSignal(int, str)
    key_cell_edited = pyqtSignal(int, str)        # row_idx, column_key
    footprint_edited = pyqtSignal(int, str, str)  # row_idx, old_fp, new_fp

    def __init__(self):
        super().__init__()
        self._rows: list[dict] = []

    def rowCount(self, parent=QModelIndex()):
        return len(self._rows)

    def columnCount(self, parent=QModelIndex()):
        return len(COLUMNS)

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if orientation == Qt.Orientation.Horizontal and role == Qt.ItemDataRole.DisplayRole:
            return COLUMNS[section][1]
        return None

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        row = self._rows[index.row()]
        key = _COL_KEYS[index.column()]
        status = row.get("status", "red")

        if role == Qt.ItemDataRole.DisplayRole:
            if key == "status":
                return _STATUS_SYMBOL.get(status, "○")
            v = row.get(key, "")
            return str(v) if v not in ("", None) else ""

        if role == Qt.ItemDataRole.BackgroundRole:
            return QBrush(_STATUS_BG.get(status, QColor("white")))

        if role == Qt.ItemDataRole.ForegroundRole:
            if key == "status":
                return QBrush(_STATUS_FG.get(status, QColor("#1a1a1a")))
            return QBrush(QColor("#1a1a1a"))

        if role == Qt.ItemDataRole.TextAlignmentRole:
            if key in ("status", "qty", "stock"):
                return Qt.AlignmentFlag.AlignCenter

        if role == Qt.ItemDataRole.EditRole:
            return str(row.get(key, ""))

        if role == Qt.ItemDataRole.ToolTipRole:
            reason = row.get("status_reason", "")
            return reason if reason else None

        return None

    def flags(self, index):
        base = Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable
        if _COL_KEYS[index.column()] in _EDITABLE:
            return base | Qt.ItemFlag.ItemIsEditable
        return base

    def setData(self, index, value, role=Qt.ItemDataRole.EditRole):
        if role != Qt.ItemDataRole.EditRole:
            return False
        key = _COL_KEYS[index.column()]
        old_value = str(self._rows[index.row()].get(key, ""))
        if isinstance(value, str):
            value = value.strip()
        self._rows[index.row()][key] = value
        self.dataChanged.emit(index, index)
        if key == "packaging":
            self.packaging_changed.emit(index.row(), value)
        elif key == "footprint":
            self.footprint_edited.emit(index.row(), old_value, value)
        elif key in _KEY_CELL_SIGNAL_KEYS:
            self.key_cell_edited.emit(index.row(), key)
        return True

    # --- public helpers ---

    def set_rows(self, rows: list[dict]):
        self.beginResetModel()
        self._rows = [dict(r) for r in rows]
        self.endResetModel()

    def update_row(self, row_idx: int, data: dict):
        if not (0 <= row_idx < len(self._rows)):
            return
        self._rows[row_idx].update(
            {k: ("" if v is None else v) for k, v in data.items()}
        )
        tl = self.index(row_idx, 0)
        br = self.index(row_idx, len(COLUMNS) - 1)
        self.dataChanged.emit(tl, br)

    def get_row(self, row_idx: int) -> dict:
        return dict(self._rows[row_idx]) if 0 <= row_idx < len(self._rows) else {}

    def get_all_rows(self) -> list[dict]:
        return [dict(r) for r in self._rows]


class BomTableView(QTableView):
    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_V and event.modifiers() == Qt.KeyboardModifier.ControlModifier:
            self._paste()
            return
        super().keyPressEvent(event)

    def _paste(self):
        clipboard = QApplication.clipboard()
        model = self.model()
        hdr = self.horizontalHeader()
        if clipboard is None or model is None or hdr is None:
            return

        text = clipboard.text()
        if not text:
            return

        clipboard_rows = [row.split('\t') for row in text.splitlines()]

        selected = self.selectedIndexes()
        if not selected:
            return

        min_row = min(idx.row() for idx in selected)
        min_visual_col = min(hdr.visualIndex(idx.column()) for idx in selected)

        for clip_row_i, clip_row in enumerate(clipboard_rows):
            target_row = min_row + clip_row_i
            if target_row >= model.rowCount():
                break

            clip_col_i = 0
            for visual_col in range(min_visual_col, hdr.count()):
                if clip_col_i >= len(clip_row):
                    break
                logical_col = hdr.logicalIndex(visual_col)
                if hdr.isSectionHidden(logical_col):
                    continue
                idx = model.index(target_row, logical_col)
                if model.flags(idx) & Qt.ItemFlag.ItemIsEditable:
                    model.setData(idx, clip_row[clip_col_i])
                clip_col_i += 1


class PackagingDelegate(QStyledItemDelegate):
    packaging_changed = pyqtSignal(int, str)

    def createEditor(self, parent, option, index):
        cb = QComboBox(parent)
        cb.addItems(PACKAGING_OPTIONS)
        QTimer.singleShot(0, cb.showPopup)
        return cb

    def setEditorData(self, editor, index):
        val = index.data(Qt.ItemDataRole.DisplayRole) or ""
        i = editor.findText(val)
        editor.setCurrentIndex(i if i >= 0 else 0)

    def setModelData(self, editor, model, index):
        chosen = editor.currentText()
        model.setData(index, chosen)
        self.packaging_changed.emit(index.row(), chosen)
