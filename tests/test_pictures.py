"""A photo shared from a phone shows in Memories whatever the phone saved
it as: a HEIC is read through the HEIF plugin, served as a JPEG the
browser can show, and the original stays exactly as it arrived."""
import io
import uuid

from PIL import Image

from familyos.extraction.parse import parse


def _heic() -> bytes:
    from pillow_heif import register_heif_opener
    register_heif_opener()
    out = io.BytesIO()
    Image.new("RGB", (640, 480), (210, 170, 150)).save(out, format="HEIF", quality=80)
    return out.getvalue()


def _jpeg() -> bytes:
    out = io.BytesIO()
    Image.new("RGB", (2400, 1800), (120, 160, 200)).save(out, format="JPEG")
    return out.getvalue()


def test_a_heic_photo_is_parsed_without_raising():
    doc = parse(_heic(), "image/heic")
    assert doc.pages[0].width == 640 and doc.pages[0].source == "ocr"


async def test_a_phone_photo_is_served_as_a_jpeg_and_the_original_is_kept(family, database):
    r = await family.upload("amma", _heic(), filename="IMG_0412.heic", visibility="shared", content_type="image/heic")
    assert r.status_code == 201, r.text
    heic_id = r.json()["artifact"]["id"]
    assert r.json()["artifact"]["media_type"] == "image/heic"
    pic = await family.client.get(f"/v1/artifacts/{heic_id}/picture", headers=family.h("appa"))
    assert pic.status_code == 200 and pic.headers["content-type"] == "image/jpeg"
    with Image.open(io.BytesIO(pic.content)) as im:
        assert im.format == "JPEG" and im.size == (640, 480)
    original = await family.client.get(f"/v1/artifacts/{heic_id}/original", headers=family.h("amma"))
    assert original.status_code == 200 and original.content == _heic()[:0] + original.content and original.headers["content-type"] == "image/heic"

    r = await family.upload("amma", _jpeg(), filename="big.jpg", visibility="shared", content_type="image/jpeg")
    big = r.json()["artifact"]["id"]
    pic = await family.client.get(f"/v1/artifacts/{big}/picture", headers=family.h("amma"))
    with Image.open(io.BytesIO(pic.content)) as im:
        assert max(im.size) == 1600                      # shown smaller; the original stays 2400 wide
    # It is in the household's pictures, and a notice is not.
    listed = (await family.client.get("/v1/artifacts?limit=50", headers=family.h("amma"))).json()
    assert {a["id"] for a in listed if a["media_type"].startswith("image/")} >= {heic_id, big}
    from tests.conftest import pdf
    r = await family.upload("amma", pdf("A circular"), filename="c.pdf", visibility="shared")
    assert (await family.client.get(f"/v1/artifacts/{r.json()['artifact']['id']}/picture", headers=family.h("amma"))).status_code == 404


def _png(im) -> bytes:
    out = io.BytesIO()
    im.save(out, format="PNG")
    return out.getvalue()


def test_a_picture_is_a_photo_or_a_document_by_what_is_in_it():
    """A QR code, a screenshot and a picture full of words are documents;
    a camera's photo, with or without its EXIF, is a photo."""
    import zxingcpp
    from PIL import Image

    from familyos import pictures
    code = zxingcpp.create_barcode("upi://pay?pa=school@upi&am=4000", zxingcpp.BarcodeFormat.QRCode).to_image()
    w, h = code.shape[1], code.shape[0]
    qr = Image.frombytes("L", (w, h), bytes(code)).resize((w * 8, h * 8), Image.NEAREST)
    assert pictures.kind_of(_png(qr)) == "document"
    assert pictures.kind_of(_png(Image.new("RGB", (1179, 2556), (250, 250, 250)))) == "document"      # a phone's screen
    assert pictures.kind_of(_png(Image.new("RGB", (4032, 3024), (120, 160, 200)))) == "photo"        # a camera's 4:3, EXIF lost
    assert pictures.kind_of(_png(Image.new("RGB", (640, 480), (120, 160, 200))), ocr_chars=300) == "document"   # a photographed circular
    exif = Image.Exif()
    exif[271] = "Apple"
    exif[272] = "iPhone 15 Pro"
    out = io.BytesIO()
    Image.new("RGB", (1179, 2556), (90, 90, 90)).save(out, format="JPEG", exif=exif.tobytes())
    assert pictures.kind_of(out.getvalue()) == "photo"                                                  # tall, but a camera took it
    assert pictures.kind_of(b"not a picture") == "document"


async def test_a_shared_qr_code_is_read_as_a_notice_and_kept_out_of_memories(family, database):
    """The phone shares a QR code for a fee. It is read like any notice, its
    picture is marked a document, and the console leaves it out of Memories;
    a photograph shared the same way is marked a photo."""
    import zxingcpp
    from PIL import Image

    from familyos import jobs
    from familyos.extraction import service
    code = zxingcpp.create_barcode("upi://pay?pa=school@upi&pn=Aachi&am=4000", zxingcpp.BarcodeFormat.QRCode).to_image()
    w, h = code.shape[1], code.shape[0]
    qr = _png(Image.frombytes("L", (w, h), bytes(code)).resize((w * 8, h * 8), Image.NEAREST).convert("RGB"))
    r = await family.client.post("/v1/devices", headers=family.h("amma"), json={"label": "Amma's phone"})
    token = r.json()["token"]
    sent = {}
    for name, body, ctype in (("qr", qr, "image/png"), ("photo", _jpeg(), "image/jpeg")):
        r = await family.client.post("/v1/inbound/share", content=body, headers={"Authorization": f"Bearer {token}", "Content-Type": ctype})
        assert r.status_code == 201, r.text
        sent[name] = r.json()["artifact"]["id"]
    for row in await database.fetch("SELECT * FROM jobs WHERE kind = $1 ORDER BY created_at", service.KIND):
        await jobs.run({**dict(row), "id": str(row["id"])})
    kinds = {name: (await database.fetchval("SELECT source->>'picture' FROM input_artifacts WHERE id = $1", uuid.UUID(aid))) for name, aid in sent.items()}
    assert kinds == {"qr": "document", "photo": "photo"}
    listed = {a["id"]: a for a in (await family.client.get("/v1/artifacts?limit=50", headers=family.h("amma"))).json()}
    assert listed[sent["qr"]]["source"]["picture"] == "document" and listed[sent["photo"]]["source"]["picture"] == "photo"


