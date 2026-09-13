"""Page rendering and preparation for OCR.

Two jobs:

1. **Split and rasterise.** Every document becomes a list of page images, one
   request each. This is why an arbitrarily large PDF is fine — the 1 MB OCR
   limit is per request, not per document.

2. **Fit under 1 MB.** An A4 page at 300 dpi is several megabytes as PNG. We
   convert to greyscale and binary-search JPEG quality until it fits, dropping
   to a lower DPI if quality alone is not enough. Greyscale is not just for
   size: OCR does not use colour, and removing it removes JPEG chroma noise
   around text.
"""

from __future__ import annotations

import io
import logging
from dataclasses import dataclass, field

import pypdfium2 as pdfium
from PIL import Image, ImageOps

logger = logging.getLogger(__name__)

# Quality floor. Below this, JPEG artefacts start eating thin glyph strokes and
# digits begin to be misread, which is worse than failing over to the model.
MIN_JPEG_QUALITY = 45
JPEG_QUALITY_LADDER = (85, 75, 65, 55, MIN_JPEG_QUALITY)


@dataclass
class RenderedPage:
    page_number: int
    image: bytes
    mime_type: str
    width: int
    height: int
    dpi: int
    """The DPI actually used, which may be lower than requested if the page had
    to be downscaled to fit the size limit."""

    @property
    def byte_size(self) -> int:
        return len(self.image)


@dataclass
class PageText:
    """Text pulled straight from a PDF text layer.

    Exact and free. Unlike OCR output this is not a recognition guess — it is the
    characters the document was authored with.
    """

    page_number: int
    text: str
    #: Word boxes from the text layer, in the same normalised 0-1 shape OCR uses.
    #: A digitally generated PDF therefore yields exact cell coordinates at no
    #: cost, which is strictly better than OCR for those pages.
    words: list[dict] = field(default_factory=list)

    @property
    def has_coordinates(self) -> bool:
        return bool(self.words)


def extract_pdf_text(pdf_bytes: bytes) -> list[PageText]:
    """Read the text layer of every page, if there is one."""
    pages: list[PageText] = []
    pdf = pdfium.PdfDocument(pdf_bytes)
    try:
        for index in range(len(pdf)):
            textpage = pdf[index].get_textpage()
            pages.append(
                PageText(page_number=index + 1, text=textpage.get_text_bounded() or "")
            )
    finally:
        pdf.close()
    return pages


def extract_pdf_words(pdf_bytes: bytes) -> dict[int, list[dict]]:
    """Word-level boxes from a PDF's text layer, keyed by page number.

    Why this matters: a bounding box is what turns a finding from an assertion
    into something an inspector can verify by looking at the page. Until now those
    coordinates came only from OCR, so a digitally generated register — the
    cleanest input there is — produced no coordinates at all.

    Coordinates are normalised to fractions of page size, identical to the OCR
    token shape, so both sources can be merged and traced against
    interchangeably. Text-layer words are placed first when merging because they
    are exact rather than recognised.

    Returns an empty mapping rather than raising when a page has no text layer:
    that is the normal case for a scan, and OCR covers it.
    """
    words: dict[int, list[dict]] = {}

    try:
        import pdfplumber
    except ImportError:
        logger.warning("pdfplumber is not installed; text-layer coordinates skipped")
        return words

    try:
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            for index, page in enumerate(pdf.pages, start=1):
                width = float(page.width or 0) or 1.0
                height = float(page.height or 0) or 1.0

                extracted: list[dict] = []
                # use_text_flow keeps words in reading order, which makes the line
                # grouping below correspond to actual printed rows.
                for word in page.extract_words(use_text_flow=True) or []:
                    text = str(word.get("text") or "").strip()
                    if not text:
                        continue

                    left = float(word.get("x0", 0.0)) / width
                    top = float(word.get("top", 0.0)) / height
                    right = float(word.get("x1", 0.0)) / width
                    bottom = float(word.get("bottom", 0.0)) / height

                    extracted.append(
                        {
                            "text": text,
                            "left": round(max(0.0, min(1.0, left)), 5),
                            "top": round(max(0.0, min(1.0, top)), 5),
                            "width": round(max(0.0, min(1.0, right - left)), 5),
                            "height": round(max(0.0, min(1.0, bottom - top)), 5),
                            # Filled in below once every word on the page is known.
                            "line": 0,
                            "source": "pdf_text",
                        }
                    )

                if extracted:
                    words[index] = _group_into_lines(extracted)
    except Exception as exc:  # noqa: BLE001
        # A malformed text layer must not stop the page being read: OCR and the
        # page image still work, they just lose the free exact coordinates.
        logger.warning(
            "text-layer word extraction failed; continuing without it",
            extra={"error": f"{type(exc).__name__}: {exc}"},
        )

    return words


