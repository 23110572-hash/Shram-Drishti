"""OCR provider interface and result types.

Providers are interchangeable behind ``OcrProvider``. Coordinates are always
normalised to 0-1 relative to page size, never raw pixels: a bounding box has to
survive the page being re-rendered at a different DPI, or the evidence viewer
would highlight the wrong cell.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Protocol


class OcrFailure(StrEnum):
    """Why a page could not be read.

    The distinction drives routing: a quota failure should fail over to a local
    provider, while an unsupported script should escalate to the vision model.
    """

    PAGE_TOO_LARGE = "PAGE_TOO_LARGE"
    QUOTA_EXHAUSTED = "QUOTA_EXHAUSTED"
    RATE_LIMITED = "RATE_LIMITED"
    UNSUPPORTED_SCRIPT = "UNSUPPORTED_SCRIPT"
    PROVIDER_ERROR = "PROVIDER_ERROR"
    TIMEOUT = "TIMEOUT"
    EMPTY_RESULT = "EMPTY_RESULT"


class OcrError(Exception):
    def __init__(self, reason: OcrFailure, message: str) -> None:
        super().__init__(message)
        self.reason = reason
        self.message = message

    @property
    def should_failover(self) -> bool:
        """Whether trying a different provider could plausibly succeed."""
        return self.reason in {
            OcrFailure.QUOTA_EXHAUSTED,
            OcrFailure.RATE_LIMITED,
            OcrFailure.PROVIDER_ERROR,
            OcrFailure.TIMEOUT,
        }


@dataclass(frozen=True)
class OcrToken:
    """One recognised word with its position on the page.

    All coordinates are fractions of page width and height.
    """

    text: str
    left: float
    top: float
    width: float
    height: float
    line: int = 0
    confidence: float | None = None

    def as_dict(self) -> dict:
        return {
            "text": self.text,
            "left": round(self.left, 5),
            "top": round(self.top, 5),
            "width": round(self.width, 5),
            "height": round(self.height, 5),
            "line": self.line,
        }


@dataclass
class OcrResult:
    provider: str
    engine: str
    text: str
    tokens: list[OcrToken] = field(default_factory=list)
    # Engine 3 returns tables as Markdown. Far better model input than
    # positional text, so kept separately when the provider supplies it.
    markdown: str | None = None
    duration_ms: int | None = None

    @property
    def has_coordinates(self) -> bool:
        return bool(self.tokens)

    @property
    def word_count(self) -> int:
        return len(self.tokens) if self.tokens else len(self.text.split())


class OcrProvider(Protocol):
    name: str

    async def recognise(
        self,
        image: bytes,
        *,
        mime_type: str,
        languages: list[str],
        want_tables: bool = True,
    ) -> OcrResult: ...
