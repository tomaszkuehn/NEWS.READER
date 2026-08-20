"""Weryfikacja klucza odblokowujacego dalsze pobieranie artykułów.

Model: okres próbny (30 dni) + offline RSA (PKCS#1 v1.5).
- Przy pierwszym uruchomieniu zapisywany jest timestamp w .trial.
- Przez 30 dni aplikacja działa bez ograniczeń.
- Po upływie 30 dni odświeżanie jest blokowane (przeglądanie nadal działa).
- Odblokowanie: keygen (u autora) podpisuje kod systemu RSA → klucz.
- Aplikacja weryfikuje podpis wbudowanym kluczem publicznym.
- Atakujący po dekompilacji ma klucz publiczny, ale nie prywatnego —
  nie wygeneruje klucza bez podmiany klucza publicznego w exe.

Anti-tamper: rozproszone bajty klucza publicznego zaszyte w license.py.
Sprawdzane przy starcie — wykrywa podmianę klucza publicznego.

Rozproszone punkty weryfikacji: app.py, refresher.py, tray.py — każdy
wywołuje license.is_active() niezależnie, więc atakujący musi znaleźć
i załatać wszystkie punkty blokady, a nie jeden if.
"""

import base64
import hashlib
import os
import struct
import sys
import time
import uuid

from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.exceptions import InvalidSignature

TRIAL_DAYS = 30

# Klucz publiczny RSA (2048-bit, PEM bez nagłówków, base64).
# Klucz prywatny NIE jest wbudowany w aplikację — tylko w keygen.py u autora.
_PUBKEY_B64 = (
    "MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEAuqdclTRb0rNhwbRws8HTGi4ADfHxmhBFVTaqrC9scn/lE5tXyNCASrvjigp84PDDwHbnA40hf2zDWTeCP+MVV3t61vf23eUv/LxA1elRyKtYdlk0kW1CYrO3ppvZNMd+bbPYUeUolqXnUbBe13XPG512S7u5jtwUrgLUliDfqHA22whnfIR8JoxwD5fT+hTyv/+za67fAyVhefUTL+VMmMyIAJE7+FBG74SvS7efv9ABUJfXT/pYMr1QhA+g2Xe5+fNLzsbMDNSqdBIMG9z8ebsxqxJuOGm2RfZ8ys2MDcM92GJs7VMpkt4fSe2CFoUvqeRgo42EQcwqPX2nJRAqHQIDAQAB"
)


def _load_pubkey():
    der = base64.b64decode(_PUBKEY_B64)
    return serialization.load_der_public_key(der)


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
    """Kod systemu pokazywany użytkownikowi (20 znaków base32)."""
    return _normalize(_machine_guid())


def _payload(code):
    """Dane podpisywane — kod systemu + ograniczenie (zapobiega reuse)."""
    return f"NEWSREADER|{code}".encode("utf-8")


def verify(code, key_b64):
    """Zwraca True jeśli klucz (base64 podpis RSA) pasuje do kodu systemu."""
    if not code or not key_b64:
        return False
    k = key_b64.strip().replace(" ", "").replace("-", "").replace("\n", "")
    if len(k) < 16:
        return False
    try:
        sig = base64.b64decode(k)
    except Exception:
        return False
    try:
        pub = _load_pubkey()
        pub.verify(sig, _payload(code), padding.PKCS1v15(), hashes.SHA256())
        return True
    except (InvalidSignature, Exception):
        return False


def _data_dir():
    if getattr(sys, "frozen", False):
        base = os.path.join(os.environ.get("APPDATA") or os.path.expanduser("~"), "NewsReader")
        os.makedirs(base, exist_ok=True)
        return base
    return os.path.dirname(os.path.abspath(__file__))


def _unlock_file():
    return os.path.join(_data_dir(), ".unlock")


def _trial_file():
    return os.path.join(_data_dir(), ".trial")


def _trial_shadow_dir():
    """Trzecia kopia trial — ukryty plik w nietypowej lokalizacji."""
    base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    d = os.path.join(base, "Microsoft", "CLR_v4.0", "UsageLogs")
    try:
        os.makedirs(d, exist_ok=True)
    except OSError:
        pass
    return d


def _trial_shadow_file():
    return os.path.join(_trial_shadow_dir(), "nr.cfg")


def _trial_shadow():
    """Druga kopia trial — w rejestrze Windows (HKCU). Zapobiega resetowi przez usunięcie pliku."""
    try:
        import winreg
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\NewsReader", 0, winreg.KEY_READ) as k:
                v, _ = winreg.QueryValueEx(k, "ts")
                return str(v)
        except OSError:
            return None
    except Exception:
        return None


