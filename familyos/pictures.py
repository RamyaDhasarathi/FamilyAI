"""What kind of picture a shared image is: a photograph the family will
want to see again, or a document that happens to be a picture -- a QR
code, a screenshot, a photographed circular.

Memories shows photographs. A QR code for a fee, a screenshot of a fee
reminder and a photographed timetable are notices, and belong in the Inbox
where their dates are read. The call is made once, when the picture is
read, from the picture itself: a barcode in it, words the OCR could read,
the proportions of a phone's screen, or a camera's own stamp in the EXIF.
Nothing of the picture is kept but the verdict.
"""
from __future__ import annotations

import io
import logging

logger = logging.getLogger(__name__)

PHOTO, DOCUMENT = "photo", "document"
# OCR this long means the picture is something to read, not look at.
DOCUMENT_CHARS = 80
# A phone's screen, give or take: a screenshot has exactly these proportions
# and no camera behind it. A camera shoots 4:3 or 16:9, never this tall, so
# those are left out: a photo that lost its EXIF on the way stays a photo.
SCREEN_RATIOS = (19.5 / 9, 20 / 9, 19 / 9, 18 / 9, 2436 / 1125, 2556 / 1179, 2796 / 1290)


def kind_of(data: bytes, *, ocr_chars: int = 0) -> str:
    """photo or document, from the bytes and what the OCR read."""
    try:
        from PIL import Image

        from familyos.extraction.parse import _heif
        _heif()
        with Image.open(io.BytesIO(data)) as im:
            width, height = im.size
            exif = im.getexif()
            camera = bool(exif.get(271) or exif.get(272) or exif.get(36867))   # Make, Model, DateTimeOriginal
            if _has_barcode(im):
                return DOCUMENT
    except Exception:  # noqa: BLE001 - an unreadable picture is not a memory either way
        logger.info("picture could not be opened for sorting", exc_info=True)
        return DOCUMENT
    if ocr_chars >= DOCUMENT_CHARS:
        return DOCUMENT
    if camera:
        return PHOTO
    if width and height and _screen_shaped(width, height):
        return DOCUMENT
    return PHOTO


def _has_barcode(im) -> bool:
    try:
        import zxingcpp
        return bool(zxingcpp.read_barcodes(im.convert("L")))
    except Exception:  # noqa: BLE001 - no reader, or a format it cannot take
        return False


def _screen_shaped(width: int, height: int) -> bool:
    long, short = max(width, height), min(width, height)
    ratio = long / short
    return any(abs(ratio - r) < 0.02 for r in SCREEN_RATIOS) and long >= 800


# ----------------------------------------------------------------------------
# reading a picture with the household's own model
# ----------------------------------------------------------------------------

TRANSCRIBE = ("Transcribe everything written in this picture, exactly as it appears: the original language and script, "
              "every line in reading order, numbers, dates, amounts and names exactly as printed. Do not summarise, "
              "translate or explain. Output only the transcription, as plain text.")
PICTURE_MAX_SIDE = 1280
TRANSCRIPTION_MIN = 20        # fewer characters than this is the model saying there is nothing to read


def _jpeg_for_model(data: bytes) -> bytes:
    """The picture as the model will see it: upright, at most 1280px on a side."""
    import io

    from PIL import Image, ImageOps

    from familyos.extraction.parse import _heif
    _heif()
    with Image.open(io.BytesIO(data)) as im:
        im = ImageOps.exif_transpose(im).convert("RGB")
        im.thumbnail((PICTURE_MAX_SIDE, PICTURE_MAX_SIDE))
        out = io.BytesIO()
        im.save(out, format="JPEG", quality=85, optimize=True)
        return out.getvalue()


async def transcribe(data: bytes, *, client=None) -> str:
    """What is written in the picture, read by the household's own model
    through its OpenAI-compatible endpoint, streamed. The picture goes to
    that model and nowhere else."""
    import base64

    from familyos.settings import settings
    if client is None:
        import openai
        client = openai.AsyncOpenAI(api_key=settings.local_model_key or "local", base_url=settings.local_model_url, max_retries=1, timeout=300)
    picture = base64.b64encode(_jpeg_for_model(data)).decode("ascii")
    stream = await client.chat.completions.create(
        model=settings.local_model, max_tokens=4000, stream=True,
        messages=[{"role": "user", "content": [
            {"type": "text", "text": TRANSCRIBE},
            {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64," + picture}}]}])
    parts: list[str] = []
    async for chunk in stream:
        for choice in chunk.choices or []:
            if choice.delta and choice.delta.content:
                parts.append(choice.delta.content)
    return "".join(parts).strip()


def as_document(media_type: str, text: str, data: bytes):
    """The transcription as a parsed document, so the reader and the
    grounding work on it as they would on OCR: one page, the picture's
    size, no word boxes."""
    import io

    from PIL import Image

    from familyos.extraction.parse import Page, ParsedDocument, _heif
    _heif()
    with Image.open(io.BytesIO(data)) as im:
        width, height = im.size
    return ParsedDocument(media_type, [Page(1, text, [], width, height, "ocr")], ["read by the household's own model from the picture"])
