"""Sealing the phone's copy of your data: encrypted and tamper-evident, with Python alone.

The Mac seals the snapshot with a phone's own key before it goes to Google Drive; the phone,
which got the key from the QR code (never through Google), opens it. Google only ever holds
scrambled bytes.

How: the snapshot is compressed (zlib), then XORed with a keystream of HMAC-SHA256 blocks
(HMAC as a pseudorandom function in counter mode, with a fresh random nonce each time), and
the result is authenticated with a second HMAC-SHA256 over everything before it
(encrypt-then-MAC). Both keys come from the phone's 32-byte key by HMAC with different
labels. Only the standard library is used, so the very same file runs on the phone.

THIS FILE IS SHARED: mobile/src/daftarche_phone/seal.py is an identical copy (a test checks).
"""

from __future__ import annotations

import base64
import hmac
import os
import zlib

MAGIC = b"DAFTARCHE-SEALED-1\n"
NONCE_SIZE = 16
TAG_SIZE = 32
KEY_SIZE = 32
MAX_OPENED = 64 * 1024 * 1024  # a snapshot is far smaller: more is not ours


class SealError(ValueError):
    """Not a sealed snapshot, the wrong key, or changed on the way."""


def new_key() -> bytes:
    return os.urandom(KEY_SIZE)


def key_to_text(key: bytes) -> str:
    return base64.urlsafe_b64encode(key).rstrip(b"=").decode("ascii")


def key_from_text(text: str) -> bytes:
    text = (text or "").strip()
    try:
        key = base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))
    except (ValueError, TypeError) as exc:
        raise SealError("That key is not readable.") from exc
    if len(key) != KEY_SIZE:
        raise SealError("That key is not readable.")
    return key


def _keys(key: bytes):
    if len(key) != KEY_SIZE:
        raise SealError("A key is 32 bytes.")
    return (hmac.digest(key, b"daftarche: encryption", "sha256"),
            hmac.digest(key, b"daftarche: authentication", "sha256"))


def _xor_stream(enc_key: bytes, nonce: bytes, data: bytes) -> bytes:
    blocks = (len(data) + 31) // 32
    stream = b"".join(hmac.digest(enc_key, nonce + i.to_bytes(8, "big"), "sha256") for i in range(blocks))
    return (int.from_bytes(data, "big") ^ int.from_bytes(stream[:len(data)], "big")).to_bytes(len(data), "big")


def seal(data: bytes, key: bytes) -> bytes:
    """``data`` compressed, encrypted and signed with ``key``."""
    enc_key, mac_key = _keys(key)
    nonce = os.urandom(NONCE_SIZE)
    body = _xor_stream(enc_key, nonce, zlib.compress(data, 9))
    tag = hmac.digest(mac_key, MAGIC + nonce + body, "sha256")
    return MAGIC + nonce + body + tag


def is_sealed(blob: bytes) -> bool:
    return blob[:len(MAGIC)] == MAGIC


def open_sealed(blob: bytes, key: bytes) -> bytes:
    """The data inside; SealError when it is not ours or was changed."""
    if not is_sealed(blob) or len(blob) < len(MAGIC) + NONCE_SIZE + TAG_SIZE:
        raise SealError("This is not Daftarche's file.")
    enc_key, mac_key = _keys(key)
    nonce = blob[len(MAGIC):len(MAGIC) + NONCE_SIZE]
    body, tag = blob[len(MAGIC) + NONCE_SIZE:-TAG_SIZE], blob[-TAG_SIZE:]
    if not hmac.compare_digest(tag, hmac.digest(mac_key, MAGIC + nonce + body, "sha256")):
        raise SealError("The file does not match this phone's key (or was changed on the way).")
    unzip = zlib.decompressobj()
    data = unzip.decompress(_xor_stream(enc_key, nonce, body), MAX_OPENED)
    if unzip.unconsumed_tail:
        raise SealError("The file is too large.")
    return data
