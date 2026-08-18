"""Generator klucza odblokowującego aplikację News Reader.

Użycie:
    python keygen.py <kod_systemu>

Kod systemu jest wyświetlany w aplikacji (menu ustawień → O aplikacji).
Wpisz go tutaj, aby otrzymać klucz do wpisania w aplikacji.

Klucz jest podpisany RSA (PKCS#1 v1.5) kluczem prywatnym (keys/private.pem).
Aplikacja weryfikuje go wbudowanym kluczem publicznym — bez klucza prywatnego
nie da się wygenerować poprawnego klucza.
"""
import base64
import sys

from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives import hashes, serialization


def _load_private_key(path="keys/private.pem"):
    with open(path, "rb") as f:
        return serialization.load_pem_private_key(f.read(), password=None)


def generate_key(code, priv_path="keys/private.pem"):
    """Zwraca klucz (base64) dla danego kodu systemu."""
    priv = _load_private_key(priv_path)
    payload = f"NEWSREADER|{code}".encode("utf-8")
    sig = priv.sign(payload, padding.PKCS1v15(), hashes.SHA256())
    return base64.b64encode(sig).decode("ascii")


def main():
    if len(sys.argv) < 2:
        print("Użycie: python keygen.py <kod_systemu>")
        print("Kod systemu jest wyświetlany w aplikacji (O aplikacji).")
        sys.exit(1)
    code = sys.argv[1].strip().upper()
    try:
        key = generate_key(code)
    except FileNotFoundError:
        print("Brak pliku keys/private.pem — uruchom gen_keys.py aby wygenerować parę kluczy.")
        sys.exit(1)
    print("Klucz do wpisania w aplikacji:")
    print(key)
    print()
    print("Wpisz dokładnie tak, jak pokazano powyżej (bez spacji).")


if __name__ == "__main__":
    main()