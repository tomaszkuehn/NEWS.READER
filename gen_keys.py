"""Generuje parę kluczy RSA i aktualizuje stałe w license.py.

Uruchom jednorazowo (u autora):
    python gen_keys.py

Tworzy:
- keys/private.pem  — klucz prywatny (do keygen.py, NIE do aplikacji)
- keys/public.pem   — klucz publiczny (referencja)

Aktualizuje license.py:
- _PUBKEY_B64  — base64 klucza publicznego (DER)
- _GUARD_S     — rozproszone bajty DER ^ maska (anti-tamper)

Po wygenerowaniu nowych kluczy, stare klucze (.unlock) przestają działać.
"""
import base64
import os
import re

from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization


GUARD_INDICES = [5, 17, 42, 89, 130, 171, 200, 250]
GUARD_MASK = [0x5F, 0x4B, 0x40, 0x52, 0x50, 0x4B, 0x40, 0x4F]


def generate():
    os.makedirs("keys", exist_ok=True)
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    priv = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    pub = key.public_key().public_bytes(
        encoding=serialization.Encoding.DER,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    with open("keys/private.pem", "wb") as f:
        f.write(key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        ))
    with open("keys/public.pem", "wb") as f:
        f.write(key.public_key().public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        ))
    pub_b64 = base64.b64encode(pub).decode("ascii")
    guard_s = [(pub[i] ^ GUARD_MASK[k]) & 0xFF for k, i in enumerate(GUARD_INDICES)]
    _update_license(pub_b64, guard_s)
    print("keys/private.pem + keys/public.pem wygenerowane")
    print("license.py zaktualizowany (_PUBKEY_B64 + _GUARD_S)")
    print(f"  public key DER: {len(pub)} bajtow")
    print(f"  guard bytes   : {[hex(b) for b in guard_s]}")


def _update_license(pub_b64, guard_s):
    p = os.path.join(os.path.dirname(os.path.abspath(__file__)), "license.py")
    with open(p, "r", encoding="utf-8") as f:
        src = f.read()
    src = re.sub(
        r'_PUBKEY_B64 = \(\s*"([^"]+)"\s*\)',
        lambda m: f'_PUBKEY_B64 = (\n    "{pub_b64}"\n)',
        src,
        count=1,
    )
    guard_hex = ", ".join(f"0x{b:02X}" for b in guard_s)
    src = re.sub(
        r'_GUARD_S = \[[^\]]*\]',
        f'_GUARD_S = [{guard_hex}]',
        src,
        count=1,
    )
    with open(p, "w", encoding="utf-8") as f:
        f.write(src)


if __name__ == "__main__":
    generate()