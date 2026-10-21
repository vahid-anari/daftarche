"""Keeping the phones up to date (Qt side of phone_link.py).

* :class:`PhoneStore` — the Google sign-in and the connected phones, in ``phone-link.json`` next
  to the database (only you can read it: it holds the phones' keys).
* :class:`PhoneSender` — sends the sealed snapshot to every phone's file: about a minute after
  the last change (so forty edits make one upload), right after an import, and when Daftarche
  closes; it tries again by itself when offline. Never for a database opened to look at.
"""

from __future__ import annotations

import json
import os
import sqlite3
import threading
import time
import uuid
from datetime import datetime

from PySide6.QtCore import QObject, QTimer, Signal

from daftarche import phone_link as L
from daftarche.paths import DATA_DIR
from daftarche.phone import build_snapshot
from daftarche.seal import key_from_text, key_to_text, new_key, seal

STORE_PATH = DATA_DIR / "phone-link.json"
QUIET_S = 60  # send this long after the last change
CHECK_MS = 5000
RETRY_S = (60, 120, 300, 600, 1800)  # after failures in a row (the last one repeats)
CLOSE_WAIT_S = 20  # at most this long when Daftarche closes


def file_name(phone_name):
    return f"Daftarche phone - {phone_name}"


def snapshot_bytes(db, app_version=""):
    return json.dumps(build_snapshot(db, app_version), ensure_ascii=False, separators=(",", ":")).encode()


class PhoneStore:
    """{"google": {"refresh_token", "email"} | None, "phones": [{id, name, file, key, sent, error}]}."""

    def __init__(self, path=STORE_PATH):
        self.path = path
        self.data = {"google": None, "phones": []}
        try:
            with open(path, encoding="utf-8") as f:
                self.data.update(json.load(f))
        except FileNotFoundError:
            pass
        except (OSError, ValueError):
            os.replace(path, f"{path}.broken")  # kept for a look, never silently overwritten

    def save(self):
        tmp = f"{self.path}.tmp"
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(self.data, f, indent=2)
        os.chmod(tmp, 0o600)
        os.replace(tmp, self.path)

    @property
    def google(self):
        return self.data.get("google")

    @property
    def phones(self):
        return self.data.setdefault("phones", [])

    def phone(self, phone_id):
        return next((p for p in self.phones if p["id"] == phone_id), None)


