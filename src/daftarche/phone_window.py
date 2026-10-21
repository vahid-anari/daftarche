"""Settings › Phone: the Google sign-in, the connected phones, and connecting one by QR code."""

from __future__ import annotations

import html
import threading
import webbrowser
from datetime import datetime

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtGui import QColor, QGuiApplication, QPainter, QPixmap
from PySide6.QtWidgets import (
    QDialog, QDialogButtonBox, QGridLayout, QHBoxLayout, QInputDialog, QLabel, QMessageBox, QPushButton,
    QApplication, QVBoxLayout, QWidget,
)

import shiboken6

from daftarche import phone_link as L

RELEASES = "https://github.com/vahid-anari/daftarche/releases"


def ago(stamp, now=None):
    """ "just now", "5 minutes ago", "yesterday at 14:05", "3 Oct at 09:12"."""
    if not stamp:
        return "never"
    try:
        when = datetime.fromisoformat(stamp)
    except ValueError:
        return stamp
    now = now or datetime.now()
    secs = (now - when).total_seconds()
    if secs < 60:
        return "just now"
    if secs < 3600:
        m = int(secs // 60)
        return f"{m} minute{'s' if m != 1 else ''} ago"
    if when.date() == now.date():
        return f"today at {when:%H:%M}"
    if (now.date() - when.date()).days == 1:
        return f"yesterday at {when:%H:%M}"
    return f"{when.day} {when:%b} at {when:%H:%M}"


def qr_pixmap(text, size=300):
    """The QR code of ``text``, black on white with a quiet border (cameras need both)."""
    import segno
    matrix = segno.make(text, error="m").matrix
    n = len(matrix) + 8  # four modules of white all round
    cell = max(size // n, 2)
    pix = QPixmap(cell * n, cell * n)
    pix.fill(QColor("white"))
    p = QPainter(pix)
    p.setPen(Qt.NoPen)
    p.setBrush(QColor("black"))
    for y, row in enumerate(matrix):
        for x, on in enumerate(row):
            if on:
                p.drawRect((x + 4) * cell, (y + 4) * cell, cell, cell)
    p.end()
    return pix


class _Relay(QObject):
    """Brings a background job's result back to the window's thread."""
    done = Signal(object, object)  # (result, error text)


def run_in_background(job, on_done, parent):
    relay = _Relay(parent)
    relay.done.connect(lambda result, error: (on_done(result, error), relay.deleteLater()))

    def work():
        try:
            result, error = job(), None
        except L.LinkError as exc:
            result, error = None, str(exc)
        except Exception as exc:  # shown, never swallowed
            result, error = None, f"{type(exc).__name__}: {exc}"
        relay.done.emit(result, error)

    threading.Thread(target=work, daemon=True).start()
    return relay


class PhoneSection(QWidget):
    """The Phone part of Settings. Its buttons act at once (they are not undone by Cancel)."""

    def __init__(self, sender, parent=None):
        super().__init__(parent)
        self.sender_ = sender
        self._signing_in = False
        self._cancel = threading.Event()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        account = QHBoxLayout()
        account.addWidget(QLabel("Google Drive:"))
        self.lbl_account = QLabel()
        self.lbl_account.setWordWrap(True)
        account.addWidget(self.lbl_account, 1)
        self.btn_account = QPushButton()
        self.btn_account.clicked.connect(self._sign_in_or_out)
        account.addWidget(self.btn_account)
        layout.addLayout(account)
        self.phones = QGridLayout()
        self.phones.setHorizontalSpacing(10)
        self.phones.setVerticalSpacing(4)
        layout.addLayout(self.phones)
        bottom = QHBoxLayout()
        self.btn_connect = QPushButton("Connect a Phone…")
        self.btn_connect.clicked.connect(self._connect)
        bottom.addWidget(self.btn_connect)
        self.lbl_status = QLabel()
        self.lbl_status.setProperty("class", "dim-label")
        self.lbl_status.setWordWrap(True)
        bottom.addWidget(self.lbl_status, 1)
        self.btn_send = QPushButton("Send Now")
        self.btn_send.setProperty("class", "secondary")
        self.btn_send.setToolTip("Send your data to the phones now (it goes by itself a minute after a change)")
        self.btn_send.clicked.connect(self.sender_.send_now)
        bottom.addWidget(self.btn_send)
        layout.addLayout(bottom)
        self.sender_.changed.connect(self.refresh)
        cancel = self._cancel
        self.destroyed.connect(lambda *_: cancel.set())  # Settings closed while signing in: stop waiting
        self.refresh()

    # ── showing ──────────────────────────────────────────────────────────────
    def refresh(self):
        store = self.sender_.store
        google = store.google
        cid, _ = L.client()
        if self._signing_in:
            self.lbl_account.setText("signing in, in your browser…")
            self.btn_account.setText("Cancel")
        elif google:
            self.lbl_account.setText(html.escape(google.get("email") or "connected"))
            self.btn_account.setText("Sign Out")
        else:
            self.lbl_account.setText("not connected" if cid else "not available in this copy of Daftarche")
            self.btn_account.setText("Sign In with Google…")
        self.btn_account.setEnabled(bool(cid) or bool(google))
        while self.phones.count():
            w = self.phones.takeAt(0).widget()
            if w:
                w.hide()
                w.deleteLater()
        for row, phone in enumerate(store.phones):
            name = QLabel(f"📱 <b>{html.escape(phone['name'])}</b>")
            state = QLabel(f"⚠️ {html.escape(phone['error'])}" if phone.get("error")
                           else f"sent {ago(phone.get('sent'))}")
            state.setProperty("class", "dim-label")
            state.setWordWrap(True)
            gone = QPushButton("Disconnect")
            gone.setProperty("class", "danger")
            gone.clicked.connect(lambda _=False, p=phone: self._disconnect(p))
            self.phones.addWidget(name, row, 0)
            self.phones.addWidget(state, row, 1)
            self.phones.addWidget(gone, row, 2)
        self.phones.setColumnStretch(1, 1)
        viewing = self.sender_.db() is None  # a database opened to look at: not yours to send
        self.btn_connect.setEnabled(bool(google) and not viewing)
        self.btn_connect.setToolTip("Go back to your own database first (File › Back to My Database)" if viewing
                                    else "")
        self.btn_send.setVisible(bool(google and store.phones))
        self.btn_send.setEnabled(not self.sender_.busy)
        if self.sender_.busy:
            status = "Sending…"
        elif self.sender_.last_error and not google:
            status = f"⚠️ {self.sender_.last_error}"
        elif not google:
            status = "Sign in to connect a phone: your data goes to it through your own Google Drive, locked."
        elif not store.phones:
            status = "No phone yet."
        elif self.sender_.pending():
            status = "Changes wait to be sent (a minute after the last one)."
        else:
            status = "Up to date."
        self.lbl_status.setText(status)
        win = self.window()
        if isinstance(win, QDialog) and win.isVisible() and hasattr(win, "fit"):
            win.fit()

    # ── Google ───────────────────────────────────────────────────────────────
    def _sign_in_or_out(self):
        if self._signing_in:
            self._cancel.set()
            return
        if self.sender_.store.google:
            phones = self.sender_.store.phones
            extra = (f"\n\nYour {len(phones)} phone{'s' if len(phones) != 1 else ''} will no longer get your "
                     "changes until you sign in again with the same account.") if phones else ""
            if QMessageBox.question(self, "Sign Out", "Sign Daftarche out of Google Drive?" + extra,
                                    QMessageBox.Yes | QMessageBox.No, QMessageBox.No) == QMessageBox.Yes:
                self.sender_.sign_out()
            return
        self._signing_in = True
        self._cancel.clear()
        self.refresh()
        sender, cancel = self.sender_, self._cancel

        def done(account, error):  # Settings may be closed by now: the sign-in is kept anyway
            if account:
                sender.signed_in(account)
            if shiboken6.isValid(self):
                self._signing_in = False
                self.refresh()
                if not account and not cancel.is_set():
                    QMessageBox.warning(self, "Google Drive", error)

        run_in_background(lambda: L.sign_in(webbrowser.open, cancelled=cancel.is_set), done, sender)

    # ── phones ───────────────────────────────────────────────────────────────
    def _connect(self):
        taken = {p["name"].casefold() for p in self.sender_.store.phones}
        name, ok = QInputDialog.getText(self, "Connect a Phone", "A name for the phone (e.g. Vahid's Pixel):",
                                        text="My phone" if "my phone" not in taken else "")
        name = " ".join((name or "").split())
        if not ok or not name:
            return
        if name.casefold() in taken:
            QMessageBox.warning(self, "Connect a Phone", f"There is already a phone named '{name}'.")
            return
        ConnectPhoneDialog(self.sender_, name, self).exec()

    def _disconnect(self, phone):
        if QMessageBox.question(
                self, "Disconnect",
                f"Disconnect '{phone['name']}'?\n\nIts copy on your Google Drive is deleted: the phone then says "
                "it was disconnected, and keeps nothing new. You can connect it again later.",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No) != QMessageBox.Yes:
            return
        self.sender_.forget_phone(phone["id"])  # gone from the list now; its file goes in the background
        def done(problem, error):
            problem = problem or error
            if problem:  # this window may be closed by now: over whichever is in front
                QMessageBox.warning(
                    QApplication.activeWindow(), "Disconnect",
                    f"'{phone['name']}' is disconnected here, but its file could not be deleted from your Google "
                    f"Drive ({problem}). Delete “Daftarche phone - {phone['name']}” there by hand: until then the "
                    "phone keeps showing the data it has.")

        run_in_background(lambda: self.sender_.delete_phone_file(phone), done, self.sender_)


class ConnectPhoneDialog(QDialog):
    """Makes the phone's file, then shows the QR code its camera reads."""

    def __init__(self, sender, name, parent=None):
        super().__init__(parent)
        self.sender_ = sender
        self.name = name
        self.link = None
        self.setWindowTitle("Connect a Phone")
        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setSizeConstraint(QVBoxLayout.SetFixedSize)  # grows with the QR code and the steps
        self.title = QLabel(f"Connecting <b>{html.escape(name)}</b>…")
        layout.addWidget(self.title)
        self.qr = QLabel()
        self.qr.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.qr)
        self.steps = QLabel()
        self.steps.setWordWrap(True)
        self.steps.setTextFormat(Qt.RichText)
        self.steps.setOpenExternalLinks(True)
        self.steps.setMinimumWidth(500)
        layout.addWidget(self.steps)
        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        self.btn_copy = buttons.addButton("Copy Link", QDialogButtonBox.ActionRole)
        self.btn_copy.setToolTip("For pasting into the phone app when the camera won't open the link")
        self.btn_copy.clicked.connect(lambda: QGuiApplication.clipboard().setText(self.link or ""))
        self.btn_copy.hide()
        buttons.rejected.connect(self.accept)
        layout.addWidget(buttons)
        self._closed = False
        self.finished.connect(lambda *_: setattr(self, "_closed", True))
        self.steps.setText("Putting a locked copy of your data on your Google Drive…")
        from daftarche.phone_sync import snapshot_bytes
        data = snapshot_bytes(sender.db(), sender.app_version)  # here: the database is used from this thread only
        # the sender, not this window, waits for the answer: it outlives the window
        run_in_background(lambda: sender.connect_phone(name, data), self._ready, sender)

    def _ready(self, result, error):
        if result is None:
            self.title.setText(f"<b>{html.escape(self.name)}</b> could not be connected.")
            self.steps.setText(html.escape(error or ""))
            return
        phone, link = result
        if self._closed:  # closed before its code was shown: that file is of no use
            run_in_background(lambda: self.sender_.discard_file(phone["file"]), lambda *_: None, self.sender_)
            return
        self.link = link
        self.sender_.add_phone(phone)
        self.title.setText(f"Connect <b>{html.escape(self.name)}</b>")
        self.qr.setPixmap(qr_pixmap(self.link))
        self.steps.setText(
            f"1. Install Daftarche on the phone, if it isn't yet (the newest <i>Phone</i> release at "
            f"<a href='{RELEASES}'>github.com/vahid-anari/daftarche/releases</a>).<br>"
            "2. Point the phone's camera at this code and tap the link: a page of Daftarche's opens, and then "
            "the app, connected (tap <b>Open Daftarche</b> on the page if it doesn't by itself).<br>"
            "3. No camera at hand? Press <b>Copy Link</b>, send it to the phone (a note, a message to yourself) "
            "and tap it there, or paste it on Daftarche's first screen.<br><br>"
            "<span style='color:gray'>The code holds this phone's key: keep it to yourself. Anyone with it "
            "could read your data, until you Disconnect the phone.</span>")
        self.btn_copy.show()
