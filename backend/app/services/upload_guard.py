"""Upload validation.

Everything here answers one question: is this file safe to spend OCR and model
budget on. Rejection is cheap; processing a malicious or malformed file is not.

Threats specifically handled:

* **Extension lying.** A ``.pdf`` that is actually a ZIP. Type is sniffed from
  content signatures, never from the filename.
* **Decompression bombs.** A 20 KB PDF that expands into thousands of pages, or
  a JPEG whose header claims 60000x60000 pixels and exhausts memory when
  rasterised. Page count and pixel area are capped before any rendering.
* **Encrypted PDFs.** Cannot be read, so they must fail fast with a clear
  message instead of producing empty OCR that looks like a blank register.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import BinaryIO

import filetype
import pypdfium2 as pdfium
from PIL import Image

logger = logging.getLogger(__name__)

# Pillow refuses very large images by default to prevent decompression bombs.
# Raise it slightly for legitimate high-DPI scans, but keep a ceiling.
Image.MAX_IMAGE_PIXELS = 120_000_000

ALLOWED_MIME_TYPES = frozenset(
    {
        "application/pdf",
        "image/jpeg",
        "image/png",
        "image/tiff",
        "image/webp",
        "image/bmp",
    }
)

# Text formats we accept without sniffing, because EPF ECR files are plain text
# and carry no magic bytes.
TEXT_EXTENSIONS = frozenset({".txt", ".csv", ".ecr"})

MAX_UPLOAD_BYTES = 64 * 1024 * 1024  # 64 MB
MAX_PDF_PAGES = 500
MAX_IMAGE_PIXELS = 80_000_000  # ~8000 x 10000


class RejectionCode(StrEnum):
    EMPTY_FILE = "EMPTY_FILE"
    TOO_LARGE = "TOO_LARGE"
    UNSUPPORTED_TYPE = "UNSUPPORTED_TYPE"
    CORRUPT_FILE = "CORRUPT_FILE"
    ENCRYPTED_PDF = "ENCRYPTED_PDF"
    TOO_MANY_PAGES = "TOO_MANY_PAGES"
    IMAGE_TOO_LARGE = "IMAGE_TOO_LARGE"


class UploadRejected(Exception):
    def __init__(self, code: RejectionCode, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class Inspection:
    """What we learned about an accepted file."""

    mime_type: str
    page_count: int
    has_text_layer: bool
    """True when a PDF carries extractable text, meaning Mode A applies and
    neither OCR nor the model is needed for it."""


def sniff_mime(path: Path, original_filename: str) -> str:
    """Determine type from content, falling back to extension only for text.

    ``filetype`` reads magic bytes. A file claiming to be a PDF but starting
    with ``PK`` is a ZIP, and treating it as a PDF is how parser exploits get
    reached.
    """
    kind = filetype.guess(str(path))
    if kind is not None:
        return str(kind.mime)

    suffix = Path(original_filename).suffix.lower()
    if suffix in TEXT_EXTENSIONS:
        return "text/plain"

    return "application/octet-stream"


def _inspect_pdf(path: Path) -> Inspection:
    try:
        pdf = pdfium.PdfDocument(str(path))
    except pdfium.PdfiumError as exc:
        message = str(exc).lower()
        if "password" in message or "encrypt" in message:
            raise UploadRejected(
                RejectionCode.ENCRYPTED_PDF,
                "This PDF is password protected. Upload an unprotected copy.",
            ) from exc
        raise UploadRejected(
            RejectionCode.CORRUPT_FILE, "This PDF could not be opened."
        ) from exc

    try:
        page_count = len(pdf)

        if page_count == 0:
            raise UploadRejected(RejectionCode.CORRUPT_FILE, "This PDF has no pages.")

        if page_count > MAX_PDF_PAGES:
            # Guards against a small file that expands into an enormous
            # rasterisation workload.
            raise UploadRejected(
                RejectionCode.TOO_MANY_PAGES,
                f"This PDF has {page_count} pages. The limit is {MAX_PDF_PAGES}.",
            )

        # Sample the first few pages for a text layer. Sampling rather than
        # scanning every page keeps validation fast on long documents, and a
        # register with text on page one has text throughout in practice.
        has_text = False
        for index in range(min(3, page_count)):
            text = pdf[index].get_textpage().get_text_bounded() or ""
            if len(text.strip()) >= 40:
                has_text = True
                break

        return Inspection(
            mime_type="application/pdf",
            page_count=page_count,
            has_text_layer=has_text,
        )
    finally:
        pdf.close()


def _inspect_image(path: Path, mime_type: str) -> Inspection:
    try:
        with Image.open(path) as image:
            width, height = image.size
            # verify() detects truncated or malformed data without decoding the
            # whole image into memory.
            image.verify()
    except UploadRejected:
        raise
    except Exception as exc:
        raise UploadRejected(
            RejectionCode.CORRUPT_FILE, "This image file could not be read."
        ) from exc

    if width * height > MAX_IMAGE_PIXELS:
        raise UploadRejected(
            RejectionCode.IMAGE_TOO_LARGE,
            f"This image is {width}x{height}, which exceeds the processing limit.",
        )

    return Inspection(mime_type=mime_type, page_count=1, has_text_layer=False)


def inspect(path: Path, *, original_filename: str, byte_size: int) -> Inspection:
    """Validate an uploaded file, or raise ``UploadRejected``."""
    if byte_size == 0:
        raise UploadRejected(RejectionCode.EMPTY_FILE, "The file is empty.")

    if byte_size > MAX_UPLOAD_BYTES:
        raise UploadRejected(
            RejectionCode.TOO_LARGE,
            f"The file is {byte_size // (1024 * 1024)} MB. The limit is "
            f"{MAX_UPLOAD_BYTES // (1024 * 1024)} MB.",
        )

    mime_type = sniff_mime(path, original_filename)

    if mime_type == "application/pdf":
        return _inspect_pdf(path)

    if mime_type in ALLOWED_MIME_TYPES:
        return _inspect_image(path, mime_type)

    if mime_type == "text/plain":
        # EPF ECR and similar structured text. No pages, no rasterisation.
        return Inspection(mime_type=mime_type, page_count=1, has_text_layer=True)

    raise UploadRejected(
        RejectionCode.UNSUPPORTED_TYPE,
        f"Files of type {mime_type} are not accepted. Upload a PDF or an image.",
    )


def guard_stream_size(stream: BinaryIO) -> None:
    """Reject an oversized upload before it is written to disk.

    Only usable when the stream reports a length. Streaming uploads without a
    Content-Length still need the post-write size check in ``inspect``.
    """
    try:
        current = stream.tell()
        stream.seek(0, 2)
        size = stream.tell()
        stream.seek(current)
    except (OSError, AttributeError):
        return

    if size > MAX_UPLOAD_BYTES:
        raise UploadRejected(
            RejectionCode.TOO_LARGE,
            f"The file exceeds the {MAX_UPLOAD_BYTES // (1024 * 1024)} MB limit.",
        )