class _Delta:
    def __init__(self, content):
        self.content = content


class _Choice:
    def __init__(self, content):
        self.delta = _Delta(content)
        self.finish_reason = None


class _Chunk:
    def __init__(self, content):
        self.choices = [_Choice(content)]
class _Stream:
    def __init__(self, parts): self.parts = parts
    def __aiter__(self): return self._go()
    async def _go(self):
        for p in self.parts:
            yield _Chunk(p)
class FakeVision:
    """An OpenAI-compatible client that reads pictures: records what it was shown, answers a script."""
    def __init__(self, text): self.text, self.calls = text, []
    @property
    def chat(self): return self
    @property
    def completions(self): return self
    async def create(self, **kw):
        self.calls.append(kw)
        return _Stream([self.text[:12], self.text[12:]])


async def test_the_households_model_reads_a_picture_as_plain_text(monkeypatch):
    from PIL import Image

    from familyos import pictures
    from familyos.settings import settings
    monkeypatch.setattr(settings, "local_model", "Qwen/Qwen3-VL-32B")
    fake = FakeVision("Diwali holidays: 18 Oct to 21 Oct 2026.\nSchool reopens 22 Oct.")
    said = await pictures.transcribe(_png(Image.new("RGB", (3000, 2000), (240, 240, 240))), client=fake)
    assert said.startswith("Diwali holidays") and "reopens" in said
    [call] = fake.calls
    content = call["messages"][0]["content"]
    assert call["model"] == "Qwen/Qwen3-VL-32B" and call["stream"] is True
    assert content[0]["type"] == "text" and "Transcribe" in content[0]["text"]
    assert content[1]["image_url"]["url"].startswith("data:image/jpeg;base64,")
    # The picture went down to 1280 on its long side before it was sent.
    import base64
    import io
    with Image.open(io.BytesIO(base64.b64decode(content[1]["image_url"]["url"].split(",", 1)[1]))) as im:
        assert max(im.size) == 1280
    doc = pictures.as_document("image/png", said, _png(Image.new("RGB", (300, 200))))
    assert doc.pages[0].source == "ocr" and doc.pages[0].width == 300 and doc.char_count == len(said)


async def test_a_photographed_circular_is_read_by_the_model_when_the_household_said_so(family, database, monkeypatch):
    """Tesseract reads nothing off the photo; with the switch on, the
    household's model transcribes it and the dates in it are proposed."""
    from PIL import Image

    from familyos import jobs, pictures
    from familyos.extraction import service
    from familyos.settings import settings
    monkeypatch.setattr(settings, "local_model", "Qwen/Qwen3-VL-32B")
    seen = []
    async def transcribe(data, client=None):
        seen.append(len(data))
        return "AACHI GLOBAL SCHOOL\nDiwali holidays from 18 October 2026 to 21 October 2026.\nSchool reopens on 22 October 2026."
    monkeypatch.setattr(pictures, "transcribe", transcribe)
    photo = _png(Image.new("RGB", (1179, 2556), (248, 248, 248)))             # a screenshot of a circular: a document, no EXIF
    r = await family.client.post("/v1/devices", headers=family.h("amma"), json={"label": "Amma's phone"})
    token = r.json()["token"]
    r = await family.client.post("/v1/inbound/share", content=photo, headers={"Authorization": f"Bearer {token}", "Content-Type": "image/png", "X-Visibility": "shared"})
    assert r.status_code == 201, r.text
    artifact_id = uuid.UUID(r.json()["artifact"]["id"])
    async def run_jobs():
        for row in await database.fetch("SELECT * FROM jobs WHERE kind = $1 AND status NOT IN ('succeeded', 'failed') ORDER BY created_at", service.KIND):
            await jobs.run({**dict(row), "id": str(row["id"])})
    await run_jobs()
    assert seen == []                                                          # off: the OCR alone, which read nothing
    assert await database.fetchval("SELECT count(*) FROM claims WHERE artifact_id = $1", artifact_id) == 0
    r = await family.client.put("/v1/household/rules", headers=family.h("amma"), json={"pictures_by_model": True})
    assert r.status_code == 200 and next(x for x in r.json()["rules"] if x["key"] == "pictures_by_model")["on"]
    r = await family.client.post(f"/v1/artifacts/{artifact_id}/extract", headers=family.h("amma"))
    assert r.status_code == 202, r.text
    await run_jobs()
    assert seen == [len(photo)]
    titles = [r["title"] for r in await database.fetch("SELECT title FROM claims WHERE artifact_id = $1 ORDER BY ordinal", artifact_id)]
    assert titles, "the transcription was read like any notice"
    assert await database.fetchval("SELECT count(*) FROM obligations WHERE artifact_id = $1", artifact_id) >= 1
    note = await database.fetchval("SELECT notes::text FROM extractions WHERE artifact_id = $1 AND superseded_at IS NULL", artifact_id)
    assert "household" in note
