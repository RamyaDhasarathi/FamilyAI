"""A photographed page is read inside the parsing sandbox, which forbids
writing any file: OCR goes through pipes, not temporary files."""
import io
import shutil

import pytest

from familyos.extraction import sandbox

pytestmark = pytest.mark.skipif(shutil.which("tesseract") is None, reason="tesseract is not installed")


def _picture(text: str) -> bytes:
    from PIL import Image, ImageDraw, ImageFont
    im = Image.new("RGB", (900, 220), "white")
    d = ImageDraw.Draw(im)
    try:
        font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 56)
    except OSError:
        font = ImageFont.load_default(size=56)
    d.text((30, 60), text, fill="black", font=font)
    buf = io.BytesIO()
    im.save(buf, format="PNG")
    return buf.getvalue()


async def test_a_picture_of_words_is_read_inside_the_sandbox_with_no_file_written():
    doc = await sandbox.parse_isolated(_picture("Fee due Friday"), "image/png")
    assert "ocr_error" not in " ".join(doc.notes) and "ocr_unavailable" not in doc.notes
    assert "Friday" in " ".join(p.text for p in doc.pages)
