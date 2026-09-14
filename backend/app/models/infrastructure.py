"""Durable object bytes and the singleton pipeline mutex."""

from __future__ import annotations

from sqlalchemy import BigInteger, LargeBinary, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models.base import TimestampMixin


class ObjectBlob(TimestampMixin, Base):
    """Content-addressed bytes mirrored in Postgres.

    Render's free filesystem is ephemeral. Keeping the bytes in Neon means an
    accepted upload can still be processed after a restart or deployment; the
    local filesystem remains only a fast cache for parsers and page images.
    """

    __tablename__ = "object_blob"

    key: Mapped[str] = mapped_column(String(512), primary_key=True)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    byte_size: Mapped[int] = mapped_column(BigInteger, nullable=False)
    content: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)


class PipelineMutex(Base):
    """One locked row serialises expensive pipeline work across deployments."""

    __tablename__ = "pipeline_mutex"

    name: Mapped[str] = mapped_column(String(64), primary_key=True)
