import os
import base64
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from app.core.config import settings


def _key() -> bytes:
    k = settings.APP_SECRET_KEY.encode("utf-8")
    if len(k) < 32:
        k = (k + b"0" * 32)[:32]
    return k[:32]


def encrypt_text(plain: str) -> str:
    aes = AESGCM(_key())
    nonce = os.urandom(12)
    ct = aes.encrypt(nonce, plain.encode("utf-8"), None)
    return base64.urlsafe_b64encode(nonce + ct).decode("utf-8")


def decrypt_text(token: str) -> str:
    raw = base64.urlsafe_b64decode(token.encode("utf-8"))
    nonce, ct = raw[:12], raw[12:]
    aes = AESGCM(_key())
    pt = aes.decrypt(nonce, ct, None)
    return pt.decode("utf-8")
