import html
import os
import shutil
from pathlib import Path

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QTabWidget, QWidget, QVBoxLayout,
    QHBoxLayout, QDialog, QFormLayout, QLabel,
    QDialogButtonBox, QPushButton, QColorDialog, QFrame, QGridLayout,
    QMessageBox, QFileDialog
)
from PySide6.QtCore import Qt, QTimer, QUrl
from PySide6.QtGui import QAction, QColor, QDesktopServices, QFont, QKeySequence, QPalette
from sciwidgets.dialogs import show_about_dialog

from daftarche.db import Database
from daftarche.app_info import APP, APP_NAME
from daftarche.backup import copy_db, copy_for_viewing, mirror_snapshots, restore_backup, startup_backup
from daftarche.overview import UnmatchedTransfersDialog
from daftarche.paths import BACKUP_DIR, DATA_DIR, DB_PATH
from daftarche.style import build_stylesheet, get_settings, DEFAULTS, THEMES, THEME_NAMES, system_theme
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
        self.viewing = None  # the file shown by Open Database… (a temporary copy of it is open)
        self._view_copy = None
        self.settings = get_settings()

        self._auto_backup()
        self._apply_style()

        central = QWidget()
        self.main_layout = QVBoxLayout(central)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(0)
        self.main_layout.addWidget(self._build_view_bar())
        self.main_layout.addWidget(self._build_tabs(), 1)
        self.setCentralWidget(central)
        self._build_menus()

        self._refresh_all()
        # Match macOS: the Mac switching between light and dark (e.g. Auto at sunset) switches too
        QApplication.styleHints().colorSchemeChanged.connect(self._system_theme_changed)

    def _system_theme_changed(self, *_):
        if self.settings.theme() == "system":
            self._restyle()

    def _restyle(self):
        """New colours: the style, then every tab (the one on screen now, the others when shown)."""
        self._apply_style()
        self._stale.update((self.dashboard_tab, self.transactions_tab, self.charts_tab, self.accounts_tab))
        self._refresh_all()
        for name in ("_manage_dlg", "_loans_dlg"):
            if getattr(self, name, None) is not None:
                getattr(self, name).refresh()

    # ── UI construction ───────────────────────────────────────────────────────
    def _build_menus(self):
        bar = self.menuBar()
        bar.setNativeMenuBar(False)

        def add(menu, text, slot, shortcut=None):
            action = menu.addAction(text, slot)
            action.setMenuRole(QAction.MenuRole.NoRole)
            if shortcut is not None:
                action.setShortcut(shortcut)
            return action

        file_menu = bar.addMenu("File")
        add(file_menu, "Import Statement…", lambda: self.open_import(), QKeySequence("Ctrl+I"))
        add(file_menu, "Export Transactions…", self._export, QKeySequence("Ctrl+E"))
        file_menu.addSeparator()
        add(file_menu, "Open Database…", self.open_database, QKeySequence("Ctrl+O"))
        self.back_action = add(file_menu, "Back to My Database", self.back_to_my_database, QKeySequence("Ctrl+Shift+O"))
        file_menu.addSeparator()
        self.backup_action = add(file_menu, "Back Up Database…", self._save_backup, QKeySequence("Ctrl+S"))
        self.restore_action = add(file_menu, "Restore Backup…", self._restore_backup)  # no shortcut: it replaces data
        file_menu.addSeparator()
        add(file_menu, "Show Data Folder", self._show_data_folder)
        file_menu.addSeparator()
        add(file_menu, "Quit", QApplication.instance().quit, QKeySequence("Ctrl+Q"))

        edit_menu = bar.addMenu("Edit")
        add(edit_menu, "Add Transaction…", self._add_transaction, QKeySequence("Ctrl+N"))
        add(edit_menu, "Find…", self._find, QKeySequence("Ctrl+F"))
        edit_menu.addSeparator()
        add(edit_menu, "Manage…", self._open_manage, QKeySequence("Ctrl+M"))
        add(edit_menu, "Settings…", self.open_settings, QKeySequence("Ctrl+,"))

        view_menu = bar.addMenu("View")
        review = add(view_menu, "To Review", self.show_uncategorized)
        review.setShortcuts([QKeySequence("Ctrl+Shift+R"), QKeySequence("Ctrl+Alt+U")])
        add(view_menu, "Unmatched Transfers…", self.show_unmatched_transfers, QKeySequence("Ctrl+Shift+U"))
        add(view_menu, "Loans…", self.open_loans, QKeySequence("Ctrl+Shift+L"))
        view_menu.addSeparator()
        add(view_menu, "Refresh", self._refresh_now, QKeySequence("Ctrl+R"))

        go_menu = bar.addMenu("Go")
        for i, (name, tab) in enumerate((("Dashboard", "dashboard_tab"), ("Transactions", "transactions_tab"),
                                         ("Charts", "charts_tab"), ("Accounts", "accounts_tab")), start=1):
            add(go_menu, name, lambda t=tab: self.tabs.setCurrentWidget(getattr(self, t)), QKeySequence(f"Ctrl+{i}"))
        go_menu.addSeparator()
        add(go_menu, "Back", lambda: self.transactions_tab.go_back(), QKeySequence("Ctrl+["))

        self.help_menu = bar.addMenu("Help")
        add(self.help_menu, "Show Data Folder", self._show_data_folder)
        self.help_menu.addSeparator()
        add(self.help_menu, f"About {APP_NAME}", self._show_about)
        self._update_view_state()

    def show_uncategorized(self, came_from=None):
        """The To review list (income and expenses with no category), in Transactions."""
        self.tabs.setCurrentWidget(self.transactions_tab)
        self.transactions_tab.show_to_review(came_from=came_from)

    def show_unmatched_transfers(self):
        def show(**filters):  # from a line of the window: "← Back to Unmatched Transfers" opens it again
            self._show_transactions(came_from=("Unmatched Transfers", self.show_unmatched_transfers), **filters)
        UnmatchedTransfersDialog(self.db, show, on_change=self._refresh_all, parent=self).exec()

    def _show_transactions(self, came_from=None, **filters):
        self.tabs.setCurrentWidget(self.transactions_tab)
        self.transactions_tab.show_matching(came_from=came_from, **filters)

    def _show_merchant(self, merchant):
        """Manage → Merchants: that merchant's transactions; Back brings Manage to the front."""
        def back():
            self._open_manage()
            self._manage_dlg.tabs.setCurrentWidget(self._manage_dlg.merchants_panel)
        self._show_transactions(came_from=("Manage", back), merchants=[merchant],
                                text=f"<b>{html.escape(merchant)}</b>: all its transactions")

    def open_loans(self):
        """View → Loans: a window, like Manage; double-clicking a person shows their loan rows."""
        from daftarche.loans_dialog import LoansDialog
        if getattr(self, "_loans_dlg", None) is not None:
            self._loans_dlg.refresh()
            self._loans_dlg.raise_()
            self._loans_dlg.activateWindow()
            return
        self._loans_dlg = LoansDialog(self.db, self._refresh_all, self._show_loan, self)
        self._loans_dlg.finished.connect(lambda: setattr(self, "_loans_dlg", None))
        self._loans_dlg.show()

    def _show_loan(self, person):
        """A person's Transfer › Loans rows; Back brings the Loans window to the front."""
        from daftarche.db import CAT_LOANS
        text = f"<b>{html.escape(person)}</b>: loan transactions" if person else "Loan transactions with no person"
        self._show_transactions(came_from=("Loans", self.open_loans), categories=[CAT_LOANS],
                                merchants=self.db.get_loan_names(person), text=text)

    def _close_windows(self):
        """Manage and Loans belong to the database on screen."""
        for name in ("_manage_dlg", "_loans_dlg"):
            if getattr(self, name, None) is not None:
                getattr(self, name).close()

    def _back_to_tab(self, name, tab):
        """(label, go back) for the Back bar: that tab, as it was left."""
        return name, lambda: self.tabs.setCurrentWidget(tab)

    # ── Menu commands for the Transactions tab ────────────────────────────────
    def _add_transaction(self):
        self.tabs.setCurrentWidget(self.transactions_tab)
        self.transactions_tab.add_transaction()

    def _find(self):
        self.tabs.setCurrentWidget(self.transactions_tab)
        self.transactions_tab.f_search.setFocus()
        self.transactions_tab.f_search.selectAll()

    def _export(self):
        self.tabs.setCurrentWidget(self.transactions_tab)
        self.transactions_tab.export()

    def _refresh_now(self):
        tab = self.tabs.currentWidget()
        if hasattr(tab, "refresh"):
            tab.refresh()

    # ── Import (a window: a task with a start and an end) ─────────────────────
    def open_import(self, paths=None):
        """The Import window, with ``paths`` already read when given (dropped files). After an
        import, Transactions shows just the new rows."""
        dialog = ImportDialog(self.db, self)
        if isinstance(paths, str):
            paths = [paths]
        if paths:
            dialog.tab.load_files(paths)
        dialog.exec()
        ids = dialog.imported_ids
        if ids:
            self._refresh_all()
            self.tabs.setCurrentWidget(self.transactions_tab)
            n = len(ids)
            self.transactions_tab.show_ids(ids, f"<b>Just imported</b>: {n} transaction{'s' if n != 1 else ''}")

    def dragEnterEvent(self, event):
        if self._dropped_statement(event):
            event.acceptProposedAction()

    def dropEvent(self, event):
        paths = self._dropped_statement(event)
        if paths:
            event.acceptProposedAction()
            self.open_import(paths)

    def _dropped_statement(self, event):
        """The QFX/OFX files being dragged onto the window (a list), or None."""
        urls = event.mimeData().urls() if event.mimeData().hasUrls() else []
        paths = [u.toLocalFile() for u in urls if u.isLocalFile()]
        statements = [p for p in paths if p.lower().endswith((".qfx", ".ofx"))]
        return statements if self.viewing is None and statements else None

    def _show_data_folder(self):
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(DATA_DIR)))

    def _show_about(self):
        show_about_dialog(
            f"About {APP_NAME}",
            f"<b>Version {APP.version}</b><br><br>"
            "Personal bookkeeping: bank statements (QFX/OFX), categories, transfers and charts.<br><br>"
            f'<a href="https://github.com/{APP.github_repo}">github.com/{APP.github_repo}</a><br>'
            "MIT License · Vahid Anari",
            parent=self, heading=APP_NAME)

    def _build_tabs(self):
        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)
        self._stale = set()

        self.dashboard_tab = DashboardTab(self.db)
        self.transactions_tab = TransactionsTab(self.db, self._refresh_all)
        self.charts_tab = ChartsTab(self.db)
        self.accounts_tab = AccountsTab(self.db)

        self.tabs.addTab(self.dashboard_tab, "📊  Dashboard")
        self.tabs.addTab(self.transactions_tab, "📋  Transactions")
        self.tabs.addTab(self.charts_tab, "📈  Charts")
        self.tabs.addTab(self.accounts_tab, "🏦  Accounts")
        self.tabs.currentChanged.connect(self._on_tab_changed)
        self.charts_tab.detail.openRequested.connect(
            lambda filters: self._show_transactions(came_from=self._back_to_tab("Charts", self.charts_tab), **filters))
        self.dashboard_tab.open_overview = (  # the Dashboard's warning: To review, or the transfers window
            lambda uncategorized: self.show_uncategorized(came_from=self._back_to_tab("Dashboard", self.dashboard_tab))
            if uncategorized else self.show_unmatched_transfers())
        return self.tabs

    def _rebuild_tabs(self):
        old_tabs = self.tabs
        self.tabs = self._build_tabs()
        self.main_layout.replaceWidget(old_tabs, self.tabs)
        old_tabs.hide()  # out of sight now: deleteLater waits for the event loop
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
        """After a change: refresh the tab on screen now, the others when they are next shown."""
        if getattr(self, "_loans_dlg", None) is not None:
            self._loans_dlg.refresh()
        current = self.tabs.currentWidget()
        for tab in (self.dashboard_tab, self.transactions_tab, self.charts_tab, self.accounts_tab):
            if tab is current:
                tab.refresh()
                self._stale.discard(tab)
            else:
                self._stale.add(tab)

    def _on_tab_changed(self, index):
        tab = self.tabs.widget(index)
        if tab in self._stale:
            self._stale.discard(tab)
            tab.refresh()

    # ── Dialogs ───────────────────────────────────────────────────────────────
    def open_settings(self):
        dlg = SettingsDialog(self.settings, self)
        if dlg.exec():
            self._restyle()

    def _open_manage(self):
        if hasattr(self, "_manage_dlg") and self._manage_dlg is not None:
            self._manage_dlg.raise_()
            self._manage_dlg.activateWindow()
            return
        self._manage_dlg = ManageDialog(self.db, self._refresh_all, self, show_merchant=self._show_merchant)
        self._manage_dlg.finished.connect(lambda: setattr(self, "_manage_dlg", None))
        self._manage_dlg.show()

    # ── Open another database (to look at) ────────────────────────────────────
    def _build_view_bar(self):
        self.view_bar = QFrame()
        self.view_bar.setStyleSheet("QFrame { background: #6b5a1e; } QLabel { color: #fff3c4; }")
        row = QHBoxLayout(self.view_bar)
        row.setContentsMargins(16, 6, 16, 6)
        self.view_label = QLabel()
        back = QPushButton("Back to my database")
        back.clicked.connect(self.back_to_my_database)
        row.addWidget(self.view_label, 1)
        row.addWidget(back)
        self.view_bar.hide()
        return self.view_bar

    def _update_view_state(self):
        viewing = self.viewing is not None
        self.view_bar.setVisible(viewing)
        if viewing:
            self.view_label.setText(f"Viewing a copy of <b>{self.viewing.name}</b> — changes are not kept")
            self.view_label.setToolTip(str(self.viewing))
        self.setWindowTitle(f"{APP_NAME} — {self.viewing.name} (copy)" if viewing else APP_NAME)
        self.back_action.setEnabled(viewing)
        for action in (self.backup_action, self.restore_action):  # they are about your own database
            action.setEnabled(not viewing)
        self.setAcceptDrops(not viewing)

    def _switch_to(self, db):
        self._close_windows()
        self.db.conn.close()
        self.db = db
        self._rebuild_tabs()
        self._refresh_all()
        self._update_view_state()

    def open_database(self):
        """Look at another database (a backup, say) without changing it or your own: a temporary
        copy of it is opened, and dropped on Back to My Database (or at quit)."""
        path, _ = QFileDialog.getOpenFileName(self, "Open Database (a copy, to look at)", str(BACKUP_DIR),
                                              "Database (*.db)")
        if not path:
            return
        try:
            copy = copy_for_viewing(path)
            db = Database(copy)
        except Exception as exc:
            QMessageBox.critical(self, "Open Database", f"Could not open {os.path.basename(path)}:\n\n{exc}")
            return
        old_copy = self._view_copy
        self.viewing, self._view_copy = Path(path), copy
        self._switch_to(db)
        self._drop_view_copy(old_copy)

    def back_to_my_database(self):
        if self.viewing is None:
            return
        old_copy = self._view_copy
        self.viewing = self._view_copy = None
        self._switch_to(Database(self.db_path))
        self._drop_view_copy(old_copy)

    @staticmethod
    def _drop_view_copy(copy):
        if copy is not None:
            shutil.rmtree(copy.parent, ignore_errors=True)

    def closeEvent(self, event):
        if self.viewing is not None:
            self.db.conn.close()
            self._drop_view_copy(self._view_copy)
        super().closeEvent(event)

    # ── Backup / restore ──────────────────────────────────────────────────────
    def _backup_db_to(self, destination_path):
        if destination_path:
            copy_db(self.db.conn, destination_path)

    def _auto_backup(self):
        try:
            startup_backup(self.db.conn, extra_dir=self.settings.get("backup_extra_dir"))
        except Exception as exc:  # the app still opens, but the problem stays in sight
            self.statusBar().showMessage(f"⚠️ Automatic backup failed: {exc}")

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
            str(BACKUP_DIR),
            "Database (*.db)"
        )

        if not path:
            return

        reply = QMessageBox.question(
            self,
            "Restore",
            "This will replace your current data with the selected backup.\n\n"
            "To only look at a backup, use File → Open Database… instead.\n\nReplace your data?",
            QMessageBox.Yes | QMessageBox.No
        )

        if reply != QMessageBox.Yes:
            return

        self._close_windows()
        try:
            safety = restore_backup(self.db.conn, path)
        except Exception as exc:
            QMessageBox.critical(self, "Restore Failed",
                                 f"Nothing was changed.\n\n{exc}")
            return

        self.db.conn.close()
        self.db = Database(self.db_path)
        self._rebuild_tabs()
        self._refresh_all()
        QMessageBox.information(self, "Restored",
                                f"Backup restored.\n\nYour data from before the restore was saved as\n{safety.name}\n"
                                "in the backups folder.")