def _write_shadow(wrapped):
    try:
        import winreg
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, r"Software\NewsReader") as k:
            winreg.SetValueEx(k, "ts", 0, winreg.REG_SZ, wrapped)
    except Exception:
        pass


def _shadow_present():
    """Czy w rejestrze jest jakikolwiek wpis trial (nawet jeśli niepoprawny)."""
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\NewsReader", 0, winreg.KEY_READ) as k:
            winreg.QueryValueEx(k, "ts")
            return True
    except OSError:
        return False
    except Exception:
        return False


# ---- obfuskacja danych pliku .trial ----
# Rozproszony klucz (nie występuje jako literał w binarnym). Łączony XOR.
_S7 = [0x4A, 0x91, 0x33, 0xC8, 0x5E, 0x12, 0xD0, 0x6F]
_S7M = [0x21, 0x55, 0x1B, 0xB7, 0x11, 0x44, 0xA2, 0x33]
_S9 = [0x10, 0xE7, 0x5F, 0x22, 0x77, 0xC3, 0x88, 0xF1]
_S9M = [0x3A, 0x44, 0xB2, 0x15, 0x6E, 0x91, 0xFC, 0x97]

def _k1():
    return bytes(((_S7[i] ^ _S7M[i]) & 0xFF) for i in range(8))

def _k2():
    return bytes(((_S9[i] ^ _S9M[i]) & 0xFF) for i in range(8))

def _hmac(data):
    k = _k1() + _k2()
    import hmac as _h
    return _h.new(k, data, hashlib.sha256).digest()[:16]

def _wrap(ts):
    raw = struct.pack(">d", ts)
    sig = _hmac(raw)
    body = raw + sig
    key = _k1() + _k2()
    out = bytes(body[i] ^ key[i % len(key)] for i in range(len(body)))
    return base64.b64encode(out).decode("ascii")

def _unwrap(s):
    try:
        data = base64.b64decode(s.strip())
    except Exception:
        return None
    key = _k1() + _k2()
    body = bytes(data[i] ^ key[i % len(key)] for i in range(len(data)))
    if len(body) != 24:
        return None
    raw, sig = body[:8], body[8:24]
    if _hmac(raw) != sig:
        return None
    try:
        return struct.unpack(">d", raw)[0]
    except struct.error:
        return None

# Stan manipulacji — ustawiany gdy HMAC się nie zgadza.
_tampered = False

def is_tampered():
    return _tampered

def _read_file(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read().strip()
    except OSError:
        return None


def _write_file(path, data):
    try:
        with open(path, "w", encoding="utf-8") as f:
            f.write(data)
    except OSError:
        pass


def _trial_shadow():
    """Kopia trial w rejestrze Windows (HKCU)."""
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\NewsReader", 0, winreg.KEY_READ) as k:
            v, _ = winreg.QueryValueEx(k, "ts")
            return str(v)
    except (OSError, Exception):
        return None


def _write_shadow(wrapped):
    try:
        import winreg
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, r"Software\NewsReader") as k:
            winreg.SetValueEx(k, "ts", 0, winreg.REG_SZ, wrapped)
    except Exception:
        pass


def _shadow_present():
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\NewsReader", 0, winreg.KEY_READ) as k:
            winreg.QueryValueEx(k, "ts")
            return True
    except (OSError, Exception):
        return False


def _installed_flag():
    """Czy aplikacja była już kiedyś instalowana (zapobiega resetowi trial przez reinstalację).

    Zapisane w osobnym kluczu rejestru (Software\\Microsoft\\CLR_v4.0\\NativeImages\\nr)
    — nietypowa lokalizacja, trudna do znalezienia przypadkowo.
    """
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\CLR_v4.0\NativeImages\nr", 0, winreg.KEY_READ) as k:
            v, _ = winreg.QueryValueEx(k, "v")
            return int(v) == 1
    except (OSError, Exception):
        return False


def _write_installed():
    try:
        import winreg
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\CLR_v4.0\NativeImages\nr") as k:
            winreg.SetValueEx(k, "v", 0, winreg.REG_DWORD, 1)
    except Exception:
        pass


def _all_locations():
    """Zwraca listę (nazwa, raw_wartość) dla wszystkich lokalizacji trial."""
    return [
        ("file", _read_file(_trial_file())),
        ("reg", _trial_shadow()),
        ("cfg", _read_file(_trial_shadow_file())),
    ]


def _any_present():
    if os.path.isfile(_trial_file()):
        return True
    if _shadow_present():
        return True
    if os.path.isfile(_trial_shadow_file()):
        return True
    return False


def _best_trial_ts():
    """Najwcześniejszy poprawny timestamp z wszystkich lokalizacji."""
    best = None
    for _, raw in _all_locations():
        if not raw:
            continue
        ts = _unwrap(raw)
        if ts is None:
            continue
        if best is None or ts < best:
            best = ts
    return best


