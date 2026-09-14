"""Private S3-compatible object storage with a small local parser cache.

Supabase Storage is the durable copy. Render's free filesystem is used only for
temporary/local-path access required by PDF and image libraries. Uploads are
streamed in fixed-size chunks and S3 transfers use one thread, so storing a file
does not duplicate the whole document in the 512 MB web process.
"""

from __future__ import annotations

import hashlib
import logging
import shutil
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any, BinaryIO, Protocol

logger = logging.getLogger(__name__)

_CHUNK = 1024 * 1024
_S3_PART = 5 * 1024 * 1024


@dataclass(frozen=True)
class StoredObject:
    key: str
    sha256: str
    byte_size: int


class ObjectStore(Protocol):
    def put_stream(self, stream: BinaryIO, *, prefix: str, suffix: str) -> StoredObject: ...
    def put_bytes(self, data: bytes, *, prefix: str, suffix: str) -> StoredObject: ...
    def open(self, key: str) -> BinaryIO: ...
    def read(self, key: str) -> bytes: ...
    def exists(self, key: str) -> bool: ...
    def delete(self, key: str) -> None: ...
    def size(self, key: str) -> int: ...
    def presigned_get_url(
        self, key: str, *, expires_in: int = 900, response_content_type: str | None = None
    ) -> str: ...


