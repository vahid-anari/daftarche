"""Merchants' logos: taken once from the shop's own website (its app icon, else its favicon) or
from a picture file, made a PNG of at most 128 px and kept in the database (merchant_logos).
Drawn on a white square with round corners, so a dark logo shows on the dark theme too."""

import html
import json
import re
import ssl
import urllib.parse
import urllib.request

from PySide6.QtCore import QBuffer, QByteArray, QIODevice, QRectF, QSize, Qt
from PySide6.QtGui import QColor, QIcon, QImage, QPainter, QPixmap
from PySide6.QtWidgets import (
    QApplication, QDialog, QFileDialog, QHBoxLayout, QLabel, QLineEdit, QMessageBox, QPushButton, QVBoxLayout,
)

SIZE = 128
"""The largest side of a logo kept (it is drawn at most a little larger than a line of text)."""
TIMEOUT = 8
AGENT = "Daftarche (logo for a merchant)"
_ICON_PATHS = ("/apple-touch-icon.png", "/apple-touch-icon-precomposed.png")


class LogoError(Exception):
    """No logo could be had (no connection, no picture there, not a picture)."""


def site_url(text):
    """ "apple.com", "www.apple.com/ca" or "https://apple.com" → "https://apple.com" (the site's root)."""
    text = (text or "").strip()
    if not text:
        raise LogoError("Write the shop's website, e.g. example.com.")
    if "://" not in text:
        text = "https://" + text
    parts = urllib.parse.urlsplit(text)
    if not parts.netloc or "." not in parts.netloc:
        raise LogoError(f"“{text}” is not a website.")
    return f"{parts.scheme or 'https'}://{parts.netloc}"


def _context():
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:  # certifi comes with sciwidgets; without it, the system's certificates
        return ssl.create_default_context()


def _get(url, limit=2_000_000):
    request = urllib.request.Request(url, headers={"User-Agent": AGENT})
    with urllib.request.urlopen(request, timeout=TIMEOUT, context=_context()) as reply:
        return reply.read(limit), reply.geturl()


def _icon_links(page, base):
    """The icons a page names (<link rel="… icon" href=…>), the largest first."""
    found = []
    for tag in re.findall(r"<link\b[^>]*>", page, re.IGNORECASE):
        rel = re.search(r"""\brel\s*=\s*["']?([^"'>]+)""", tag, re.IGNORECASE)
        href = re.search(r"""\bhref\s*=\s*["']?([^"' >]+)""", tag, re.IGNORECASE)
        if not rel or not href or "icon" not in rel.group(1).lower():
            continue
        sizes = re.search(r"""\bsizes\s*=\s*["']?(\d+)""", tag, re.IGNORECASE)
        size = int(sizes.group(1)) if sizes else (180 if "apple" in rel.group(1).lower() else 32)
        found.append((size, urllib.parse.urljoin(base + "/", html.unescape(href.group(1)))))
    return [url for _size, url in sorted(found, reverse=True)]


def _manifest_icons(manifest, base):
    """The icons a web app manifest (JSON) names, the largest first."""
    try:
        icons = json.loads(manifest).get("icons") or []
    except (ValueError, AttributeError):
        return []
    found = []
    for icon in icons:
        if not isinstance(icon, dict) or not icon.get("src"):
            continue
        sizes = re.findall(r"(\d+)x\d+", str(icon.get("sizes") or ""))
        found.append((max(map(int, sizes)) if sizes else 0, urllib.parse.urljoin(base, icon["src"])))
    return [url for _size, url in sorted(found, reverse=True)]


def _manifest_links(page, base):
    links = []
    for tag in re.findall(r"<link\b[^>]*>", page, re.IGNORECASE):
        rel = re.search(r"""\brel\s*=\s*["']?([^"'>]+)""", tag, re.IGNORECASE)
        href = re.search(r"""\bhref\s*=\s*["']?([^"' >]+)""", tag, re.IGNORECASE)
        if rel and href and "manifest" in rel.group(1).lower():
            links.append(urllib.parse.urljoin(base + "/", html.unescape(href.group(1))))
    return links


GOOD = 96  # a logo at least this wide is sharp enough; a smaller one: look further


