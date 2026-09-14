"""Content-addressed storage with a local cache and durable Neon mirror.

Render's free filesystem is ephemeral. Parsers still need real local paths, so
objects are written to disk first and mirrored to Postgres. After a restart a
read restores the object into the local cache from Neon. This keeps accepted
uploads and evidence images recoverable without adding another infrastructure
service.
"""

from __future__ import annotations

import hashlib
import logging
import shutil
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO, Protocol

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

logger = logging.getLogger(__name__)

_CHUNK = 1024 * 1024


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


class LocalObjectStore:
    """Filesystem cache backed by content-addressed blobs in Postgres."""

    def __init__(self, root: Path) -> None:
        self._root = root
        self._root.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        candidate = (self._root / key).resolve()
        if not candidate.is_relative_to(self._root.resolve()):
            raise ValueError(f"storage key escapes root: {key!r}")
        return candidate

    @staticmethod
    def _key_for(digest: str, prefix: str, suffix: str) -> str:
        return f"{prefix}/{digest[:2]}/{digest[2:4]}/{digest}{suffix}"

    def _persist_file(self, stored: StoredObject, path: Path) -> None:
        from app.db import get_session_factory
        from app.models.infrastructure import ObjectBlob

        with get_session_factory()() as session:
            present = session.execute(
                select(ObjectBlob.key).where(ObjectBlob.key == stored.key)
            ).scalar_one_or_none()
            if present is not None:
                return
            session.add(
                ObjectBlob(
                    key=stored.key,
                    sha256=stored.sha256,
                    byte_size=stored.byte_size,
                    content=path.read_bytes(),
                )
            )
            try:
                session.commit()
            except IntegrityError:
                # Another request persisted identical content between our check
                # and insert. The content-addressed key guarantees equivalence.
                session.rollback()

    def _ensure_local(self, key: str) -> bool:
        path = self._path(key)
        if path.exists():
            return True

        from app.db import get_session_factory
        from app.models.infrastructure import ObjectBlob

        with get_session_factory()() as session:
            content = session.execute(
                select(ObjectBlob.content).where(ObjectBlob.key == key)
            ).scalar_one_or_none()
        if content is None:
            return False

        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(f"{path.name}.{threading.get_ident()}.tmp")
        try:
            temporary.write_bytes(content)
            temporary.replace(path)
        finally:
            temporary.unlink(missing_ok=True)
        return True

    def put_stream(self, stream: BinaryIO, *, prefix: str, suffix: str) -> StoredObject:
        digest = hashlib.sha256()
        size = 0
        tmp_dir = self._root / "_tmp"
        tmp_dir.mkdir(parents=True, exist_ok=True)
        tmp_path = tmp_dir / f"upload-{id(stream):x}-{threading.get_ident()}"

        try:
            with tmp_path.open("wb") as out:
                while chunk := stream.read(_CHUNK):
                    digest.update(chunk)
                    size += len(chunk)
                    out.write(chunk)

            sha = digest.hexdigest()
            key = self._key_for(sha, prefix, suffix)
            final = self._path(key)
            final.parent.mkdir(parents=True, exist_ok=True)
            if final.exists():
                tmp_path.unlink(missing_ok=True)
            else:
                shutil.move(str(tmp_path), str(final))

            stored = StoredObject(key=key, sha256=sha, byte_size=size)
            self._persist_file(stored, final)
            return stored
        finally:
            tmp_path.unlink(missing_ok=True)

    def put_bytes(self, data: bytes, *, prefix: str, suffix: str) -> StoredObject:
        sha = hashlib.sha256(data).hexdigest()
        key = self._key_for(sha, prefix, suffix)
        final = self._path(key)
        final.parent.mkdir(parents=True, exist_ok=True)
        if not final.exists():
            final.write_bytes(data)
        stored = StoredObject(key=key, sha256=sha, byte_size=len(data))
        self._persist_file(stored, final)
        return stored

    def open(self, key: str) -> BinaryIO:
        self._ensure_local(key)
        return self._path(key).open("rb")

    def read(self, key: str) -> bytes:
        self._ensure_local(key)
        return self._path(key).read_bytes()

    def exists(self, key: str) -> bool:
        if self._path(key).exists():
            return True
        from app.db import get_session_factory
        from app.models.infrastructure import ObjectBlob

        with get_session_factory()() as session:
            return session.execute(
                select(ObjectBlob.key).where(ObjectBlob.key == key)
            ).scalar_one_or_none() is not None

    def size(self, key: str) -> int:
        path = self._path(key)
        if path.exists():
            return path.stat().st_size
        from app.db import get_session_factory
        from app.models.infrastructure import ObjectBlob

        with get_session_factory()() as session:
            size = session.execute(
                select(ObjectBlob.byte_size).where(ObjectBlob.key == key)
            ).scalar_one_or_none()
        if size is None:
            raise FileNotFoundError(key)
        return int(size)

    def delete(self, key: str) -> None:
        self._path(key).unlink(missing_ok=True)
        from app.db import get_session_factory
        from app.models.infrastructure import ObjectBlob

        with get_session_factory()() as session:
            blob = session.get(ObjectBlob, key)
            if blob is not None:
                session.delete(blob)
                session.commit()


_store: LocalObjectStore | None = None


def get_store() -> LocalObjectStore:
    global _store
    if _store is None:
        from app.config import get_settings

        _store = LocalObjectStore(get_settings().storage_dir / "objects")
    return _store
