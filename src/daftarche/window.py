import os
import shutil

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QTabWidget, QWidget, QVBoxLayout,
    QHBoxLayout, QDialog, QFormLayout, QLabel,
    QDialogButtonBox, QPushButton, QColorDialog, QFrame, QGridLayout,
    QMessageBox, QFileDialog, QSizePolicy
)
from PySide6.QtGui import QFont, QColor, QPalette

from daftarche.db import Database
from daftarche.app_info import APP_NAME
from daftarche.backup import copy_db, mirror_snapshots, startup_backup
from daftarche.paths import BACKUP_DIR, DB_PATH
from daftarche.style import build_stylesheet, get_settings, DEFAULTS
from daftarche.widgets import StepSpinBox, SingleSelectCombo

from daftarche.tabs.transactions import TransactionsTab
from daftarche.tabs.import_tab import ImportTab
from daftarche.tabs.manage import ManageDialog
from daftarche.tabs.dashboard import DashboardTab
from daftarche.tabs.charts import ChartsTab
from daftarche.tabs.accounts import AccountsTab


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        self.setWindowTitle(APP_NAME)
        self.setMinimumSize(1280, 800)

        self.db_path = DB_PATH
        self.db = Database(self.db_path)
        self.settings = get_settings()

        self._auto_backup()
        self._apply_style()

        central = QWidget()
        self.main_layout = QVBoxLayout(central)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(0)
        self.main_layout.addLayout(self._build_top_bar())
        self.main_layout.addWidget(self._build_tabs(), 1)
        self.setCentralWidget(central)

        self._refresh_all()

    # ── UI construction ───────────────────────────────────────────────────────
    def _build_top_bar(self):
        btn_backup = QPushButton("💾  Backup")
        btn_restore = QPushButton("↩️  Restore")
        btn_settings = QPushButton("⚙️  Settings")
        btn_manage = QPushButton("🗂  Manage")

        btn_restore.setProperty("class", "secondary")
        btn_settings.setProperty("class", "secondary")
        btn_manage.setProperty("class", "secondary")

        # Connections
        btn_backup.clicked.connect(self._save_backup)
        btn_restore.clicked.connect(self._restore_backup)
        btn_settings.clicked.connect(self.open_settings)
        btn_manage.clicked.connect(self._open_manage)

        # Layout
        top_bar = QHBoxLayout()
        top_bar.setContentsMargins(8, 4, 8, 4)
        top_bar.setSpacing(4)
        top_bar.addStretch(1)
        for btn in [btn_backup, btn_restore, btn_settings, btn_manage]:
            btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
            top_bar.addWidget(btn)
        return top_bar

    def _build_tabs(self):
        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)

        self.dashboard_tab = DashboardTab(self.db)
        self.transactions_tab = TransactionsTab(self.db, self._refresh_all)
        self.charts_tab = ChartsTab(self.db)
        self.accounts_tab = AccountsTab(self.db)
        self.import_tab = ImportTab(self.db, self._refresh_all)

        self.tabs.addTab(self.dashboard_tab, "📊  Dashboard")
        self.tabs.addTab(self.transactions_tab, "📋  Transactions")
        self.tabs.addTab(self.charts_tab, "📈  Charts")
        self.tabs.addTab(self.accounts_tab, "🏦  Accounts")
        self.tabs.addTab(self.import_tab, "📥  Import")
        return self.tabs

    def _rebuild_tabs(self):
        old_tabs = self.tabs
        self.tabs = self._build_tabs()
        self.main_layout.replaceWidget(old_tabs, self.tabs)
        old_tabs.deleteLater()

    # ── Styling ───────────────────────────────────────────────────────────────
    def _apply_style(self):
        self.setStyleSheet(build_stylesheet(self.settings))

        font_family = self.settings.get("font_family")
        font_size = self.settings.get("font_size")
        QApplication.instance().setFont(QFont(font_family, font_size))

        accent = QColor(self.settings.get("accent"))
        highlight = QColor(accent)
        highlight.setAlpha(90)

        palette = QApplication.instance().palette()
        palette.setColor(QPalette.Highlight, highlight)
        palette.setColor(QPalette.HighlightedText, QColor(self.settings.get("text")))
        QApplication.instance().setPalette(palette)

    # ── Refresh callbacks ─────────────────────────────────────────────────────
    def _refresh_all(self):
        self.transactions_tab.refresh()
        self.dashboard_tab.refresh()
        self.charts_tab.refresh()
        self.accounts_tab.refresh()

    # ── Dialogs ───────────────────────────────────────────────────────────────
    def open_settings(self):
        dlg = SettingsDialog(self.settings, self)
        if dlg.exec():
            self._apply_style()
            self._refresh_all()

    def _open_manage(self):
        if hasattr(self, "_manage_dlg") and self._manage_dlg is not None:
            self._manage_dlg.raise_()
            self._manage_dlg.activateWindow()
            return
        self._manage_dlg = ManageDialog(self.db, self._refresh_all, self)
        self._manage_dlg.finished.connect(lambda: setattr(self, "_manage_dlg", None))
        self._manage_dlg.show()

    # ── Backup / restore ──────────────────────────────────────────────────────
    def _backup_db_to(self, destination_path):
        if destination_path:
            copy_db(self.db.conn, destination_path)

    def _auto_backup(self):
        try:
            startup_backup(self.db.conn, extra_dir=self.settings.get("backup_extra_dir"))
        except Exception as exc:
            print(f"Auto-backup failed: {exc}")

    def _save_backup(self):
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Save Backup",
            str(BACKUP_DIR / "daftarche-backup.db"),
            "Database (*.db)"
        )

        if not path:
            return

        try:
            self._backup_db_to(path)
            QMessageBox.information(self, "Backup", f"Backup saved to:\n{path}")
        except Exception as exc:
            QMessageBox.critical(self, "Backup Failed", f"Could not save backup:\n{exc}")

    def _restore_backup(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Restore Backup",
            "",
            "Database (*.db)"
        )

        if not path:
            return

        reply = QMessageBox.question(
            self,
            "Restore",
            "This will replace your current data with the selected backup.\n\nAre you sure?",
            QMessageBox.Yes | QMessageBox.No
        )

        if reply != QMessageBox.Yes:
            return

        try:
            self.db.conn.close()
            shutil.copy2(path, self.db_path)

            self.db = Database(self.db_path)
            self._rebuild_tabs()
            self._refresh_all()

            QMessageBox.information(self, "Restored", "Backup restored successfully.")

        except Exception as exc:
            QMessageBox.critical(self, "Restore Failed", f"Could not restore backup:\n{exc}")