def fetch(site, get=_get):
    """The logo of a website: (PNG bytes, the address it came from). Tries the app icon a site
    has for phones (large), then the icons its home page and its web app manifest name, then
    /favicon.ico, and the same with "www." when nothing sharp was found; keeps the largest
    picture. ``get(url) → (bytes, final url)``: replaced in tests."""
    root = site_url(site)
    best = _search(root, get)
    host = urllib.parse.urlsplit(root).netloc
    if (best is None or best[0].width() < GOOD) and not host.startswith("www."):
        other = _search(root.replace("://", "://www.", 1), get)
        if other is not None and (best is None or other[0].width() > best[0].width()):
            best = other
    if best is None:
        raise LogoError(f"No logo found at {root}: no connection, or the site has no icon. "
                        "Choose a picture file instead.")
    return to_png(best[0]), best[1]


def _search(root, get):
    """(the largest picture found on the site at ``root``, its address), or None."""
    tried, best = [], None

    def consider(url):
        nonlocal best
        if url in tried:
            return
        tried.append(url)
        try:
            data, _final = get(url)
        except (OSError, ValueError):
            return
        image = QImage.fromData(data)
        if not image.isNull() and (best is None or image.width() * image.height() > best[0].width() * best[0].height()):
            best = (image, url)

    for path in _ICON_PATHS:
        consider(root + path)
    if best is None or best[0].width() < GOOD:
        manifests = [root + "/manifest.json", root + "/site.webmanifest"]
        try:
            page, final = get(root)
            text = page.decode("utf-8", "replace")
            for url in _icon_links(text, final.rstrip("/")):
                consider(url)
            manifests = _manifest_links(text, final.rstrip("/")) + manifests
        except (OSError, ValueError):
            pass
        for manifest in dict.fromkeys(manifests):
            if best is not None and best[0].width() >= GOOD:
                break
            try:
                data, final = get(manifest)
            except (OSError, ValueError):
                continue
            for url in _manifest_icons(data.decode("utf-8", "replace"), final)[:3]:
                consider(url)
    if best is None:
        consider(root + "/favicon.ico")
    return best


def normalise(data):
    """Picture bytes (PNG, JPEG, ICO…) → PNG bytes of at most SIZE px. Raises LogoError."""
    image = QImage.fromData(data)
    if image.isNull():
        raise LogoError("That is not a picture Daftarche can read.")
    return to_png(image)


def to_png(image):
    if max(image.width(), image.height()) > SIZE:
        image = image.scaled(SIZE, SIZE, Qt.KeepAspectRatio, Qt.SmoothTransformation)
    out = QByteArray()
    buffer = QBuffer(out)
    buffer.open(QIODevice.WriteOnly)
    image.save(buffer, "PNG")
    return bytes(out)


# ── drawing ──────────────────────────────────────────────────────────────────
_drawn = {}


def plate(data, size=64):
    """A logo on a white square with round corners, ``size`` px (cached)."""
    key = (hash(data), size)
    if key not in _drawn:
        pix = QPixmap(size, size)
        pix.fill(Qt.transparent)
        p = QPainter(pix)
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        p.setBrush(QColor("#ffffff"))
        p.setPen(Qt.NoPen)
        p.drawRoundedRect(QRectF(0, 0, size, size), size * 0.2, size * 0.2)
        logo = QImage.fromData(data)
        if not logo.isNull():
            inner = size * 0.8
            scaled = logo.scaled(int(inner), int(inner), Qt.KeepAspectRatio, Qt.SmoothTransformation)
            p.drawImage(int((size - scaled.width()) / 2), int((size - scaled.height()) / 2), scaled)
        p.end()
        _drawn[key] = pix
    return _drawn[key]


def logo_icon(data):
    return QIcon(plate(data, 64)) if data else QIcon()


