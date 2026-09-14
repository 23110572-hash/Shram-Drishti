"""Singleton database mutex used by the in-process pipeline worker."""

from __future__ import annotations

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class PipelineMutex(Base):
    """One locked row serialises expensive work across rolling deployments."""

    __tablename__ = "pipeline_mutex"

    name: Mapped[str] = mapped_column(String(64), primary_key=True)
