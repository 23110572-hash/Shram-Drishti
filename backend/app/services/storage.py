"""Content-addressed file storage on local disk.

Behind an interface so S3 or MinIO can replace it without touching callers.

Files are stored by content hash, sharded two levels deep. Sharding matters:
a single directory with tens of thousands of entries becomes slow to list on
most filesystems, and this store will hold every page image of every document.
"""

from __future__ import annotations

import hashlib
import logging
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO, Protocol

logger = logging.getLogger(__name__)

# Read in chunks so a large upload never has to fit in memory.
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
    """Filesystem-backed store rooted at a single directory."""

    def __init__(self, root: Path) -> None:
        self._root = root
        self._root.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------- internals
    def _path(self, key: str) -> Path:
        candidate = (self._root / key).resolve()
        # Guard against a key like "../../etc/passwd" escaping the root. Keys are
        # generated internally today, but this class will eventually receive
        # keys read back from the database.
        if not candidate.is_relative_to(self._root.resolve()):
            raise ValueError(f"storage key escapes root: {key!r}")
        return candidate

    @staticmethod
    def _key_for(digest: str, prefix: str, suffix: str) -> str:
        return f"{prefix}/{digest[:2]}/{digest[2:4]}/{digest}{suffix}"

    # ---------------------------------------------------------------- writes
    def put_stream(self, stream: BinaryIO, *, prefix: str, suffix: str) -> StoredObject:
        """Stream to a temporary file while hashing, then move into place.

        Hash-then-move rather than hash-then-write means the final path only ever
        contains complete files. A crash mid-upload leaves a temp file, not a
        truncated object that later reads as valid.
        """
        digest = hashlib.sha256()
        size = 0

        tmp_dir = self._root / "_tmp"
        tmp_dir.mkdir(parents=True, exist_ok=True)
        tmp_path = tmp_dir / f"upload-{id(stream):x}-{size}"

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
                # Identical content already stored. Discard the duplicate rather
                # than rewriting it.
                tmp_path.unlink(missing_ok=True)
            else:
                shutil.move(str(tmp_path), str(final))

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
        return StoredObject(key=key, sha256=sha, byte_size=len(data))

    # ----------------------------------------------------------------- reads
    def open(self, key: str) -> BinaryIO:
        return self._path(key).open("rb")

    def read(self, key: str) -> bytes:
        return self._path(key).read_bytes()

    def exists(self, key: str) -> bool:
        return self._path(key).exists()

    def size(self, key: str) -> int:
        return self._path(key).stat().st_size

    def delete(self, key: str) -> None:
        """Remove an object.

        Content-addressed storage means several database rows can legitimately
        reference one key. Callers must confirm no other row needs it before
        deleting — this method does not check.
        """
        self._path(key).unlink(missing_ok=True)


_store: LocalObjectStore | None = None


def get_store() -> LocalObjectStore:
    global _store
    if _store is None:
        from app.config import get_settings

        _store = LocalObjectStore(get_settings().storage_dir / "objects")
    return _store