class ImportDialog(QDialog):
    """File → Import Statement…: the statement preview and import, in a window of its own."""

    def __init__(self, db, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Import Statement")
        self.setAttribute(Qt.WA_DeleteOnClose)  # see CategoryDialog: nothing closed lingers until quit
        if parent is not None:
            self.resize(int(parent.width() * 0.9), int(parent.height() * 0.85))
        self.imported_ids = []  # kept on the Python side: read after the window is gone
        self._asked = False
        self.tab = ImportTab(db, self._done)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.tab)

    def showEvent(self, event):
        super().showEvent(event)
        if not self._asked and not self.tab.statements:
            self._asked = True  # opened from the menu: choose the file straight away
            QTimer.singleShot(0, self.tab, self.tab._browse_ofx)

    def _done(self):
        """Imported: close, and say what was added."""
        self.imported_ids = list(self.tab.imported_ids)
        self.accept()


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
        # each theme's colours, changed here until OK
        self._pending_themes = {t: self.settings.theme_colors(t) for t in THEMES}
        self._pending_theme = self.settings.theme()
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
        self.f_theme = SingleSelectCombo()
        for key, name in THEME_NAMES.items():
            self.f_theme.addItem(name, key)
        self.f_theme.setCurrentIndex(list(THEME_NAMES).index(self._pending_theme))
        self.f_theme.currentIndexChanged.connect(self._theme_changed)
        self.lbl_editing = QLabel()
        self.lbl_editing.setProperty("class", "dim-label")
        theme_row = QHBoxLayout()
        theme_row.addWidget(QLabel("Theme:"))
        theme_row.addWidget(self.f_theme)
        theme_row.addWidget(self.lbl_editing, 1)

        color_grid = QGridLayout()
        color_grid.setSpacing(10)
        for i, (key, label) in enumerate(self.COLOR_KEYS_COL_1):
            lbl = QLabel(label)
            btn = QPushButton()
            self._set_btn_color(btn, self._colors()[key])
            btn.clicked.connect(lambda checked=False, k=key: self._pick_color(k))
            self._color_btns[key] = btn
            color_grid.addWidget(lbl, i, 0)
            color_grid.addWidget(btn, i, 1)

        for i, (key, label) in enumerate(self.COLOR_KEYS_COL_2):
            lbl = QLabel(label)
            btn = QPushButton()
            self._set_btn_color(btn, self._colors()[key])
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
        btn_reset.setToolTip("The font, the splash screen, and the colours of the theme shown")
        btn_reset.setProperty("class", "secondary")
        btn_reset.clicked.connect(self._reset)
        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(self._save)
        btns.rejected.connect(self.reject)

        form = QFormLayout()
        form.setSpacing(10)
        form.addRow("Font Family:", self.f_font)
        form.addRow("Font Size:", self.f_size)
        self.f_splash = StepSpinBox(value=self.settings.get("splash_seconds"), min_val=0, max_val=10,
                                    step=0.5, decimals=1)
        self.f_splash.setToolTip("Seconds the splash screen stays at start-up; 0 = no splash screen")
        form.addRow("Splash Screen (s):", self.f_splash)

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
        layout.addLayout(theme_row)
        layout.addLayout(color_grid)
        layout.addWidget(self._sep())
        layout.addWidget(backups_lbl)
        layout.addLayout(extra_row)
        layout.addWidget(self._sep())
        layout.addLayout(btn_row)
        self._theme_changed()

    def _editing(self):
        """The theme whose colours the buttons show and change ("system": the one on screen now)."""
        return system_theme() if self._pending_theme == "system" else self._pending_theme

    def _colors(self):
        return self._pending_themes[self._editing()]

    def _theme_changed(self, *_):
        self._pending_theme = self.f_theme.currentData()
        for key, btn in self._color_btns.items():
            self._set_btn_color(btn, self._colors()[key])
        self.lbl_editing.setText(f"(editing the {THEME_NAMES[self._editing()]} colours: the Mac shows that one now)"
                                 if self._pending_theme == "system" else "")
        if self.isVisible():
            self.setFixedSize(self.sizeHint())

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
        current = QColor(self._colors()[key])
        color = QColorDialog.getColor(current, self, f"Choose color for {key}")

        if color.isValid():
            hex_color = color.name()
            self._colors()[key] = hex_color
            self._set_btn_color(self._color_btns[key], hex_color)

    def _save(self):
        self.settings.set("font_family", self.f_font.currentText())
        self.settings.set("font_size", int(self.f_size.value()))
        self.settings.set("splash_seconds", float(self.f_splash.value()))

        self.settings.set("theme", self._pending_theme)
        for theme, colors in self._pending_themes.items():
            self.settings.set_theme_colors(theme, colors)

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
        self.f_splash.setValue(self._default_value("splash_seconds"))

        self._pending_themes[self._editing()] = dict(THEMES[self._editing()])  # this theme's own colours
        for key, btn in self._color_btns.items():
            self._set_btn_color(btn, self._colors()[key])
