"""Chiffrement des données sensibles au repos (CV, texte extrait, faits).

Fernet (AES-128-CBC + HMAC-SHA256). La clé vient de STORAGE_ENCRYPTION_KEY ; en
développement uniquement, elle est dérivée de SECRET_KEY pour éviter une étape
de configuration.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
from functools import lru_cache

from cryptography.fernet import Fernet, InvalidToken

from .config import get_settings


@lru_cache
def _fernet() -> Fernet:
    s = get_settings()
    key = s.storage_encryption_key
    if not key:
        if s.environment == "prod":
            raise RuntimeError("STORAGE_ENCRYPTION_KEY est obligatoire en production.")
        key = base64.urlsafe_b64encode(hashlib.sha256(("dev-key:" + s.secret_key).encode()).digest()).decode()
    return Fernet(key.encode() if isinstance(key, str) else key)


def encrypt_bytes(data: bytes) -> bytes:
    return _fernet().encrypt(data)


def decrypt_bytes(token: bytes) -> bytes:
    try:
        return _fernet().decrypt(token)
    except InvalidToken as exc:  # pragma: no cover - clé changée ou donnée corrompue
        raise ValueError("Impossible de déchiffrer la donnée (clé incorrecte ?)") from exc


def encrypt_str(value: str) -> str:
    return encrypt_bytes(value.encode("utf-8")).decode("ascii")


def decrypt_str(value: str) -> str:
    return decrypt_bytes(value.encode("ascii")).decode("utf-8")


def new_token(nbytes: int = 24) -> str:
    return secrets.token_urlsafe(nbytes)


def hash_token(token: str) -> str:
    """Empreinte stockée en base à la place du jeton (un vol de base ne donne pas les liens)."""
    return hmac.new(get_settings().secret_key.encode(), token.encode(), hashlib.sha256).hexdigest()


def fingerprint(text: str) -> str:
    """Empreinte courte d'un contenu, utilisée dans le journal d'audit à la place du contenu."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]