class S3ObjectStore:
    """Content-addressed private objects in Supabase's S3-compatible API."""

    def __init__(
        self,
        root: Path,
        *,
        endpoint_url: str,
        region: str,
        access_key_id: str,
        secret_access_key: str,
        bucket: str,
    ) -> None:
        missing = [
            name
            for name, value in {
                "S3_ENDPOINT_URL": endpoint_url,
                "S3_REGION": region,
                "S3_ACCESS_KEY_ID": access_key_id,
                "S3_SECRET_ACCESS_KEY": secret_access_key,
                "S3_BUCKET": bucket,
            }.items()
            if not value.strip()
        ]
        if missing:
            raise RuntimeError(f"private object storage is not configured: {', '.join(missing)}")

        import boto3
        from boto3.s3.transfer import TransferConfig
        from botocore.config import Config

        self._root = root
        self._root.mkdir(parents=True, exist_ok=True)
        self._bucket = bucket
        self._client: Any = boto3.client(
            "s3",
            endpoint_url=endpoint_url.rstrip("/"),
            region_name=region,
            aws_access_key_id=access_key_id,
            aws_secret_access_key=secret_access_key,
            config=Config(
                signature_version="s3v4",
                s3={"addressing_style": "path"},
                max_pool_connections=2,
                retries={"max_attempts": 3, "mode": "standard"},
            ),
        )
        self._transfer = TransferConfig(
            multipart_threshold=_S3_PART,
            multipart_chunksize=_S3_PART,
            max_concurrency=1,
            use_threads=False,
        )

    def _path(self, key: str) -> Path:
        candidate = (self._root / key).resolve()
        if not candidate.is_relative_to(self._root.resolve()):
            raise ValueError(f"storage key escapes root: {key!r}")
        return candidate

    @staticmethod
    def _key_for(digest: str, prefix: str, suffix: str) -> str:
        return f"{prefix}/{digest[:2]}/{digest[2:4]}/{digest}{suffix}"

    @staticmethod
    def _is_missing(exc: Exception) -> bool:
        response = getattr(exc, "response", {})
        code = str(response.get("Error", {}).get("Code", ""))
        return code in {"404", "NoSuchKey", "NotFound"}

    def _remote_exists(self, key: str) -> bool:
        try:
            self._client.head_object(Bucket=self._bucket, Key=key)
            return True
        except Exception as exc:  # botocore is imported lazily with the client
            if self._is_missing(exc):
                return False
            raise

    def _upload_path(self, key: str, path: Path) -> None:
        if self._remote_exists(key):
            return
        self._client.upload_file(
            str(path),
            self._bucket,
            key,
            ExtraArgs={"ContentType": _content_type(path.suffix)},
            Config=self._transfer,
        )

    def _ensure_local(self, key: str) -> bool:
        path = self._path(key)
        if path.exists():
            return True
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(f"{path.name}.{threading.get_ident()}.tmp")
        try:
            self._client.download_file(
                self._bucket,
                key,
                str(temporary),
                Config=self._transfer,
            )
            temporary.replace(path)
            return True
        except Exception as exc:
            if self._is_missing(exc):
                return False
            raise
        finally:
            temporary.unlink(missing_ok=True)

    def put_stream(self, stream: BinaryIO, *, prefix: str, suffix: str) -> StoredObject:
        digest = hashlib.sha256()
        size = 0
        tmp_dir = self._root / "_tmp"
        tmp_dir.mkdir(parents=True, exist_ok=True)
        tmp_path = tmp_dir / f"upload-{id(stream):x}-{threading.get_ident()}"

        try:
            with tmp_path.open("wb") as output:
                while chunk := stream.read(_CHUNK):
                    digest.update(chunk)
                    size += len(chunk)
                    output.write(chunk)

            sha = digest.hexdigest()
            key = self._key_for(sha, prefix, suffix)
            final = self._path(key)
            final.parent.mkdir(parents=True, exist_ok=True)
            if final.exists():
                tmp_path.unlink(missing_ok=True)
            else:
                shutil.move(str(tmp_path), str(final))

            self._upload_path(key, final)
            return StoredObject(key=key, sha256=sha, byte_size=size)
        finally:
            tmp_path.unlink(missing_ok=True)

    def put_bytes(self, data: bytes, *, prefix: str, suffix: str) -> StoredObject:
        sha = hashlib.sha256(data).hexdigest()
        key = self._key_for(sha, prefix, suffix)
        final = self._path(key)
        final.parent.mkdir(parents=True, exist_ok=True)
        if not final.exists():
            final.write_bytes(data)
        self._upload_path(key, final)
        return StoredObject(key=key, sha256=sha, byte_size=len(data))

    def open(self, key: str) -> BinaryIO:
        if not self._ensure_local(key):
            raise FileNotFoundError(key)
        return self._path(key).open("rb")

    def read(self, key: str) -> bytes:
        if not self._ensure_local(key):
            raise FileNotFoundError(key)
        return self._path(key).read_bytes()

    def exists(self, key: str) -> bool:
        return self._path(key).exists() or self._remote_exists(key)

    def size(self, key: str) -> int:
        path = self._path(key)
        if path.exists():
            return path.stat().st_size
        try:
            response = self._client.head_object(Bucket=self._bucket, Key=key)
        except Exception as exc:
            if self._is_missing(exc):
                raise FileNotFoundError(key) from exc
            raise
        return int(response["ContentLength"])

    def presigned_get_url(
        self,
        key: str,
        *,
        expires_in: int = 900,
        response_content_type: str | None = None,
    ) -> str:
        """Return a short-lived private download URL without fetching the object."""
        self._path(key)  # Apply the same traversal validation as local operations.
        if not 60 <= expires_in <= 3600:
            raise ValueError("presigned URL lifetime must be between 60 and 3600 seconds")
        params = {"Bucket": self._bucket, "Key": key}
        if response_content_type:
            params["ResponseContentType"] = response_content_type
        return str(
            self._client.generate_presigned_url(
                "get_object",
                Params=params,
                ExpiresIn=expires_in,
            )
        )

    def delete(self, key: str) -> None:
        self._path(key).unlink(missing_ok=True)
        self._client.delete_object(Bucket=self._bucket, Key=key)


def _content_type(suffix: str) -> str:
    return {
        ".pdf": "application/pdf",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".tif": "image/tiff",
        ".tiff": "image/tiff",
        ".webp": "image/webp",
        ".bmp": "image/bmp",
        ".txt": "text/plain",
        ".csv": "text/csv",
        ".ecr": "text/plain",
    }.get(suffix.lower(), "application/octet-stream")


_store: S3ObjectStore | None = None


def get_store() -> S3ObjectStore:
    global _store
    if _store is None:
        from app.config import get_settings

        settings = get_settings()
        _store = S3ObjectStore(
            settings.storage_dir / "objects",
            endpoint_url=settings.s3_endpoint_url,
            region=settings.s3_region,
            access_key_id=settings.s3_access_key_id,
            secret_access_key=settings.s3_secret_access_key,
            bucket=settings.s3_bucket,
        )
    return _store