class PhoneSender(QObject):
    """``db()`` gives the database to send (None: none now, e.g. one opened to look at)."""

    changed = Signal()  # the phones, the sign-in or the last send changed: redraw what shows them
    _done = Signal(int, object)

    def __init__(self, db, app_version="", store=None, parent=None, drive_factory=None):
        super().__init__(parent)
        self.db = db
        self.app_version = app_version
        self.store = store or PhoneStore()
        self.drive_factory = drive_factory or (lambda token: L.Drive(token))
        self.busy = False
        self.last_error = ""
        self._seen = self._state()
        # unsent changes survive a quit: "dirty" is kept in the store until a send succeeds
        self._pending = bool(self.store.data.get("dirty")) or any(
            p.get("error") or not p.get("sent") for p in self.store.phones)
        self._changed_at = 0.0
        self._fails = 0
        self._next_try = 0.0
        self._thread = None
        self._send_no = 0  # each send's number: a late answer from an earlier one is ignored
        self._results = {}
        self._done.connect(self._finished)
        self.timer = QTimer(self)
        self.timer.setInterval(CHECK_MS)
        self.timer.timeout.connect(self.tick)
        self.timer.start()

    # ── what there is to send ────────────────────────────────────────────────
    def _state(self):
        db = self.db()
        if db is None:
            return None
        try:
            return db.conn.total_changes
        except sqlite3.Error:  # closed (Daftarche is quitting, or switching databases)
            return None

    def active(self):
        return bool(self.store.google and self.store.phones and self._state() is not None)

    def pending(self):
        return self._pending

    def _mark(self, now):
        self._pending, self._changed_at = True, now
        if not self.store.data.get("dirty"):
            self.store.data["dirty"] = True
            self.store.save()

    def _note(self, now):
        state = self._state()
        if state != self._seen:
            if state is not None and self._seen is not None:
                self._mark(now)
            self._seen = state

    def database_switched(self, changed):
        """The window opened another database, went back to yours (``changed`` False), or
        restored a backup over yours (``changed`` True: that is new data for the phones)."""
        self._seen = self._state()
        if changed:
            self.send_now()

    def tick(self, now=None):
        """Every few seconds: note a change; send once things have been quiet for a minute."""
        now = time.monotonic() if now is None else now
        self._note(now)
        if (self._pending and not self.busy and self.active() and now - self._changed_at >= QUIET_S
                and now >= self._next_try):
            self.send()

    def send_now(self):
        """After an import or a restore, a new phone, or the person's Send Now: no waiting."""
        self._mark(time.monotonic() - QUIET_S)
        self._next_try = 0.0
        if self.active() and not self.busy:
            self.send()

    # ── sending ──────────────────────────────────────────────────────────────
    def send(self, wait=False):
        """Seal the snapshot for every phone and upload it (in the background; ``wait``: block,
        at most CLOSE_WAIT_S, when closing)."""
        if self.busy or not self.active():
            return
        data = snapshot_bytes(self.db(), self.app_version)
        jobs = [(p["id"], p["file"], seal(data, key_from_text(p["key"]))) for p in self.store.phones]
        token = self.store.google["refresh_token"]
        self.busy, self._pending = True, False
        self._seen = self._state()
        self._send_no += 1
        number = self._send_no
        self._results[number] = None
        self.changed.emit()

        def work():
            results = {}
            try:
                drive = self.drive_factory(token)
                for phone_id, file_id, blob in jobs:
                    try:
                        drive.update(file_id, blob)
                        results[phone_id] = None
                    except L.SignedOut:
                        raise
                    except L.FileGone:
                        results[phone_id] = "gone"
                    except L.LinkError as exc:
                        results[phone_id] = str(exc)
            except L.SignedOut as exc:
                results = {"signed_out": str(exc)}
            except Exception as exc:  # never let a surprise kill the thread silently
                results = {pid: f"{type(exc).__name__}: {exc}" for pid, _, _ in jobs}
            self._results[number] = results
            self._done.emit(number, results)

        self._thread = threading.Thread(target=work, daemon=True)
        self._thread.start()
        if wait:
            self._wait_for(number, jobs)

    def _wait_for(self, number, jobs):
        """Block until send ``number`` is done (at most CLOSE_WAIT_S) and record it."""
        self._thread.join(CLOSE_WAIT_S)
        results = self._results.get(number) or {pid: "Daftarche closed before it finished: sent next time."
                                                for pid, _, _ in jobs}
        self._finished(number, results)

    def _finished(self, number, results):
        if number != self._send_no or not self.busy:
            return  # already recorded (a send waited for at quit), or an earlier one
        self.busy = False
        stamp = datetime.now().isoformat(timespec="seconds")
        if "signed_out" in results:
            self.last_error = results["signed_out"]
            self.store.data["google"] = None
            failed = True
        else:
            failed = False
            for phone in self.store.phones:  # a phone disconnected meanwhile is simply not there
                if phone["id"] not in results:
                    continue
                error = results[phone["id"]]
                if error == "gone":
                    error = "Its file is no longer on your Google Drive: disconnect it and connect it again."
                if error:
                    phone["error"] = error
                    failed = True
                else:
                    phone["sent"], phone["error"] = stamp, None
            self.last_error = next((p["error"] for p in self.store.phones if p.get("error")), "")
        if failed:
            self._pending = True
            self._next_try = time.monotonic() + RETRY_S[min(self._fails, len(RETRY_S) - 1)]
            self._fails += 1
        else:
            self._fails = 0
            if not self._pending:  # nothing changed while it was sending
                self.store.data["dirty"] = False
        self.store.save()
        self.changed.emit()

    def finish(self):
        """Daftarche is closing: wait for a send on its way, then send what is left (a little
        while at most; what is still unsent goes next time)."""
        self.timer.stop()
        self._note(time.monotonic())  # a last change, if any
        if self.busy and self._thread is not None:
            self._wait_for(self._send_no, [(p["id"], None, None) for p in self.store.phones])
        if self._pending and self.active() and not self.busy:
            self.send(wait=True)

    # ── the Google sign-in and the phones (blocking: call off the main thread) ──
    def connect_phone(self, name, data=None):
        """A new phone: its file with the snapshot in it, shared by link; returns (phone, pairing
        link). ``data``: the snapshot, made beforehand on the window's thread (the database is
        used from there only) when this runs in the background."""
        key = new_key()
        blob = seal(data if data is not None else snapshot_bytes(self.db(), self.app_version), key)
        file_id = self.drive_factory(self.store.google["refresh_token"]).create(file_name(name), blob)
        phone = {"id": uuid.uuid4().hex, "name": name, "file": file_id, "key": key_to_text(key),
                 "sent": datetime.now().isoformat(timespec="seconds"), "error": None,
                 "added": datetime.now().isoformat(timespec="seconds")}
        return phone, L.pairing_link(file_id, phone["key"], name)

    def add_phone(self, phone):
        self.store.phones.append(phone)
        self.store.save()
        self.changed.emit()
        if self.busy:  # a send on its way has not got this phone: send again after it
            self._mark(time.monotonic() - QUIET_S)

    def discard_file(self, file_id):
        """A file made for a phone that was never shown its code (the window closed first)."""
        try:
            self.drive_factory(self.store.google["refresh_token"]).delete(file_id)
        except (L.LinkError, TypeError):
            pass

    def delete_phone_file(self, phone):
        """Delete a phone's file from the Drive (blocking). Returns a problem, or None."""
        if not self.store.google:
            return "Daftarche is signed out of Google Drive"
        try:
            self.drive_factory(self.store.google["refresh_token"]).delete(phone["file"])
        except L.LinkError as exc:
            return str(exc)
        return None

    def forget_phone(self, phone_id):
        self.store.data["phones"] = [p for p in self.store.phones if p["id"] != phone_id]
        self.store.save()
        self.changed.emit()

    def disconnect_phone(self, phone_id):
        """Delete its file (the phone then says it was disconnected) and forget it (blocking).
        A file that cannot be deleted now is still forgotten here: Disconnect is what you asked;
        the problem is returned to be shown."""
        phone = self.store.phone(phone_id)
        if phone is None:
            return None
        problem = self.delete_phone_file(phone)
        self.forget_phone(phone_id)
        return problem

    def signed_in(self, account):
        self.store.data["google"] = account
        self.last_error = ""
        self.store.save()
        self.changed.emit()

    def sign_out(self):
        account = self.store.google
        self.store.data["google"] = None
        self.store.save()
        self.changed.emit()
        if account:
            threading.Thread(target=L.sign_out, args=(account["refresh_token"],), daemon=True).start()
