"""OCR.space provider for images and signed document URLs.

The production pipeline submits a short-lived Supabase URL instead of rendering
PDF pages inside the 512 MB Render process. OCR.space returns one ``ParsedResults``
entry per PDF page; this adapter preserves that page order and rejects partial
results rather than silently extracting an incomplete register.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from typing import Any

import httpx

from app.services.ocr.base import OcrError, OcrFailure, OcrResult, OcrToken

logger = logging.getLogger(__name__)

LATIN_LANGUAGE = "eng"
AUTO_LANGUAGE = "auto"

INDIC_HINTS = frozenset(
    {"hin", "hi", "mar", "ben", "guj", "tam", "tel", "kan", "mal", "pan", "ori", "asm"}
)
_RETRYABLE_STATUS = frozenset({429, 500, 502, 503, 504})


@dataclass
class EngineBudget:
    """Soft in-process request/conversion guard; provider limits remain authoritative."""

    limit: int
    used: int = 0

    @property
    def remaining(self) -> int:
        return max(0, self.limit - self.used)

    @property
    def exhausted(self) -> bool:
        return self.used >= self.limit

    def consume(self, units: int = 1) -> None:
        self.used += max(0, units)


class OcrSpaceProvider:
    name = "ocrspace"

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str,
        engine_latin: int = 2,
        engine_indic: int = 3,
        daily_budget: int = 500,
        engine3_monthly_budget: int = 2500,
        timeout_seconds: float = 180.0,
    ) -> None:
        if not api_key:
            raise ValueError("OCR_SPACE_API_KEY is not set")

        self._api_key = api_key
        self._endpoint = f"{base_url.rstrip('/')}/parse/image"
        self._engine_latin = engine_latin
        self._engine_indic = engine_indic
        self._timeout = timeout_seconds
        self._daily = EngineBudget(limit=daily_budget)
        self._engine3 = EngineBudget(limit=engine3_monthly_budget)

    def _select_engine(
        self, languages: list[str], *, want_tables: bool, conversions: int = 1
    ) -> int:
        needs_indic = any(lang.lower() in INDIC_HINTS for lang in languages)

        if needs_indic or want_tables:
            if self._engine3.remaining >= conversions:
                return self._engine_indic
            if needs_indic:
                raise OcrError(
                    OcrFailure.UNSUPPORTED_SCRIPT,
                    "Engine 3 quota is too low to read every page of this document",
                )
            logger.info("engine 3 quota exhausted; using engine 2 for table document")

        return self._engine_latin

    def _request_form(self, engine: int, *, want_tables: bool) -> dict[str, str]:
        is_engine3 = engine == self._engine_indic
        return {
            "apikey": self._api_key,
            "OCREngine": str(engine),
            "isOverlayRequired": "true",
            "isTable": "true" if want_tables else "false",
            "scale": "true",
            "detectOrientation": "true",
            "language": AUTO_LANGUAGE if is_engine3 else LATIN_LANGUAGE,
        }

    async def recognise(
        self,
        image: bytes,
        *,
        mime_type: str = "image/jpeg",
        languages: list[str] | None = None,
        want_tables: bool = True,
    ) -> OcrResult:
        """Retained for bounded callers; production documents use ``recognise_url``."""
        self._ensure_daily_budget()
        engine = self._select_engine(languages or [], want_tables=want_tables)
        form = self._request_form(engine, want_tables=want_tables)

        started = time.perf_counter()
        payload = await self._post_with_retry(
            form,
            image=image,
            mime_type=mime_type,
        )
        duration_ms = int((time.perf_counter() - started) * 1000)
        self._consume(engine, conversions=1)

        pages = self._parse_results(
            payload,
            engine=engine,
            duration_ms=duration_ms,
            allow_blank_pages=False,
        )
        if len(pages) != 1:
            raise OcrError(
                OcrFailure.PROVIDER_ERROR,
                f"OCR returned {len(pages)} results for one image",
            )
        return pages[0]

    async def recognise_url(
        self,
        source_url: str,
        *,
        mime_type: str,
        languages: list[str] | None = None,
        expected_pages: int,
        want_tables: bool = True,
    ) -> list[OcrResult]:
        """Read an image or PDF directly from a short-lived private HTTPS URL."""
        if not source_url.lower().startswith("https://"):
            raise OcrError(
                OcrFailure.PROVIDER_ERROR,
                "OCR document URLs must use HTTPS",
            )
        if expected_pages < 1:
            raise OcrError(OcrFailure.EMPTY_RESULT, "document has no pages")

        self._ensure_daily_budget()
        engine = self._select_engine(
            languages or [],
            want_tables=want_tables,
            conversions=expected_pages,
        )
        form = self._request_form(engine, want_tables=want_tables)
        form["url"] = source_url
        if mime_type == "application/pdf":
            form["filetype"] = "PDF"

        started = time.perf_counter()
        payload = await self._post_with_retry(form)
        duration_ms = int((time.perf_counter() - started) * 1000)
        self._consume(engine, conversions=expected_pages)

        pages = self._parse_results(
            payload,
            engine=engine,
            duration_ms=duration_ms,
            allow_blank_pages=True,
        )
        if len(pages) != expected_pages:
            raise OcrError(
                OcrFailure.PROVIDER_ERROR,
                "OCR returned "
                f"{len(pages)} of {expected_pages} page(s). The OCR plan may have "
                "rejected the document size or page count; split the PDF and retry.",
            )
        return pages

    def _ensure_daily_budget(self) -> None:
        if self._daily.exhausted:
            raise OcrError(
                OcrFailure.QUOTA_EXHAUSTED,
                f"daily OCR budget of {self._daily.limit} requests is used up",
            )

    def _consume(self, engine: int, *, conversions: int) -> None:
        self._daily.consume()
        if engine == self._engine_indic:
            self._engine3.consume(conversions)

    async def _post_with_retry(
        self,
        form: dict[str, str],
        *,
        image: bytes | None = None,
        mime_type: str = "image/jpeg",
        attempts: int = 3,
    ) -> dict[str, Any]:
        last_error: Exception | None = None

        async with httpx.AsyncClient(timeout=self._timeout) as client:
            for attempt in range(attempts):
                try:
                    if image is None:
                        response = await client.post(self._endpoint, data=form)
                    else:
                        response = await client.post(
                            self._endpoint,
                            data=form,
                            files={"file": ("page.jpg", image, mime_type)},
                        )
                except (httpx.TimeoutException, httpx.HTTPError) as exc:
                    last_error = exc
                else:
                    if response.status_code == 403:
                        raise OcrError(
                            OcrFailure.QUOTA_EXHAUSTED,
                            "OCR.space rejected the key or the quota is exhausted",
                        )

                    if response.status_code not in _RETRYABLE_STATUS:
                        try:
                            return dict(response.json())
                        except ValueError as exc:
                            raise OcrError(
                                OcrFailure.PROVIDER_ERROR,
                                "OCR.space returned a non-JSON response",
                            ) from exc

                    if response.status_code == 429 and attempt == attempts - 1:
                        raise OcrError(
                            OcrFailure.RATE_LIMITED,
                            "OCR.space rate limit reached",
                        )
                    last_error = RuntimeError(f"HTTP {response.status_code}")

                if attempt < attempts - 1:
                    await asyncio.sleep(1.5 * (2**attempt))

        if isinstance(last_error, httpx.TimeoutException):
            raise OcrError(OcrFailure.TIMEOUT, "OCR.space did not respond in time")
        raise OcrError(
            OcrFailure.PROVIDER_ERROR,
            f"OCR.space request failed: {last_error}",
        )

    def _parse_results(
        self,
        payload: dict[str, Any],
        *,
        engine: int,
        duration_ms: int,
        allow_blank_pages: bool,
    ) -> list[OcrResult]:
        if payload.get("IsErroredOnProcessing"):
            raise OcrError(
                OcrFailure.PROVIDER_ERROR,
                self._error_message(payload, "unknown OCR error"),
            )

        exit_code = str(payload.get("OCRExitCode") or "")
        if exit_code in {"3", "4"}:
            raise OcrError(
                OcrFailure.PROVIDER_ERROR,
                self._error_message(payload, "OCR could not parse the document"),
            )

        raw_results = payload.get("ParsedResults") or []
        if not isinstance(raw_results, list) or not raw_results:
            raise OcrError(OcrFailure.EMPTY_RESULT, "OCR returned no parsed results")

        pages: list[OcrResult] = []
        for page_number, raw in enumerate(raw_results, start=1):
            if not isinstance(raw, dict):
                raise OcrError(
                    OcrFailure.PROVIDER_ERROR,
                    f"OCR returned an invalid result for page {page_number}",
                )

            if str(raw.get("FileParseExitCode", "")) != "1":
                raise OcrError(
                    OcrFailure.PROVIDER_ERROR,
                    f"page {page_number}: "
                    + self._error_message(raw, "page could not be parsed"),
                )

            text = str(raw.get("ParsedText") or "")
            tokens = self._extract_tokens(raw.get("TextOverlay") or {})
            if not allow_blank_pages and not text.strip() and not tokens:
                raise OcrError(OcrFailure.EMPTY_RESULT, "OCR found no text on the page")

            pages.append(
                OcrResult(
                    provider=self.name,
                    engine=str(engine),
                    text=text,
                    tokens=tokens,
                    markdown=(
                        text
                        if engine != self._engine_latin and "|" in text
                        else None
                    ),
                    duration_ms=duration_ms,
                )
            )

        return pages

    @staticmethod
    def _error_message(payload: dict[str, Any], fallback: str) -> str:
        message = payload.get("ErrorMessage") or payload.get("ErrorDetails") or fallback
        if isinstance(message, list):
            message = "; ".join(str(item) for item in message)
        return str(message)[:250]

    @staticmethod
    def _extract_tokens(overlay: dict[str, Any]) -> list[OcrToken]:
        lines = overlay.get("Lines") or []
        if not isinstance(lines, list) or not lines:
            return []

        raw_tokens: list[tuple[str, float, float, float, float, int]] = []
        max_right = 0.0
        max_bottom = 0.0

        for line_index, line in enumerate(lines):
            if not isinstance(line, dict):
                continue
            for word in line.get("Words") or []:
                if not isinstance(word, dict):
                    continue
                text = str(word.get("WordText") or "").strip()
                if not text:
                    continue
                try:
                    left = float(word.get("Left", 0) or 0)
                    top = float(word.get("Top", 0) or 0)
                    width = float(word.get("Width", 0) or 0)
                    height = float(word.get("Height", 0) or 0)
                except (TypeError, ValueError):
                    continue

                raw_tokens.append((text, left, top, width, height, line_index))
                max_right = max(max_right, left + width)
                max_bottom = max(max_bottom, top + height)

        if not raw_tokens or max_right <= 0 or max_bottom <= 0:
            return []

        page_width = max_right * 1.02
        page_height = max_bottom * 1.02
        return [
            OcrToken(
                text=text,
                left=left / page_width,
                top=top / page_height,
                width=width / page_width,
                height=height / page_height,
                line=line_index,
            )
            for text, left, top, width, height, line_index in raw_tokens
        ]

    def budget_status(self) -> dict[str, int]:
        return {
            "daily_used": self._daily.used,
            "daily_remaining": self._daily.remaining,
            "engine3_used": self._engine3.used,
            "engine3_remaining": self._engine3.remaining,
        }
