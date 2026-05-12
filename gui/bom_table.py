from PyQt6.QtCore import Qt, QAbstractTableModel, QModelIndex, pyqtSignal, QTimer
from PyQt6.QtGui import QColor, QBrush
from PyQt6.QtWidgets import QComboBox, QStyledItemDelegate

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

# value + footprint are editable so users can normalise names (e.g. C_0805_2012Metric → C0805)
# and have those drive Part Dictionary lookups.
_EDITABLE = {"value", "footprint", "mpn", "manufacturer", "digikey_pn", "mouser_pn", "lcsc_pn", "notes", "packaging"}


class BomTableModel(QAbstractTableModel):
    packaging_changed = pyqtSignal(int, str)
    key_cell_edited = pyqtSignal(int, str)        # row_idx, column_key  (value edits)
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
            return str(v) if v != "" else ""

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
        self._rows[index.row()][key] = value
        self.dataChanged.emit(index, index)
        if key == "packaging":
            self.packaging_changed.emit(index.row(), value)
        elif key == "footprint":
            self.footprint_edited.emit(index.row(), old_value, value)
        elif key == "value":
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
        self._rows[row_idx].update(data)
        tl = self.index(row_idx, 0)
        br = self.index(row_idx, len(COLUMNS) - 1)
        self.dataChanged.emit(tl, br)

    def get_row(self, row_idx: int) -> dict:
        return dict(self._rows[row_idx]) if 0 <= row_idx < len(self._rows) else {}

    def get_all_rows(self) -> list[dict]:
        return [dict(r) for r in self._rows]


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
