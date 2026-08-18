"""Generator klucza odblokowującego aplikację News Reader.

Użycie:
    python keygen.py <kod_systemu>

Kod systemu jest wyświetlany w aplikacji po przekroczeniu limitu artykułów
(prompt „Wprowadź klucz"). Wpisz go tutaj, aby otrzymać klucz do wpisania
w aplikacji.

Klucz jest weryfikowany przez license.verify() — to samo urządzenie
(wersja skompilowana z _material() wbudowanym) generuje pasujący klucz.
"""
import base64
import hashlib
import hmac
import sys


def _material():
    """Musi być identyczne z license._material()."""
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


def main():
    if len(sys.argv) < 2:
        print("Użycie: python keygen.py <kod_systemu>")
        print("Kod systemu jest wyświetlany w aplikacji po przekroczeniu limitu.")
        sys.exit(1)
    code = sys.argv[1].strip().upper()
    key = _expect(code)
    print("Klucz do wpisania w aplikacji:")
    print(key)
    print()
    print("Wpisz dokładnie tak, jak pokazano powyżej (bez spacji).")


if __name__ == "__main__":
    main()