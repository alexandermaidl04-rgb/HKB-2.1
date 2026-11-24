"""Programm-Passwort (PBKDF2-HMAC-SHA256, nur Hash wird gespeichert)."""
import hashlib
import hmac
import os

ITER = 200_000


def _hash(pw, salt):
    return hashlib.pbkdf2_hmac("sha256", pw.encode("utf-8"), salt, ITER).hex()


def has_password(db):
    return bool(db.one("SELECT value FROM settings WHERE key='pw_hash'"))


def set_password(db, pw):
    if len(pw) < 4:
        raise ValueError("Das Passwort muss mindestens 4 Zeichen lang sein.")
    salt = os.urandom(16)
    db.set_setting("pw_salt", salt.hex())
    db.set_setting("pw_hash", _hash(pw, salt))


def check_password(db, pw):
    h = db.one("SELECT value FROM settings WHERE key='pw_hash'")
    s = db.one("SELECT value FROM settings WHERE key='pw_salt'")
    if not h or not s:
        return False
    return hmac.compare_digest(h["value"], _hash(pw, bytes.fromhex(s["value"])))