class SettingsDialog(QDialog):
    COLOR_KEYS_COL_1 = [
        ("accent", "Accent"),
        ("bg_base", "Background"),
        ("bg_surface", "Surface"),
        ("bg_raised", "Raised"),
        ("text", "Text"),
    ]
    COLOR_KEYS_COL_2 = [
        ("income", "Income Color"),
        ("expense", "Expense Color"),
        ("transfer", "Transfer Color"),
    ]

    def __init__(self, settings, parent=None):
        super().__init__(parent)

        self.settings = settings
        self.setWindowTitle("Settings")

        self._color_btns = {}
        self._pending_colors = {
            key: self.settings.get(key)
            for key, _ in self.COLOR_KEYS_COL_1 + self.COLOR_KEYS_COL_2
        }
        self._pending_extra_dir = self.settings.get("backup_extra_dir") or ""

        self._build()
        self.setFixedSize(self.sizeHint())

    def _build(self):
        fs = self.settings.get("font_size")
        ff = self.settings.get("font_family")

        title = QLabel("Appearance Settings")
        title.setProperty("class", "settings-title")

        self.f_font = SingleSelectCombo()
        self.f_font.addItems([
            "Helvetica Neue",
            "Helvetica",
            "Arial",
            "Verdana",
            "Tahoma",
        ])
        idx = self.f_font.findText(ff)
        if idx >= 0:
            self.f_font.setCurrentIndex(idx)
        self.f_size = StepSpinBox(value=fs, min_val=8, max_val=18, step=1, decimals=0)

        colors_lbl = QLabel("Colors")
        colors_lbl.setProperty("class", "settings-section")

        color_grid = QGridLayout()
        color_grid.setSpacing(10)
        for i, (key, label) in enumerate(self.COLOR_KEYS_COL_1):
            lbl = QLabel(label)
            btn = QPushButton()
            self._set_btn_color(btn, self._pending_colors[key])
            btn.clicked.connect(lambda checked=False, k=key: self._pick_color(k))
            self._color_btns[key] = btn
            color_grid.addWidget(lbl, i, 0)
            color_grid.addWidget(btn, i, 1)

        for i, (key, label) in enumerate(self.COLOR_KEYS_COL_2):
            lbl = QLabel(label)
            btn = QPushButton()
            self._set_btn_color(btn, self._pending_colors[key])
            btn.clicked.connect(lambda checked=False, k=key: self._pick_color(k))
            self._color_btns[key] = btn
            color_grid.addWidget(lbl, i, 3)
            color_grid.addWidget(btn, i, 4)

        color_grid.setColumnMinimumWidth(1, 60)
        color_grid.setColumnMinimumWidth(2, 40)
        color_grid.setColumnMinimumWidth(4, 60)

        backups_lbl = QLabel("Backups")
        backups_lbl.setProperty("class", "settings-section")
        self.lbl_extra_dir = QLabel()
        self.lbl_extra_dir.setWordWrap(True)
        self._show_extra_dir()
        btn_extra_choose = QPushButton("Choose…")
        btn_extra_choose.clicked.connect(self._choose_extra_dir)
        btn_extra_clear = QPushButton("Clear")
        btn_extra_clear.setProperty("class", "secondary")
        btn_extra_clear.clicked.connect(lambda: self._set_extra_dir(""))
        extra_row = QHBoxLayout()
        extra_row.addWidget(QLabel("Extra backup folder:"))
        extra_row.addWidget(self.lbl_extra_dir, 1)
        extra_row.addWidget(btn_extra_choose)
        extra_row.addWidget(btn_extra_clear)

        btn_reset = QPushButton("Reset to Defaults")
        btn_reset.setProperty("class", "secondary")
        btn_reset.clicked.connect(self._reset)
        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(self._save)
        btns.rejected.connect(self.reject)

        form = QFormLayout()
        form.setSpacing(10)
        form.addRow("Font Family:", self.f_font)
        form.addRow("Font Size:", self.f_size)

        btn_row = QHBoxLayout()
        btn_row.addWidget(btn_reset)
        btn_row.addStretch()
        btn_row.addWidget(btns)

        layout = QVBoxLayout(self)
        layout.setSpacing(16)

        layout.addWidget(title)
        layout.addLayout(form)
        layout.addWidget(self._sep())
        layout.addWidget(colors_lbl)
        layout.addLayout(color_grid)
        layout.addWidget(self._sep())
        layout.addWidget(backups_lbl)
        layout.addLayout(extra_row)
        layout.addWidget(self._sep())
        layout.addLayout(btn_row)

    def _show_extra_dir(self):
        path = self._pending_extra_dir.replace(os.path.expanduser("~"), "~", 1)
        path = path.replace("~/Library/Mobile Documents/com~apple~CloudDocs", "iCloud Drive", 1)
        self.lbl_extra_dir.setText(path or "none (monthly snapshots stay on this Mac only)")
        self.lbl_extra_dir.setToolTip(self._pending_extra_dir)

    def _set_extra_dir(self, path):
        self._pending_extra_dir = path
        self._show_extra_dir()
        self.setFixedSize(self.sizeHint())

    def _choose_extra_dir(self):
        path = QFileDialog.getExistingDirectory(self, "Extra Backup Folder", self._pending_extra_dir or "")
        if path:
            self._set_extra_dir(path)

    def _sep(self):
        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        return sep

    def _default_value(self, key):
        if hasattr(DEFAULTS, "get"):
            return DEFAULTS.get(key, self.settings.get(key))
        return self.settings.get(key)

    def _set_btn_color(self, btn, color):
        btn.setStyleSheet(f"background: {color}; border: 1px solid #555; border-radius: 4px;")
        # btn.setText(color)

    def _pick_color(self, key):
        current = QColor(self._pending_colors[key])
        color = QColorDialog.getColor(current, self, f"Choose color for {key}")

        if color.isValid():
            hex_color = color.name()
            self._pending_colors[key] = hex_color
            self._set_btn_color(self._color_btns[key], hex_color)

    def _save(self):
        self.settings.set("font_family", self.f_font.currentText())
        self.settings.set("font_size", int(self.f_size.value()))

        for key, color in self._pending_colors.items():
            self.settings.set(key, color)

        self.settings.set("backup_extra_dir", self._pending_extra_dir)
        try:
            mirror_snapshots(self._pending_extra_dir)
        except OSError as exc:
            QMessageBox.warning(self, "Extra Backup", f"Could not copy the backups to\n{self._pending_extra_dir}:\n{exc}")

        self.accept()

    def _reset(self):
        default_font = self._default_value("font_family")
        default_size = self._default_value("font_size")

        self.f_font.setCurrentText(default_font)
        self.f_size.setValue(default_size)

        for key, btn in self._color_btns.items():
            default_color = self._default_value(key)
            self._pending_colors[key] = default_color
            self._set_btn_color(btn, default_color)
