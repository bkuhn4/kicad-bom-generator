from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout,
    QLineEdit, QCheckBox, QPushButton, QGroupBox,
    QSpinBox, QComboBox, QLabel, QTabWidget, QWidget,
    QColorDialog,
)
from PyQt6.QtGui import QColor
from PyQt6.QtCore import Qt

from gui.workers import TestApiWorker


# ── color utilities ──────────────────────────────────────────────────────────

def _text_on(hex6: str) -> str:
    r, g, b = int(hex6[0:2], 16), int(hex6[2:4], 16), int(hex6[4:6], 16)
    return "#000000" if (0.299 * r + 0.587 * g + 0.114 * b) > 140 else "#FFFFFF"


# ── color swatch button ──────────────────────────────────────────────────────

class ColorSwatch(QPushButton):
    """Colored button that opens a QColorDialog when clicked."""

    def __init__(self, hex6: str, parent=None):
        super().__init__(parent)
        self.setFixedSize(96, 28)
        self.set_color(hex6)
        self.clicked.connect(self._pick)

    def set_color(self, hex6: str):
        self._hex = hex6.lstrip("#").upper()
        fg = _text_on(self._hex)
        self.setText(f"#{self._hex}")
        self.setStyleSheet(
            f"background-color:#{self._hex}; color:{fg}; "
            f"border:1px solid #888; border-radius:3px; font-weight:bold;"
        )

    def get_color(self) -> str:
        return self._hex

    def _pick(self):
        color = QColorDialog.getColor(QColor(f"#{self._hex}"), self, "Choose Color")
        if color.isValid():
            self.set_color(color.name()[1:])


# ── inline status label ──────────────────────────────────────────────────────

class _StatusLabel(QLabel):
    def __init__(self):
        super().__init__("")
        self.setWordWrap(True)
        self.setStyleSheet("color:#555; font-style:italic;")
        self.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)

    def set_pending(self, msg: str):
        self.setText(msg)
        self.setStyleSheet("color:#856404; font-style:italic;")

    def set_result(self, ok: bool, msg: str):
        self.setText(("✓ " if ok else "✗ ") + msg)
        self.setStyleSheet("color:#155724; font-weight:bold;" if ok else "color:#721C24; font-weight:bold;")
        self.setToolTip(msg)


# ── main dialog ──────────────────────────────────────────────────────────────

_PRESETS = [
    ("Olive Green",  "4F6228"),
    ("Steel Blue",   "4472C4"),
    ("Dark Teal",    "1F7391"),
    ("Burgundy",     "843C0C"),
    ("Purple",       "4B3080"),
    ("Charcoal",     "404040"),
]