def _write_all(wrapped):
    _write_file(_trial_file(), wrapped)
    _write_shadow(wrapped)
    _write_file(_trial_shadow_file(), wrapped)


def trial_start():
    """Inicjalizuje i weryfikuje okres próbny.

    Trial jest zapisany w trzech lokalizacjach: plik .trial, rejestr
    HKCU\\Software\\NewsReader\\ts, ukryty plik nr.cfg w UsageLogs.
    Dodatkowo rejestr przechowuje flagę 'installed' (zapisaną raz, nigdy
    nie usuwaną) — zapobiega resetowi trial przez reinstalację.

    Zasady:
    - Brak wszystkich lokalizacji + brak flagi installed → pierwszy start (nowy trial).
    - Brak wszystkich lokalizacji + flaga installed → blokada (reset przez usunięcie).
    - Brak/uszkodzenie jakiejkolwiek lokalizacji (ale inne istnieją) → blokada.
    - Wszystkie poprawne → normalne działanie.
    """
    global _tampered
    locs = _all_locations()
    valid_count = sum(1 for _, raw in locs if raw and _unwrap(raw) is not None)
    present_count = sum(1 for _, raw in locs if raw is not None)
    installed = _installed_flag()

    if present_count == 0 and not installed:
        # Pierwszy start w życiu — utwórz trial wszędzie + flagę installed.
        _write_all(_wrap(time.time()))
        _write_installed()
        return

    if present_count == 0 and installed:
        # Wszystko usunięte, ale aplikacja była instalowana → blokada.
        _tampered = True
        return

    # Coś istnieje — sprawdź spójność.
    best_ts = _best_trial_ts()
    if best_ts is None:
        # Żadna lokalizacja nie ma poprawnych danych, ale coś istnieje.
        _tampered = True
        _write_installed()
        return

    # Sprawdź czy wszystkie trzy są poprawne.
    if valid_count != 3:
        _tampered = True
        wrapped_best = _wrap(best_ts)
        for name, raw in locs:
            ts = _unwrap(raw) if raw else None
            if ts is None:
                if name == "file":
                    _write_file(_trial_file(), wrapped_best)
                elif name == "reg":
                    _write_shadow(wrapped_best)
                elif name == "cfg":
                    _write_file(_trial_shadow_file(), wrapped_best)

    _write_installed()


def _read_trial():
    """Zwraca najwcześniejszy poprawny timestamp, lub None."""
    return _best_trial_ts()


def trial_start_ts():
    return _read_trial()


def trial_days_left():
    """Ile pełnych dni zostało w okresie próbnym (>= 0)."""
    ts = trial_start_ts()
    if ts is None:
        return 0.0 if _tampered else TRIAL_DAYS
    elapsed = time.time() - ts
    left = TRIAL_DAYS - elapsed / 86400.0
    return max(0.0, left)


def trial_expired():
    """True jeśli okres próbny minął LUB wykryto manipulację."""
    return _tampered or trial_days_left() <= 0


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


def is_active():
    """Czy aplikacja może pobierać artykuły: odblokowana LUB w okresie próbnym (bez manipulacji)."""
    return is_unlocked() or (not _tampered and not trial_expired())


def store_key(key):
    """Zapisuje klucz (weryfikacja przy is_unlocked)."""
    p = _unlock_file()
    with open(p, "w", encoding="utf-8") as f:
        f.write(key.strip())


def clear_key():
    try:
        os.remove(_unlock_file())
    except OSError:
        pass


def pubkey_integrity():
    """Zwraca hash klucza publicznego (compat, używane wstarszych wersjach)."""
    return hashlib.sha256(_PUBKEY_B64.encode("ascii")).hexdigest()


# ---- anti-tamper: rozproszone bajty klucza publicznego ----
# Wybrane bajty z DER klucza publicznego, zaciemnione operacjami bitowymi.
# Jeśli atakujący podmieni klucz publiczny, bajty się nie zgadzają.
_GUARD_S = [0x52, 0x4E, 0x81, 0x91, 0xE3, 0x44, 0x06, 0xB9]
_GUARD_M = [0x5F, 0x4B, 0x40, 0x52, 0x50, 0x4B, 0x40, 0x4F]
_GUARD_IDX = [5, 17, 42, 89, 130, 171, 200, 250]


def check_pubkey():
    """Sprawdza integralność klucza publicznego. Zwraca True jeśli OK."""
    try:
        der = base64.b64decode(_PUBKEY_B64)
        guard = bytes(((_GUARD_S[i] ^ _GUARD_M[i]) & 0xFF) for i in range(8))
        return all(der[_GUARD_IDX[i]] == guard[i] for i in range(8))
    except Exception:
        return False