def _group_into_lines(words: list[dict], tolerance: float = 0.004) -> list[dict]:
    """Assign a line number to each word by vertical position.

    Line grouping is what lets a value split across several words be reassembled
    — "15,250" and ".50" only belong together if they sit on the same printed row.
    Words within ``tolerance`` of a line's baseline join it; the default is about
    0.4% of page height, roughly a third of a line of body text.
    """
    ordered = sorted(words, key=lambda w: (w["top"], w["left"]))

    lines: list[float] = []
    for word in ordered:
        centre = word["top"] + word["height"] / 2

        for line_index, baseline in enumerate(lines):
            if abs(centre - baseline) <= tolerance:
                word["line"] = line_index
                break
        else:
            lines.append(centre)
            word["line"] = len(lines) - 1

    return ordered


def _encode_within_limit(
    image: Image.Image, *, max_bytes: int
) -> tuple[bytes, int] | None:
    """Encode as greyscale JPEG under ``max_bytes``.

    Returns ``(data, quality)`` or None if even the quality floor is too large.
    """
    grey = ImageOps.grayscale(image)

    for quality in JPEG_QUALITY_LADDER:
        buffer = io.BytesIO()
        grey.save(buffer, format="JPEG", quality=quality, optimize=True)
        data = buffer.getvalue()
        if len(data) <= max_bytes:
            return data, quality

    return None


def render_pdf_pages(
    pdf_bytes: bytes,
    *,
    dpi: int = 300,
    fallback_dpi: int = 200,
    max_bytes: int = 1_000_000,
    page_numbers: list[int] | None = None,
) -> list[RenderedPage]:
    """Rasterise PDF pages to JPEGs that each fit within ``max_bytes``.

    Tries the requested DPI first, then the fallback. A page that still will not
    fit is skipped and reported by the caller as needing the vision path, which
    is preferable to shipping an image so compressed that digits are unreadable.
    """
    rendered: list[RenderedPage] = []
    pdf = pdfium.PdfDocument(pdf_bytes)

    try:
        total = len(pdf)
        wanted = page_numbers or list(range(1, total + 1))

        for page_number in wanted:
            if not 1 <= page_number <= total:
                continue

            page = pdf[page_number - 1]
            result: tuple[bytes, int, int, int, int] | None = None

            for attempt_dpi in (dpi, fallback_dpi):
                # pypdfium2 takes a scale factor where 1.0 == 72 dpi.
                bitmap = page.render(scale=attempt_dpi / 72)
                image = bitmap.to_pil()

                encoded = _encode_within_limit(image, max_bytes=max_bytes)
                if encoded is not None:
                    data, quality = encoded
                    result = (data, image.width, image.height, attempt_dpi, quality)
                    break

                logger.info(
                    "page did not fit at dpi; retrying lower",
                    extra={"page": page_number, "dpi": attempt_dpi},
                )

            if result is None:
                logger.warning(
                    "page could not be compressed under the OCR size limit",
                    extra={"page": page_number, "max_bytes": max_bytes},
                )
                continue

            data, width, height, used_dpi, quality = result
            rendered.append(
                RenderedPage(
                    page_number=page_number,
                    image=data,
                    mime_type="image/jpeg",
                    width=width,
                    height=height,
                    dpi=used_dpi,
                )
            )
            logger.debug(
                "page rendered",
                extra={
                    "page": page_number,
                    "dpi": used_dpi,
                    "quality": quality,
                    "bytes": len(data),
                },
            )
    finally:
        pdf.close()

    return rendered


def prepare_image_page(
    image_bytes: bytes, *, max_bytes: int = 1_000_000, max_edge: int = 3500
) -> RenderedPage | None:
    """Normalise a photo or scan into a single OCR-ready page.

    Phone photos are often far larger than any OCR engine needs. Downscaling to
    a sane long edge first means the quality ladder starts from a size that can
    actually fit, instead of crushing a 12-megapixel image to quality 45.
    """
    with Image.open(io.BytesIO(image_bytes)) as opened:
        # Honour EXIF rotation. A sideways register is unreadable, and OCR
        # orientation detection is far less reliable than the camera's own tag.
        image = ImageOps.exif_transpose(opened) or opened
        image = image.convert("L")

        if max(image.size) > max_edge:
            scale = max_edge / max(image.size)
            image = image.resize(
                (max(1, int(image.width * scale)), max(1, int(image.height * scale))),
                Image.LANCZOS,
            )

        encoded = _encode_within_limit(image, max_bytes=max_bytes)
        if encoded is None:
            return None

        data, _quality = encoded
        return RenderedPage(
            page_number=1,
            image=data,
            mime_type="image/jpeg",
            width=image.width,
            height=image.height,
            dpi=0,  # unknown for a photo
        )
