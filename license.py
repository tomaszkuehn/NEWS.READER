"""Weryfikacja klucza odblokowujacego dalsze pobieranie artykułów.

Gdy baza przekroczy limit, aplikacja żąda klucza powiązanego z kodem systemu.
Klucz jest generowany osobnym narzędziem (keygen.py) na podstawie kodu systemu.

Implementacja celowo zaciemniona: stałe sekretu nie występują jako literały,
funkcje mają mylące nazwy, a porównanie odbywa się przez HMAC z重建ionym kluczem.
"""

import base64
import hashlib
import hmac
import os
import sys
import uuid

LIMIT = 4000


def _machine_guid():
    """Stabilny identyfikator maszyny (Windows MachineGuid, fallback MAC)."""
    try:
        if sys.platform == "win32":
            import winreg
            try:
                with winreg.OpenKey(
                    winreg.HKEY_LOCAL_MACHINE,
                    r"SOFTWARE\Microsoft\Cryptography",
                    0,
                    winreg.KEY_READ | winreg.KEY_WOW64_64KEY,
                ) as k:
                    v, _ = winreg.QueryValueEx(k, "MachineGuid")
                    if v and isinstance(v, str):
                        return v
            except OSError:
                pass
    except Exception:
        pass
    return str(uuid.getnode())


def _normalize(s):
    h = hashlib.sha256(s.encode("utf-8")).digest()
    return base64.b32encode(h[:10]).decode("ascii").rstrip("=").upper()


def system_code():
    """Kod systemu pokazywany użytkownikowi w prompcie (20 znaków base32)."""
    return _normalize(_machine_guid())


def _material():
    """Rekonstruuje materiał weryfikacyjny z rozproszonych operacji bitowych.

    Zmienne nazwane myląco; wartości nie występują jako ciągłe literały.
    """
    a = [0x5F, 0x3A, 0x71, 0xC4, 0x2D, 0x9E, 0x08, 0x17]
    b = [0xD6, 0x41, 0xB3, 0x55, 0xA2, 0xEF, 0x7C, 0x19]
    out = bytearray(len(a))
    for i in range(len(a)):
        out[i] = (a[i] ^ b[i]) & 0xFF
        out[i] = (out[i] + (i * 7 + 3)) & 0xFF
        out[i] = (out[i] ^ ((b[i] >> (i & 3)) & 0xFF)) & 0xFF
    return bytes(out)


def _expect(code):
    m = _material()
    d = hashlib.sha256(m + code.encode("utf-8")).digest()
    inner = hashlib.sha256(m + d).digest()
    tag = hmac.new(inner, code.encode("utf-8"), hashlib.sha256).digest()
    return base64.b32encode(tag[:10]).decode("ascii").rstrip("=").upper()


def verify(code, key):
    """Zwraca True jeśli klucz pasuje do kodu systemu."""
    if not code or not key:
        return False
    k = key.strip().upper().replace(" ", "").replace("-", "")
    if len(k) < 8:
        return False
    try:
        return hmac.compare_digest(_expect(code), k)
    except Exception:
        return False


def _unlock_file():
    d = os.path.dirname(os.path.abspath(__file__))
    if getattr(sys, "frozen", False):
        base = os.path.join(os.environ.get("APPDATA") or os.path.expanduser("~"), "NewsReader")
        os.makedirs(base, exist_ok=True)
        d = base
    return os.path.join(d, ".unlock")


def is_unlocked():
    """Czy aplikacja została odblokowana (klucz zapisany i poprawny)."""
    p = _unlock_file()
    if not os.path.isfile(p):
        return False
    try:
        with open(p, "r", encoding="utf-8") as f:
            saved = f.read().strip()
        if not saved:
            return False
        return verify(system_code(), saved)
    except OSError:
        return False


def store_key(key):
    """Zapisuje klucz (bez weryfikacji — weryfikacja przy is_unlocked)."""
    p = _unlock_file()
    with open(p, "w", encoding="utf-8") as f:
        f.write(key.strip())


def clear_key():
    try:
        os.remove(_unlock_file())
    except OSError:
        pass