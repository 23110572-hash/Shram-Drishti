"""OCR.space provider.

Free-tier constraints this adapter works around, from their published API docs:

* 1 MB per request, 3 PDF pages per request -> we send one page image at a time
* 500 requests/day per IP                   -> daily budget counter
* Engine 1/2: 25,000/month, Engine 3: 2,500 -> separate counter per engine
* Engine 2 reads Latin scripts and Chinese only, with precise word boxes
* Engine 3 reads 200+ languages including Devanagari, returns tables as
  Markdown, handles handwriting and checkboxes, but its coordinates are less
  precise and asking for them makes the call 2-3x slower

Engine choice is therefore a correctness requirement, not a preference: a Hindi
page sent to Engine 2 comes back as garbage.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass

import httpx

from app.services.ocr.base import OcrError, OcrFailure, OcrResult, OcrToken

logger = logging.getLogger(__name__)

# Language codes in this API are always three letters ("eng", not "en").
LATIN_LANGUAGE = "eng"
# Engine 3 auto-detects across 200+ languages, so no explicit code is needed.
AUTO_LANGUAGE = "auto"

INDIC_HINTS = frozenset(
    {"hin", "hi", "mar", "ben", "guj", "tam", "tel", "kan", "mal", "pan", "ori", "asm"}
)

_RETRYABLE_STATUS = frozenset({429, 500, 502, 503, 504})


@dataclass
class EngineBudget:
    """In-process request counter.

    Not persisted: a restart resetting the count is acceptable for a soft guard
    whose job is to avoid silently burning through a free tier. The provider's
    own 403 remains the hard limit.
    """

    limit: int
    used: int = 0

    @property
    def remaining(self) -> int:
        return max(0, self.limit - self.used)

    @property
    def exhausted(self) -> bool:
        return self.used >= self.limit

    def consume(self) -> None:
        self.used += 1


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
        timeout_seconds: float = 60.0,
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

    # ------------------------------------------------------------- selection
    def _select_engine(self, languages: list[str], *, want_tables: bool) -> int:
        """Choose Engine 2 or Engine 3.

        Engine 3 is required for non-Latin scripts and is much better on
        handwriting and tables, but has a tenth of the quota. So it is spent
        where it is genuinely needed and Engine 2 is used otherwise, preserving
        the Engine 3 allowance for pages that cannot be read without it.
        """
        needs_indic = any(lang.lower() in INDIC_HINTS for lang in languages)

        if needs_indic or want_tables:
            if not self._engine3.exhausted:
                return self._engine_indic
            if needs_indic:
                # No Engine 3 quota left and Engine 2 cannot read this script.
                # Reporting it precisely lets the caller escalate to the vision
                # model instead of storing nonsense.
                raise OcrError(
                    OcrFailure.UNSUPPORTED_SCRIPT,
                    "Engine 3 quota exhausted and page is not Latin script",
                )
            logger.info("engine 3 quota exhausted; using engine 2 for table page")

        return self._engine_latin

    # ---------------------------------------------------------------- public
    async def recognise(
        self,
        image: bytes,
        *,
        mime_type: str = "image/jpeg",
        languages: list[str] | None = None,
        want_tables: bool = True,
    ) -> OcrResult:
        if self._daily.exhausted:
            raise OcrError(
                OcrFailure.QUOTA_EXHAUSTED,
                f"daily OCR budget of {self._daily.limit} requests is used up",
            )

        engine = self._select_engine(languages or [], want_tables=want_tables)
        is_engine3 = engine == self._engine_indic

        form = {
            "apikey": self._api_key,
            "OCREngine": str(engine),
            # Word boxes. Nearly free on Engine 2, and the only way to produce
            # cell-level evidence an inspector can click.
            "isOverlayRequired": "true",
            # Documented as recommended for table, receipt and invoice OCR.
            "isTable": "true" if want_tables else "false",
            # Off by default in the API and documented to improve low-resolution
            # scans significantly. Every scanned register benefits.
            "scale": "true",
            "detectOrientation": "true",
            "language": AUTO_LANGUAGE if is_engine3 else LATIN_LANGUAGE,
        }

        started = time.perf_counter()
        payload = await self._post_with_retry(form, image, mime_type)
        duration_ms = int((time.perf_counter() - started) * 1000)

        self._daily.consume()
        if is_engine3:
            self._engine3.consume()

        return self._parse(payload, engine=engine, duration_ms=duration_ms)

    # ----------------------------------------------------------- transport
    async def _post_with_retry(
        self, form: dict[str, str], image: bytes, mime_type: str, attempts: int = 3
    ) -> dict:
        last_error: Exception | None = None

        async with httpx.AsyncClient(timeout=self._timeout) as client:
            for attempt in range(attempts):
                try:
                    response = await client.post(
                        self._endpoint,
                        data=form,
                        files={"file": ("page.jpg", image, mime_type)},
                    )
                except httpx.TimeoutException as exc:
                    last_error = exc
                except httpx.HTTPError as exc:
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
                            OcrFailure.RATE_LIMITED, "OCR.space rate limit reached"
                        )
                    last_error = RuntimeError(f"HTTP {response.status_code}")

                # Exponential backoff. The free tier is shared infrastructure and
                # transient 5xx responses are common.
                if attempt < attempts - 1:
                    await asyncio.sleep(1.5 * (2**attempt))

        if isinstance(last_error, httpx.TimeoutException):
            raise OcrError(OcrFailure.TIMEOUT, "OCR.space did not respond in time")
        raise OcrError(
            OcrFailure.PROVIDER_ERROR, f"OCR.space request failed: {last_error}"
        )

    # ------------------------------------------------------------- parsing
    def _parse(self, payload: dict, *, engine: int, duration_ms: int) -> OcrResult:
        if payload.get("IsErroredOnProcessing"):
            message = payload.get("ErrorMessage") or "unknown OCR error"
            if isinstance(message, list):
                message = "; ".join(str(m) for m in message)
            raise OcrError(OcrFailure.PROVIDER_ERROR, str(message)[:250])

        results = payload.get("ParsedResults") or []
        if not results:
            raise OcrError(OcrFailure.EMPTY_RESULT, "OCR returned no parsed results")

        # We submit one page per request, so there is exactly one result. The
        # per-page exit code still has to be checked: OCRExitCode 2 means partial
        # success, where the call looks fine overall but this page failed.
        first = results[0]
        if str(first.get("FileParseExitCode", "1")) not in {"1", "2"}:
            raise OcrError(
                OcrFailure.PROVIDER_ERROR,
                str(first.get("ErrorMessage") or "page could not be parsed")[:250],
            )

        text = first.get("ParsedText") or ""
        tokens = self._extract_tokens(first.get("TextOverlay") or {})

        if not text.strip() and not tokens:
            raise OcrError(OcrFailure.EMPTY_RESULT, "OCR found no text on the page")

        # Engine 3 renders tables as Markdown inside ParsedText. Detecting pipe
        # rows lets the extractor use a much cleaner input than raw text.
        markdown = text if (engine != self._engine_latin and "|" in text) else None

        return OcrResult(
            provider=self.name,
            engine=str(engine),
            text=text,
            tokens=tokens,
            markdown=markdown,
            duration_ms=duration_ms,
        )

    @staticmethod
    def _extract_tokens(overlay: dict) -> list[OcrToken]:
        """Convert pixel word boxes into normalised 0-1 coordinates.

        The API returns Left/Top/Width/Height in pixels but no page dimensions,
        so the extent is derived from the boxes themselves. Coordinates have to
        be resolution-independent, or an evidence highlight drawn over a page
        re-rendered at a different DPI lands on the wrong cell.
        """
        lines = overlay.get("Lines") or []
        if not lines:
            return []

        raw: list[tuple[str, float, float, float, float, int]] = []
        max_right = 0.0
        max_bottom = 0.0

        for line_index, line in enumerate(lines):
            for word in line.get("Words") or []:
                text = str(word.get("WordText") or "").strip()
                if not text:
                    continue

                left = float(word.get("Left", 0) or 0)
                top = float(word.get("Top", 0) or 0)
                width = float(word.get("Width", 0) or 0)
                height = float(word.get("Height", 0) or 0)

                raw.append((text, left, top, width, height, line_index))
                max_right = max(max_right, left + width)
                max_bottom = max(max_bottom, top + height)

        if not raw or max_right <= 0 or max_bottom <= 0:
            return []

        # Pad the derived extent slightly. Text rarely reaches the page edge, so
        # the text bounding box alone would overstate every coordinate.
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
            for text, left, top, width, height, line_index in raw
        ]

    # -------------------------------------------------------------- status
    def budget_status(self) -> dict[str, int]:
        return {
            "daily_used": self._daily.used,
            "daily_remaining": self._daily.remaining,
            "engine3_used": self._engine3.used,
            "engine3_remaining": self._engine3.remaining,
        }
