"""OCR layer.

One interface, swappable providers. ``get_ocr_provider`` reads configuration so
callers never name a provider directly — switching from the cloud free tier to a
self-hosted engine is a ``.env`` change.
"""

from __future__ import annotations

import logging

from app.services.ocr.base import (
    OcrError,
    OcrFailure,
    OcrProvider,
    OcrResult,
    OcrToken,
)
from app.services.ocr.ocrspace import OcrSpaceProvider

logger = logging.getLogger(__name__)

__all__ = [
    "OcrError",
    "OcrFailure",
    "OcrProvider",
    "OcrResult",
    "OcrToken",
    "OcrSpaceProvider",
    "get_ocr_provider",
]

_provider: OcrProvider | None = None


def get_ocr_provider() -> OcrProvider:
    global _provider
    if _provider is not None:
        return _provider

    from app.config import get_settings

    settings = get_settings()

    if settings.ocr_provider == "ocrspace":
        _provider = OcrSpaceProvider(
            api_key=settings.ocr_space_api_key,
            base_url=settings.ocr_space_base_url,
            engine_latin=settings.ocr_space_engine_latin,
            engine_indic=settings.ocr_space_engine_indic,
            daily_budget=settings.ocr_space_daily_budget,
            engine3_monthly_budget=settings.ocr_space_engine3_monthly_budget,
        )
        return _provider

    raise ValueError(
        f"OCR_PROVIDER={settings.ocr_provider!r} is not implemented. "
        "Supported today: 'ocrspace'."
    )


def reset_provider() -> None:
    """Drop the cached provider. For tests and config reloads."""
    global _provider
    _provider = None
