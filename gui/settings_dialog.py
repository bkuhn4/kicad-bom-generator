from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout,
    QLineEdit, QCheckBox, QPushButton, QGroupBox,
    QSpinBox, QComboBox, QLabel, QTabWidget, QWidget,
    QColorDialog, QScrollArea, QGridLayout,
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
        from gui.bom_table import COLUMNS as TABLE_COLUMNS

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        inner = QWidget()
        layout = QVBoxLayout(inner)

        exp = cfg.get("export", {})

        # ── project info ──────────────────────────────────────────────────────
        proj_grp = QGroupBox("Project Info")
        proj_form = QFormLayout(proj_grp)
        self.project_name = QLineEdit(exp.get("project_name", ""))
        self.project_name.setPlaceholderText("e.g. Motor Controller Board")
        self.revision = QLineEdit(exp.get("revision", ""))
        self.revision.setPlaceholderText("e.g. 1.0")
        self.show_title_cb = QCheckBox("Include title and revision in header")
        self.show_title_cb.setChecked(exp.get("show_title", True))
        self.show_footer_cb = QCheckBox("Include date/time in footer  (Created: …)")
        self.show_footer_cb.setChecked(exp.get("show_footer", True))
        proj_form.addRow("Project Name:", self.project_name)
        proj_form.addRow("Revision:", self.revision)
        proj_form.addRow(self.show_title_cb)
        proj_form.addRow(self.show_footer_cb)
        layout.addWidget(proj_grp)

        # ── header color ──────────────────────────────────────────────────────
        current_color = exp.get("header_color", "4F6228")

        style_grp = QGroupBox("Table Style")
        grp_layout = QVBoxLayout(style_grp)

        hdr_row = QHBoxLayout()
        hdr_row.addWidget(QLabel("Header Color:"))
        self.color_swatch = ColorSwatch(current_color)
        hdr_row.addWidget(self.color_swatch)
        hdr_row.addStretch()
        grp_layout.addLayout(hdr_row)

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

        layout.addWidget(style_grp)

        # ── column visibility ─────────────────────────────────────────────────
        col_cfg = cfg.get("columns", {})
        col_grp = QGroupBox("Column Visibility")
        grid = QGridLayout(col_grp)
        grid.setColumnStretch(0, 1)

        grid.addWidget(QLabel("<b>Column</b>"),  0, 0)
        grid.addWidget(QLabel("<b>Show</b>"),    0, 1, Qt.AlignmentFlag.AlignCenter)
        grid.addWidget(QLabel("<b>Export</b>"),  0, 2, Qt.AlignmentFlag.AlignCenter)

        self._col_checks: dict[str, tuple[QCheckBox, QCheckBox]] = {}
        for row_i, (key, label) in enumerate(TABLE_COLUMNS, 1):
            if key == "status":
                continue
            defaults = col_cfg.get(key, {"show": True, "export": True})
            show_cb   = QCheckBox()
            export_cb = QCheckBox()
            show_cb.setChecked(defaults.get("show",   True))
            export_cb.setChecked(defaults.get("export", True))
            grid.addWidget(QLabel(label), row_i, 0)
            grid.addWidget(show_cb,   row_i, 1, Qt.AlignmentFlag.AlignCenter)
            grid.addWidget(export_cb, row_i, 2, Qt.AlignmentFlag.AlignCenter)
            self._col_checks[key] = (show_cb, export_cb)

        layout.addWidget(col_grp)
        layout.addStretch()
        scroll.setWidget(inner)
        return scroll

    def _prefs_tab(self, cfg: dict) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)

        grp = QGroupBox("Defaults")
        form = QFormLayout(grp)

        self.default_pkg = QComboBox()
        self.default_pkg.addItems(["Cut Tape", "Tape & Reel", "Digi-Reel/MouseReel"])
        idx = self.default_pkg.findText(cfg.get("default_packaging", "Cut Tape"))
        self.default_pkg.setCurrentIndex(idx if idx >= 0 else 0)

        self.low_stock = QSpinBox()
        self.low_stock.setRange(0, 100_000)
        self.low_stock.setValue(cfg.get("low_stock_threshold", 10))
        self.low_stock.setSuffix(" units")

        self.compress_refs = QCheckBox("Compress reference ranges  (e.g. R1, R2, R3 → R1-R3)")
        self.compress_refs.setChecked(cfg.get("compress_references", True))

        compress_note = QLabel(
            "Disable this for JLC PCBA BOMs — JLCPCB requires each designator listed "
            "individually (e.g. R1, R2, R3), not as a range."
        )
        compress_note.setWordWrap(True)
        compress_note.setStyleSheet("color: #666; font-style: italic; margin-left: 22px;")

        form.addRow("Default Packaging:", self.default_pkg)
        form.addRow("Low-Stock Threshold:", self.low_stock)
        form.addRow(self.compress_refs)
        form.addRow(compress_note)
        layout.addWidget(grp)
        layout.addStretch()
        return w

    # ── test helpers ─────────────────────────────────────────────────────────

    def _test_digikey(self):
        from api.digikey import DigiKeyClient, AUTH_REQUIRED
        cfg    = self._current_config()
        client = DigiKeyClient(cfg)

        if not client.is_configured():
            self.dk_status.set_result(False, "Client ID or Secret is empty.")
            return

        if not client.has_token():
            self._start_digikey_oauth(client)
            return

        self.dk_status.set_pending("Testing connection…")
        w = TestApiWorker(client.test_connection)
        w.done.connect(lambda ok, msg: self._on_dk_test_done(ok, msg, client))
        w.start()
        self._workers.append(w)

    def _on_dk_test_done(self, ok: bool, msg: str, client):
        from api.digikey import AUTH_REQUIRED
        if not ok and msg == AUTH_REQUIRED:
            self._start_digikey_oauth(client)
        else:
            self.dk_status.set_result(ok, msg)

    def _start_digikey_oauth(self, client):
        import webbrowser
        from urllib.parse import urlparse, parse_qs
        from PyQt6.QtWidgets import (
            QDialog, QVBoxLayout, QLabel, QLineEdit, QDialogButtonBox, QApplication,
        )
        from PyQt6.QtCore import Qt

        webbrowser.open(client.build_auth_url())

        dlg = QDialog(self)
        dlg.setWindowTitle("DigiKey Authorization")
        dlg.setMinimumWidth(540)
        layout = QVBoxLayout(dlg)

        msg = QLabel(
            "<b>Step 1:</b> Log in to DigiKey in the browser that just opened.<br><br>"
            "<b>Step 2:</b> After logging in, your browser will redirect and will likely "
            "show <i>\"This site can't be reached\"</i> — that is expected and normal.<br><br>"
            "<b>Step 3:</b> Copy the <b>full URL</b> from your browser's address bar "
            "and paste it below:"
        )
        msg.setWordWrap(True)
        msg.setTextFormat(Qt.TextFormat.RichText)
        layout.addWidget(msg)

        url_input = QLineEdit()
        url_input.setPlaceholderText("https://localhost:8139/digikey_callback?code=…")
        layout.addWidget(url_input)

        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        btns.accepted.connect(dlg.accept)
        btns.rejected.connect(dlg.reject)
        layout.addWidget(btns)

        if dlg.exec() != QDialog.DialogCode.Accepted:
            self.dk_status.set_result(False, "Authorization cancelled.")
            return

        pasted = url_input.text().strip()
        if not pasted:
            self.dk_status.set_result(False, "No URL entered.")
            return

        # Accept either a full callback URL or just the bare code
        if pasted.startswith("http"):
            try:
                params = parse_qs(urlparse(pasted).query)
                code = params.get("code", [None])[0]
            except Exception:
                code = None
        else:
            code = pasted  # user pasted just the code value

        if not code:
            self.dk_status.set_result(False, "Could not find 'code=' in the URL. Make sure you copied the full address bar URL.")
            return

        self.dk_status.set_pending("Exchanging code for access token…")
        QApplication.processEvents()

        ok, err = client.exchange_code_for_token(code)
        if not ok:
            self.dk_status.set_result(False, f"Token exchange failed: {err}")
            return

        self.dk_status.set_pending("Token saved. Testing connection…")
        w = TestApiWorker(client.test_connection)
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
            "export": {
                "header_color": self.color_swatch.get_color(),
                "project_name": self.project_name.text().strip(),
                "revision":     self.revision.text().strip(),
                "show_title":   self.show_title_cb.isChecked(),
                "show_footer":  self.show_footer_cb.isChecked(),
            },
            "default_packaging":   self.default_pkg.currentText(),
            "low_stock_threshold": self.low_stock.value(),
            "compress_references": self.compress_refs.isChecked(),
            "columns": {
                key: {
                    "show":   show_cb.isChecked(),
                    "export": export_cb.isChecked(),
                }
                for key, (show_cb, export_cb) in self._col_checks.items()
            },
        }

    def get_config(self) -> dict:
        return self._current_config()