class SettingsDialog(QDialog):
    def __init__(self, config: dict, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.setMinimumWidth(520)
        self._workers: list[TestApiWorker] = []

        tabs = QTabWidget()
        tabs.addTab(self._api_tab(config), "API Keys")
        tabs.addTab(self._export_tab(config), "Export")
        tabs.addTab(self._prefs_tab(config), "Preferences")

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        save = QPushButton("Save")
        save.setDefault(True)
        save.clicked.connect(self.accept)
        cancel = QPushButton("Cancel")
        cancel.clicked.connect(self.reject)
        btn_row.addWidget(save)
        btn_row.addWidget(cancel)

        root = QVBoxLayout(self)
        root.addWidget(tabs)
        root.addLayout(btn_row)

    # ── Tab builders ─────────────────────────────────────────────────────────

    def _api_tab(self, cfg: dict) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)

        # DigiKey
        dk = cfg.get("digikey", {})
        dk_grp = QGroupBox("Digi-Key API")
        dk_form = QFormLayout(dk_grp)
        self.dk_id = QLineEdit(dk.get("client_id", ""))
        self.dk_secret = QLineEdit(dk.get("client_secret", ""))
        self.dk_secret.setEchoMode(QLineEdit.EchoMode.Password)
        self.dk_sandbox = QCheckBox("Use Sandbox")
        self.dk_sandbox.setChecked(dk.get("sandbox", False))
        dk_test_btn = QPushButton("Test Connection")
        dk_test_btn.clicked.connect(self._test_digikey)
        self.dk_status = _StatusLabel()
        dk_form.addRow("Client ID:", self.dk_id)
        dk_form.addRow("Client Secret:", self.dk_secret)
        dk_form.addRow("", self.dk_sandbox)
        dk_form.addRow("", dk_test_btn)
        dk_form.addRow("", self.dk_status)
        layout.addWidget(dk_grp)

        # Mouser
        mu = cfg.get("mouser", {})
        mu_grp = QGroupBox("Mouser API")
        mu_form = QFormLayout(mu_grp)
        self.mu_key = QLineEdit(mu.get("api_key", ""))
        self.mu_key.setEchoMode(QLineEdit.EchoMode.Password)
        mu_test_btn = QPushButton("Test Connection")
        mu_test_btn.clicked.connect(self._test_mouser)
        self.mu_status = _StatusLabel()
        mu_form.addRow("API Key:", self.mu_key)
        mu_form.addRow("", mu_test_btn)
        mu_form.addRow("", self.mu_status)
        layout.addWidget(mu_grp)

        layout.addStretch()
        return w

    def _export_tab(self, cfg: dict) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)

        exp = cfg.get("export", {})
        current_color = exp.get("header_color", "4F6228")

        grp = QGroupBox("Table Style")
        grp_layout = QVBoxLayout(grp)

        # Header color row
        hdr_row = QHBoxLayout()
        hdr_row.addWidget(QLabel("Header Color:"))
        self.color_swatch = ColorSwatch(current_color)
        hdr_row.addWidget(self.color_swatch)
        hdr_row.addStretch()
        grp_layout.addLayout(hdr_row)

        # Preset buttons
        preset_label = QLabel("Presets:")
        grp_layout.addWidget(preset_label)
        preset_row = QHBoxLayout()
        for name, color in _PRESETS:
            btn = QPushButton(name)
            fg = _text_on(color)
            btn.setStyleSheet(
                f"background-color:#{color}; color:{fg}; "
                f"border:1px solid #888; border-radius:3px; padding:3px 8px;"
            )
            btn.clicked.connect(lambda checked, c=color: self.color_swatch.set_color(c))
            preset_row.addWidget(btn)
        grp_layout.addLayout(preset_row)

        # Info note
        note = QLabel(
            "The stripe rows use an auto-lightened tint of the header color.\n"
            "All cell borders use the same header color."
        )
        note.setStyleSheet("color:#555; font-style:italic; padding-top:6px;")
        grp_layout.addWidget(note)

        layout.addWidget(grp)
        layout.addStretch()
        return w

    def _prefs_tab(self, cfg: dict) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)

        grp = QGroupBox("Defaults")
        form = QFormLayout(grp)

        self.default_pkg = QComboBox()
        self.default_pkg.addItems(["Cut Tape", "Tape & Reel", "Digi-Reel"])
        idx = self.default_pkg.findText(cfg.get("default_packaging", "Cut Tape"))
        self.default_pkg.setCurrentIndex(idx if idx >= 0 else 0)

        self.low_stock = QSpinBox()
        self.low_stock.setRange(0, 100_000)
        self.low_stock.setValue(cfg.get("low_stock_threshold", 10))
        self.low_stock.setSuffix(" units")

        form.addRow("Default Packaging:", self.default_pkg)
        form.addRow("Low-Stock Threshold:", self.low_stock)
        layout.addWidget(grp)
        layout.addStretch()
        return w

    # ── test helpers ─────────────────────────────────────────────────────────

    def _test_digikey(self):
        from api.digikey import DigiKeyClient
        self.dk_status.set_pending("Testing — a browser may open for OAuth2 login…")
        w = TestApiWorker(DigiKeyClient(self._current_config()).test_connection)
        w.done.connect(self.dk_status.set_result)
        w.start()
        self._workers.append(w)

    def _test_mouser(self):
        from api.mouser import MouserClient
        self.mu_status.set_pending("Testing…")
        w = TestApiWorker(MouserClient(self._current_config()).test_connection)
        w.done.connect(self.mu_status.set_result)
        w.start()
        self._workers.append(w)

    # ── getters ──────────────────────────────────────────────────────────────

    def _current_config(self) -> dict:
        return {
            "digikey": {
                "client_id":     self.dk_id.text().strip(),
                "client_secret": self.dk_secret.text().strip(),
                "sandbox":       self.dk_sandbox.isChecked(),
            },
            "mouser": {"api_key": self.mu_key.text().strip()},
            "export": {"header_color": self.color_swatch.get_color()},
            "default_packaging":   self.default_pkg.currentText(),
            "low_stock_threshold": self.low_stock.value(),
        }

    def get_config(self) -> dict:
        return self._current_config()
