"""OpenRouter client for Muse Spark.

Three things this has to get right.

**Schema-constrained output.** Extraction uses ``response_format`` with a strict
JSON schema, so the model returns a validated object rather than prose we have to
parse. Free-form output would mean regex-scraping a wage register, which fails
silently and unpredictably.

**Reasoning suppressed.** Muse Spark has mandatory reasoning. For transcription
that is wasted output tokens, so effort is pinned to the lowest the model allows.
Document reading is perception, not deliberation.

**Budget enforced per document.** A malformed page that triggers repeated retries
must not be able to run up an unbounded bill. Spend is tracked per call and the
budget is checked before each request, not after.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any

import httpx

logger = logging.getLogger(__name__)

OPENROUTER_URL = "https://openrouter.ai/api/v1"

_RETRYABLE_STATUS = frozenset({408, 429, 500, 502, 503, 504})


class LlmError(Exception):
    pass


class BudgetExceeded(LlmError):
    """Raised before a call that would breach the per-document budget."""


class SchemaViolation(LlmError):
    """Model returned JSON that does not satisfy the requested schema."""


@dataclass
class Usage:
    prompt_tokens: int = 0
    completion_tokens: int = 0
    cost_usd: float = 0.0

    def add(self, other: Usage) -> None:
        self.prompt_tokens += other.prompt_tokens
        self.completion_tokens += other.completion_tokens
        self.cost_usd += other.cost_usd


@dataclass
class LlmResponse:
    content: str
    parsed: dict[str, Any] | None
    model: str
    usage: Usage
    duration_ms: int
    finish_reason: str | None = None


@dataclass
class BudgetTracker:
    """Per-document spend ceiling.

    Checked before dispatch rather than after, because knowing you overspent is
    not the same as not overspending.
    """

    limit_usd: float
    spent_usd: float = 0.0
    calls: int = 0
    max_calls: int = 24

    def assert_can_spend(self) -> None:
        if self.spent_usd >= self.limit_usd:
            raise BudgetExceeded(
                f"document budget of ${self.limit_usd:.2f} is exhausted "
                f"(${self.spent_usd:.4f} spent over {self.calls} calls)"
            )
        if self.calls >= self.max_calls:
            # A call ceiling catches runaway retry loops even when each call is
            # individually cheap enough to stay under the dollar limit.
            raise BudgetExceeded(
                f"document call limit of {self.max_calls} reached"
            )

    def record(self, usage: Usage) -> None:
        self.spent_usd += usage.cost_usd
        self.calls += 1


@dataclass
class ContentPart:
    """One piece of a multimodal message."""

    kind: str  # "text" | "image" | "file"
    text: str | None = None
    data_url: str | None = None
    filename: str | None = None

    def to_payload(self) -> dict[str, Any]:
        if self.kind == "text":
            return {"type": "text", "text": self.text or ""}
        if self.kind == "image":
            return {"type": "image_url", "image_url": {"url": self.data_url}}
        if self.kind == "file":
            return {
                "type": "file",
                "file": {"filename": self.filename, "file_data": self.data_url},
            }
        raise ValueError(f"unknown content part: {self.kind}")


def text_part(text: str) -> ContentPart:
    return ContentPart(kind="text", text=text)


def image_part(jpeg_bytes: bytes) -> ContentPart:
    import base64

    encoded = base64.b64encode(jpeg_bytes).decode("ascii")
    return ContentPart(kind="image", data_url=f"data:image/jpeg;base64,{encoded}")


def pdf_part(pdf_bytes: bytes, filename: str = "document.pdf") -> ContentPart:
    import base64

    encoded = base64.b64encode(pdf_bytes).decode("ascii")
    return ContentPart(
        kind="file",
        filename=filename,
        data_url=f"data:application/pdf;base64,{encoded}",
    )


@dataclass
class ModelCapabilities:
    """What a model actually accepts, read from OpenRouter's live catalogue.

    Verified at startup rather than assumed, because sending a PDF to a model
    that only takes images fails at request time — in the middle of a pipeline
    run, on a background thread, where nobody is watching.
    """

    model_id: str
    accepts_text: bool = False
    accepts_image: bool = False
    accepts_file: bool = False
    supports_structured_outputs: bool = False
    context_length: int = 0
    supported_reasoning_efforts: tuple[str, ...] = field(default_factory=tuple)

    @property
    def lowest_reasoning_effort(self) -> str | None:
        """Cheapest effort this model allows.

        Ordered cheapest first. Extraction gains nothing from deliberation, and
        reasoning tokens bill at the completion rate.
        """
        for candidate in ("none", "minimal", "low", "medium", "high"):
            if candidate in self.supported_reasoning_efforts:
                return candidate
        return None


class LlmClient:
    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        reasoning_effort: str = "minimal",
        timeout_seconds: float = 180.0,
        referer: str = "https://github.com/shram-drishti",
        title: str = "Shram Drishti",
    ) -> None:
        if not api_key:
            raise ValueError("OPENROUTER_API_KEY is not set")

        self._api_key = api_key
        self._model = model
        self._reasoning_effort = reasoning_effort
        self._timeout = timeout_seconds
        self._capabilities: ModelCapabilities | None = None
        # OpenRouter uses these for attribution on their dashboard.
        self._headers = {
            "Authorization": f"Bearer {api_key}",
            "HTTP-Referer": referer,
            "X-Title": title,
            "Content-Type": "application/json",
        }

    @property
    def model(self) -> str:
        return self._model

    @property
    def capabilities(self) -> ModelCapabilities | None:
        return self._capabilities

    # -------------------------------------------------------- capability probe
    async def load_capabilities(self) -> ModelCapabilities:
        """Fetch and cache what the configured model supports.

        Fails loudly. A misconfigured model id should stop the process at
        startup, not surface as a confusing 400 hours later.
        """
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                f"{OPENROUTER_URL}/models", headers=self._headers
            )

        if response.status_code != 200:
            raise LlmError(
                f"could not read OpenRouter model catalogue: HTTP {response.status_code}"
            )

        wanted = self._model.split(":", 1)[0]
        for entry in response.json().get("data", []):
            if entry.get("id", "").split(":", 1)[0] != wanted:
                continue

            architecture = entry.get("architecture") or {}
            modalities = set(architecture.get("input_modalities") or [])
            supported = set(entry.get("supported_parameters") or [])
            reasoning = entry.get("reasoning") or {}

            caps = ModelCapabilities(
                model_id=entry["id"],
                accepts_text="text" in modalities,
                accepts_image="image" in modalities,
                accepts_file="file" in modalities,
                supports_structured_outputs="structured_outputs" in supported,
                context_length=int(entry.get("context_length") or 0),
                supported_reasoning_efforts=tuple(
                    reasoning.get("supported_efforts") or ()
                ),
            )
            self._capabilities = caps

            logger.info(
                "model capabilities verified",
                extra={
                    "model": caps.model_id,
                    "image": caps.accepts_image,
                    "file": caps.accepts_file,
                    "structured_outputs": caps.supports_structured_outputs,
                    "context": caps.context_length,
                },
            )

            if not caps.supports_structured_outputs:
                logger.warning(
                    "model does not advertise structured outputs; extraction will "
                    "fall back to prompt-enforced JSON and may be less reliable",
                    extra={"model": caps.model_id},
                )
            return caps

        raise LlmError(
            f"model {self._model!r} is not in the OpenRouter catalogue. "
            "Check LLM_MODEL in .env."
        )

    # ------------------------------------------------------------------ calls
    async def complete(
        self,
        *,
        system: str,
        parts: list[ContentPart],
        budget: BudgetTracker,
        json_schema: dict[str, Any] | None = None,
        schema_name: str = "extraction",
        max_tokens: int = 8000,
        attempts: int = 3,
    ) -> LlmResponse:
        budget.assert_can_spend()

        body: dict[str, Any] = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": [p.to_payload() for p in parts]},
            ],
            "max_tokens": max_tokens,
            # Deterministic as far as the provider allows. Two runs over the same
            # register should not disagree about a wage figure.
            "temperature": 0,
            # Report generation cost per call so the budget is real.
            "usage": {"include": True},
        }

        effort = self._resolve_effort()
        if effort is not None:
            body["reasoning"] = {"effort": effort}

        if json_schema is not None:
            body["response_format"] = {
                "type": "json_schema",
                "json_schema": {
                    "name": schema_name,
                    "strict": True,
                    "schema": json_schema,
                },
            }

        payload = await self._post_with_retry(body, attempts=attempts)
        return self._parse_response(payload, budget=budget, expect_json=json_schema is not None)

    def _resolve_effort(self) -> str | None:
        caps = self._capabilities
        if caps is None:
            return self._reasoning_effort
        if self._reasoning_effort in caps.supported_reasoning_efforts:
            return self._reasoning_effort
        # Configured effort is not offered by this model. Fall back to the
        # cheapest it does support rather than sending an invalid value.
        return caps.lowest_reasoning_effort

    async def _post_with_retry(self, body: dict[str, Any], *, attempts: int) -> dict:
        last_error: Exception | None = None

        async with httpx.AsyncClient(timeout=self._timeout) as client:
            for attempt in range(attempts):
                try:
                    response = await client.post(
                        f"{OPENROUTER_URL}/chat/completions",
                        headers=self._headers,
                        json=body,
                    )
                except httpx.TimeoutException as exc:
                    last_error = exc
                except httpx.HTTPError as exc:
                    last_error = exc
                else:
                    if response.status_code == 200:
                        return dict(response.json())

                    if response.status_code == 401:
                        raise LlmError(
                            "OpenRouter rejected the API key. Check "
                            "OPENROUTER_API_KEY in .env."
                        )
                    if response.status_code == 402:
                        raise LlmError("OpenRouter account has insufficient credit.")

                    if response.status_code not in _RETRYABLE_STATUS:
                        raise LlmError(
                            f"OpenRouter returned HTTP {response.status_code}: "
                            f"{response.text[:300]}"
                        )
                    last_error = RuntimeError(f"HTTP {response.status_code}")

                if attempt < attempts - 1:
                    await asyncio.sleep(2.0 * (2**attempt))

        raise LlmError(f"OpenRouter request failed after {attempts} attempts: {last_error}")

    def _parse_response(
        self, payload: dict, *, budget: BudgetTracker, expect_json: bool
    ) -> LlmResponse:
        choices = payload.get("choices") or []
        if not choices:
            raise LlmError("OpenRouter response contained no choices")

        message = choices[0].get("message") or {}
        content = message.get("content") or ""
        finish_reason = choices[0].get("finish_reason")

        raw_usage = payload.get("usage") or {}
        usage = Usage(
            prompt_tokens=int(raw_usage.get("prompt_tokens") or 0),
            completion_tokens=int(raw_usage.get("completion_tokens") or 0),
            cost_usd=float(raw_usage.get("cost") or 0.0),
        )
        budget.record(usage)

        parsed: dict[str, Any] | None = None
        if expect_json:
            if finish_reason == "length":
                # Truncated output is invalid JSON. Saying so precisely is more
                # useful than a generic parse error, because the fix is different:
                # raise max_tokens or split the page.
                raise SchemaViolation(
                    "model output was truncated before the JSON object closed"
                )
            try:
                parsed = json.loads(content)
            except json.JSONDecodeError as exc:
                raise SchemaViolation(
                    f"model did not return valid JSON: {exc}"
                ) from exc
            if not isinstance(parsed, dict):
                raise SchemaViolation("model returned JSON that is not an object")

        logger.info(
            "llm call complete",
            extra={
                "model": payload.get("model") or self._model,
                "prompt_tokens": usage.prompt_tokens,
                "completion_tokens": usage.completion_tokens,
                "cost_usd": round(usage.cost_usd, 6),
                "budget_spent_usd": round(budget.spent_usd, 6),
                "finish_reason": finish_reason,
            },
        )

        return LlmResponse(
            content=content,
            parsed=parsed,
            model=str(payload.get("model") or self._model),
            usage=usage,
            duration_ms=0,
            finish_reason=finish_reason,
        )


_client: LlmClient | None = None


def get_llm_client() -> LlmClient:
    global _client
    if _client is None:
        from app.config import get_settings

        settings = get_settings()
        _client = LlmClient(
            api_key=settings.openrouter_api_key,
            model=settings.llm_model,
            reasoning_effort=settings.llm_reasoning_effort,
        )
    return _client