# ── the window ───────────────────────────────────────────────────────────────
class LogoDialog(QDialog):
    """A merchant's logo: from its website or a file, with a preview; No Logo takes it away.
    ``edit_name``: Edit Merchant, its name above the logo, both kept with OK. After OK: ``name``,
    ``image`` (PNG bytes, None for no logo), ``source``, and ``logo_changed``."""

    def __init__(self, merchant, image=None, source="", parent=None, fetch_logo=fetch, edit_name=False):
        super().__init__(parent)
        self.setWindowTitle("Edit Merchant" if edit_name else "Logo")
        self.merchant = self.name = merchant
        self.image, self.source = image, source or ""
        self.logo_changed = False
        self._fetch = fetch_logo
        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        self.name_field = None
        if edit_name:
            row = QHBoxLayout()
            row.addWidget(QLabel("Name:"))
            self.name_field = QLineEdit(merchant)
            self.name_field.setToolTip("A name another merchant has already: the two are merged (it asks first)")
            row.addWidget(self.name_field, 1)
            layout.addLayout(row)
            head = QLabel("Logo")
            head.setProperty("class", "dim-label")
        else:
            head = QLabel(f"Logo for <b>{html.escape(merchant)}</b>")
        layout.addWidget(head)
        row = QHBoxLayout()
        row.addWidget(QLabel("Website:"))
        self.site = QLineEdit(self._site_of(source))  # the site it came from (a file's name: none)
        self.site.setPlaceholderText("the shop's website, e.g. example.com")
        self.site.returnPressed.connect(self._get)
        row.addWidget(self.site, 1)
        self.btn_get = QPushButton("Get Logo")
        self.btn_get.setProperty("class", "secondary")
        self.btn_get.clicked.connect(self._get)
        row.addWidget(self.btn_get)
        layout.addLayout(row)
        note = QLabel("Taken once from the shop's own site (its app icon), and kept in your data: no other "
                      "service, and nothing is fetched again.")
        note.setProperty("class", "dim-label")
        note.setWordWrap(True)
        layout.addWidget(note)
        preview = QHBoxLayout()
        preview.setSpacing(16)
        self.previews = []
        for size in (96, 40, 22):
            label = QLabel()
            label.setFixedSize(size, size)
            label.setAlignment(Qt.AlignCenter)
            self.previews.append((label, size))
            preview.addWidget(label, 0, Qt.AlignBottom)
        self.none_label = QLabel("No logo yet.")
        self.none_label.setProperty("class", "dim-label")
        preview.addWidget(self.none_label, 1)
        layout.addLayout(preview)
        buttons = QHBoxLayout()
        pick = QPushButton("Choose an Image File…")
        pick.setProperty("class", "secondary")
        pick.clicked.connect(self._choose_file)
        buttons.addWidget(pick)
        buttons.addStretch()
        self.btn_none = QPushButton("No Logo")
        self.btn_none.clicked.connect(self._no_logo)
        buttons.addWidget(self.btn_none)
        ok = QPushButton("OK")
        ok.setDefault(False)
        ok.clicked.connect(self._accept)
        cancel = QPushButton("Cancel")
        cancel.clicked.connect(self.reject)
        buttons.addWidget(ok)
        buttons.addWidget(cancel)
        layout.addLayout(buttons)
        self._show()

    def _accept(self):
        if self.name_field is not None:
            name = " ".join(self.name_field.text().split())
            if not name:
                QMessageBox.warning(self, "Edit Merchant", "Write the merchant's name.")
                return
            self.name = name
        self.accept()

    @staticmethod
    def _site_of(source):
        if not source or "://" not in source:
            return ""
        return urllib.parse.urlsplit(source).netloc

    def _show(self):
        for label, size in self.previews:
            label.setPixmap(plate(self.image, size) if self.image else QPixmap())
            label.setVisible(bool(self.image))
        self.none_label.setVisible(not self.image)
        self.btn_none.setEnabled(bool(self.image))

    def _get(self):
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            image, url = self._fetch(self.site.text())
        except LogoError as exc:
            QApplication.restoreOverrideCursor()
            QMessageBox.warning(self, "Logo", str(exc))
            return
        QApplication.restoreOverrideCursor()
        self.image, self.source = image, url
        self.logo_changed = True
        self._show()

    def _choose_file(self):
        path, _ = QFileDialog.getOpenFileName(self, "A Picture for the Logo", "",
                                              "Pictures (*.png *.jpg *.jpeg *.gif *.bmp *.ico *.webp *.svg)")
        if path:
            self.use_file(path)

    def use_file(self, path):
        try:
            with open(path, "rb") as f:
                self.image = normalise(f.read())
        except (OSError, LogoError) as exc:
            QMessageBox.warning(self, "Logo", str(exc))
            return
        from pathlib import Path
        self.source = Path(path).name
        self.logo_changed = True
        self._show()

    def _no_logo(self):
        self.image, self.source = None, ""
        self.logo_changed = True
        self._show()


def icon_size(widget):
    """The size of an icon or a logo beside a name: a little taller than the widget's line of
    text, so it follows the font size (Settings)."""
    side = round(widget.fontMetrics().height() * 1.2)
    return QSize(side, side)
