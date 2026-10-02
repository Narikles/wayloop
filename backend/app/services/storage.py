"""Stockage des CV : chiffré au repos, accessible uniquement par liens temporaires signés."""
from __future__ import annotations

import os
import uuid
from functools import lru_cache
from pathlib import Path

from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from ..config import get_settings
from ..crypto import decrypt_bytes, encrypt_bytes


class Storage:
    def put(self, data: bytes, suffix: str = "") -> str:  # pragma: no cover - interface
        raise NotImplementedError

    def get(self, key: str) -> bytes:  # pragma: no cover
        raise NotImplementedError

    def delete(self, key: str) -> None:  # pragma: no cover
        raise NotImplementedError


class LocalEncryptedStorage(Storage):
    def __init__(self, root: str) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        if "/" in key or ".." in key:
            raise ValueError("clé invalide")
        return self.root / key

    def put(self, data: bytes, suffix: str = "") -> str:
        key = uuid.uuid4().hex + suffix + ".enc"
        p = self._path(key)
        p.write_bytes(encrypt_bytes(data))
        os.chmod(p, 0o600)
        return key

    def get(self, key: str) -> bytes:
        return decrypt_bytes(self._path(key).read_bytes())

    def delete(self, key: str) -> None:
        p = self._path(key)
        if p.exists():
            p.unlink()


class S3EncryptedStorage(Storage):
    """Stockage objet compatible S3 (Scaleway, OVHcloud…), chiffré côté application."""

    def __init__(self) -> None:
        import boto3  # dépendance optionnelle

        s = get_settings()
        self.bucket = s.s3_bucket
        self.client = boto3.client(
            "s3",
            endpoint_url=s.s3_endpoint_url,
            aws_access_key_id=s.s3_access_key,
            aws_secret_access_key=s.s3_secret_key,
            region_name=s.s3_region,
        )

    def put(self, data: bytes, suffix: str = "") -> str:
        key = uuid.uuid4().hex + suffix + ".enc"
        self.client.put_object(Bucket=self.bucket, Key=key, Body=encrypt_bytes(data))
        return key

    def get(self, key: str) -> bytes:
        obj = self.client.get_object(Bucket=self.bucket, Key=key)
        return decrypt_bytes(obj["Body"].read())

    def delete(self, key: str) -> None:
        self.client.delete_object(Bucket=self.bucket, Key=key)


@lru_cache
def get_storage() -> Storage:
    s = get_settings()
    if s.storage_backend == "s3":
        return S3EncryptedStorage()
    return LocalEncryptedStorage(s.storage_local_path)


def _serializer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(get_settings().secret_key, salt="file-link")


def signed_file_token(application_id: str) -> str:
    return _serializer().dumps({"a": application_id})


def read_file_token(token: str) -> str | None:
    try:
        data = _serializer().loads(token, max_age=get_settings().signed_url_ttl_seconds)
    except (BadSignature, SignatureExpired):
        return None
    return data.get("a")
