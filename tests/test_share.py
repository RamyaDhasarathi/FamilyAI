"""The share sheet and Shortcuts as a rail: a phone holds a token of its
own, sends a file, a text or a URL, and a word after names the child."""
import uuid

from familyos.execution import disposable
from tests.conftest import pdf


async def _device(family, who="amma", label="Amma's iPhone"):
    r = await family.client.post("/v1/devices", headers=family.h(who), json={"label": label})
    assert r.status_code == 201, r.text
    return r.json()


def _h(token):
    return {"Authorization": f"Bearer {token}"}


async def test_a_phone_token_is_shown_once_sends_a_file_and_the_notice_is_private_to_that_member(family, database):
    issued = await _device(family)
    assert issued["token"].startswith("fosd_") and issued["share_url"].endswith("/v1/inbound/share")
    # The token never comes back from the list.
    listed = (await family.client.get("/v1/devices", headers=family.h("amma"))).json()
    assert [d["label"] for d in listed] == ["Amma's iPhone"] and "token" not in listed[0]
    r = await family.client.post("/v1/inbound/share", headers=_h(issued["token"]),
                                 files={"item": ("circular.pdf", pdf("ptm"), "application/pdf")})
    assert r.status_code == 201, r.text
    assert r.json()["message"] == "Saved to your Inbox: circular.pdf"
    a = r.json()["artifact"]
    assert a["channel"] == "share" and a["visibility"] == "private" and a["submitted_by"] == family.amma["id"]
    assert a["source"]["via"] == "share"
    # Appa cannot see it; Amma's inbox says where it came from.
    assert all(x["id"] != a["id"] for x in (await family.client.get("/v1/inbox", headers=family.h("appa"))).json())
    row = next(x for x in (await family.client.get("/v1/inbox", headers=family.h("amma"))).json() if x["id"] == a["id"])
    assert row["from_label"] == "your phone"
    # The same bytes again from the same phone: the same notice.
    again = await family.client.post("/v1/inbound/share", headers=_h(issued["token"]),
                                     files={"item": ("circular.pdf", pdf("ptm"), "application/pdf")})
    assert again.status_code == 200 and again.json()["duplicate"] is True
    assert again.json()["message"].startswith("Already in your Inbox")


async def test_shared_text_becomes_a_notice_and_a_childs_name_after_it_is_a_tag(family, database):
    await family.consent(family.older)
    issued = await _device(family)
    r = await family.client.post("/v1/inbound/share", headers=_h(issued["token"]),
                                 data={"text": "Dear Parents, PTM on Friday 17 October. Kindly attend."})
    assert r.status_code == 201 and r.json()["artifact"]["media_type"] == "text/plain"
    artifact_id = r.json()["artifact"]["id"]
    # Shortcuts sends text as a text part; that is text too.
    r2 = await family.client.post("/v1/inbound/share", headers=_h(issued["token"]),
                                  files={"item": ("shared.txt", b"Older one", "text/plain")})
    assert r2.status_code == 200, r2.text
    assert r2.json()["tagged"] == ["Older one"] and r2.json()["artifact"] is None
    assert r2.json()["message"] == "Tagged: Older one"
    subjects = await database.fetch("SELECT member_id, inferred FROM artifact_subjects WHERE artifact_id = $1", uuid.UUID(artifact_id))
    assert [(str(s["member_id"]), s["inferred"]) for s in subjects] == [(family.older["id"], False)]


async def test_a_shared_link_is_read_once_as_a_public_page(family, database, monkeypatch):
    issued = await _device(family)

    async def fake_read(url, allow_hosts, *, client=None):
        return disposable.Page(url=url, title="Circular 12", text="Fee circular: term 2 fees are due by 20 October.",
                               sha256="x", bytes=64, truncated=False)

    monkeypatch.setattr(disposable, "read", fake_read)
    r = await family.client.post("/v1/inbound/share", headers=_h(issued["token"]),
                                 data={"url": "https://school.example/circulars/12"})
    assert r.status_code == 201, r.text
    a = r.json()["artifact"]
    assert a["source"]["url"] == "https://school.example/circulars/12" and a["source"]["shared_as"] == "page", a["source"]


async def test_a_link_that_needs_a_login_is_kept_as_the_link_and_said_plainly(family, database, monkeypatch):
    issued = await _device(family)

    async def refuse(url, allow_hosts, *, client=None):
        raise disposable.Refused("HTTP 403")

    monkeypatch.setattr(disposable, "read", refuse)
    r = await family.client.post("/v1/inbound/share", headers=_h(issued["token"]), data={"url": "https://portal.example/fees"})
    assert r.status_code == 201 and r.json()["artifact"]["source"]["shared_as"] == "url"


async def test_a_device_token_never_slides_and_revoking_it_ends_the_shortcut(family, database):
    issued = await _device(family)
    token_id = issued["device"]["id"]
    before = await database.fetchval("SELECT expires_at FROM member_tokens WHERE id = $1", uuid.UUID(token_id))
    assert before is None
    assert (await family.client.get("/v1/me", headers=_h(issued["token"]))).status_code == 200
    after = await database.fetchval("SELECT expires_at FROM member_tokens WHERE id = $1", uuid.UUID(token_id))
    assert after is None
    r = await family.client.delete(f"/v1/devices/{token_id}", headers=family.h("amma"))
    assert r.status_code == 204
    assert (await family.client.get("/v1/me", headers=_h(issued["token"]))).status_code == 401
    # Another member cannot revoke it, and it is gone from the list.
    assert (await family.client.get("/v1/devices", headers=family.h("amma"))).json() == []


async def test_a_device_token_never_used_is_replaced_by_the_next_one_under_its_label(family, database):
    """An app signing in again, or a shortcut set up twice, used to leave a
    trail of "not used yet" rows on the Devices card (six of them on 10 Oct 2026)."""
    first = await _device(family)
    assert (await family.client.get("/v1/me", headers=_h(first["token"]))).status_code == 200   # used: a phone that works
    second = await _device(family)
    third = await _device(family)
    ids = {d["id"] for d in (await family.client.get("/v1/devices", headers=family.h("amma"))).json()}
    assert ids == {first["device"]["id"], third["device"]["id"]}
    assert (await family.client.get("/v1/me", headers=_h(second["token"]))).status_code == 401
    assert (await family.client.get("/v1/me", headers=_h(first["token"]))).status_code == 200


async def test_nothing_shared_is_refused_plainly(family, database):
    issued = await _device(family)
    r = await family.client.post("/v1/inbound/share", headers=_h(issued["token"]), data={"note": "nothing here"})
    assert r.status_code in (400, 422)


async def test_the_item_field_may_be_a_plain_value_as_a_shortcut_sends_text(family, database):
    """Shortcuts puts the shared thing under one field name whatever it is: a
    file part for a photo, a plain value for text. A plain value is a share
    too, not a malformed request."""
    await family.consent(family.older)
    issued = await _device(family)
    r = await family.client.post("/v1/inbound/share", headers=_h(issued["token"]),
                                 data={"item": "Dear Parents, sports day on Friday.", "tag": "Older one"})
    assert r.status_code == 201, r.text
    assert r.json()["artifact"]["channel"] == "share" and r.json()["tagged"] == ["Older one"]
    # And an empty one still says which field was missing.
    r = await family.client.post("/v1/inbound/share", headers=_h(issued["token"]), data={"item": "", "tag": "Nobody"})
    assert r.status_code == 422 and "Nothing was shared" in r.json()["message"]


async def test_a_name_sent_with_the_share_tags_it_in_one_go(family, database):
    await family.consent(family.older)
    issued = await _device(family)
    r = await family.client.post("/v1/inbound/share", headers=_h(issued["token"]),
                                 data={"text": "Dear Parents, sports day on Friday.", "tag": "Older one"})
    assert r.status_code == 201, r.text
    assert r.json()["tagged"] == ["Older one"] and r.json()["message"].endswith("— for Older one")
    artifact_id = uuid.UUID(r.json()["artifact"]["id"])
    rows = await database.fetch("SELECT member_id, inferred FROM artifact_subjects WHERE artifact_id = $1", artifact_id)
    assert [(str(x["member_id"]), x["inferred"]) for x in rows] == [(family.older["id"], False)]
    # "Nobody" from the list is no tag; a name that is nobody's is ignored, not an error.
    r2 = await family.client.post("/v1/inbound/share", headers=_h(issued["token"]), data={"text": "Second notice", "tag": "Nobody"})
    assert r2.status_code == 201 and r2.json()["tagged"] is None
    r3 = await family.client.post("/v1/inbound/share", headers=_h(issued["token"]), data={"text": "Third notice", "tag": "Ravi"})
    assert r3.status_code == 201 and r3.json()["tagged"] is None


async def test_a_photos_name_instead_of_the_photo_is_said_plainly(family, database):
    """A share whose item field is typed Text sends a photo as its identifier.
    The phone shows one line that says which setting to change."""
    r = await family.client.post("/v1/devices", headers=family.h("amma"), json={"label": "Amma's phone"})
    token = r.json()["token"]
    r = await family.client.post("/v1/inbound/share", headers={"Authorization": f"Bearer {token}"},
                                 data={"item": "7D0A6F1E-3C2B-4A5D-9E8F-1234567890AB/L0/001", "tag": "none"})
    assert r.status_code == 422, r.text
    assert "choose File" in r.json()["message"] and "not the photo" in r.json()["message"]
    assert await database.fetchval("SELECT count(*) FROM input_artifacts WHERE channel = 'share'") == 0


async def test_a_photo_sent_as_the_whole_body_with_the_tag_in_a_header_is_a_notice(family, database):
    """The shortcut's other shape: Request Body File. The picture is the body,
    the tag rides in X-Tag, and the result is the same notice."""
    import io

    from PIL import Image
    out = io.BytesIO()
    Image.new("RGB", (320, 240), (200, 160, 140)).save(out, format="JPEG")
    photo = out.getvalue()
    r = await family.client.post("/v1/devices", headers=family.h("amma"), json={"label": "Amma's phone"})
    token = r.json()["token"]
    r = await family.client.post("/v1/inbound/share", content=photo,
                                 headers={"Authorization": f"Bearer {token}", "Content-Type": "image/jpeg", "X-Tag": "none"})
    assert r.status_code == 201, r.text
    art = r.json()["artifact"]
    assert art["media_type"] == "image/jpeg" and art["channel"] == "share" and art["visibility"] == "private"
    assert r.json()["message"].startswith("Saved to your Inbox")
    pic = await family.client.get(f"/v1/artifacts/{art['id']}/picture", headers=family.h("amma"))
    assert pic.status_code == 200 and pic.headers["content-type"] == "image/jpeg"
    # Text the same way is text, and a URL is a URL.
    r = await family.client.post("/v1/inbound/share", content=b"Term 2 fee payment due 20 Oct",
                                 headers={"Authorization": f"Bearer {token}", "Content-Type": "text/plain; charset=utf-8", "X-Visibility": "shared"})
    assert r.status_code == 201 and r.json()["artifact"]["media_type"].startswith("text/") and r.json()["artifact"]["visibility"] == "shared"


async def test_a_share_is_called_by_what_it_says_not_shared_txt(family, database):
    """A text's first real line, a page's address, a note on a photo: the
    Inbox names a share by its content. The reader's first claim, once
    there is one, still wins."""
    from familyos.intake.gateway import headline_for
    assert headline_for(text="02 Oct 2026\n\nTaekwondo Tournament+\n Dear Parent, ...", url=None, note=None, media_type="text/plain") == "Taekwondo Tournament+"
    assert headline_for(text="7D0A6F1E", url=None, note=None, media_type="text/plain") is None
    assert headline_for(text=None, url="https://www.urbancompany.com/x?y=1", note=None, media_type="text/plain") == "A page from www.urbancompany.com"
    assert headline_for(text=None, url=None, note="Varali at the sports day", media_type="image/jpeg") == "Varali at the sports day"
    assert headline_for(text=None, url=None, note=None, media_type="image/heic") == "A photo"
    r = await family.client.post("/v1/devices", headers=family.h("amma"), json={"label": "Amma's phone"})
    token = r.json()["token"]
    r = await family.client.post("/v1/inbound/share", headers={"Authorization": f"Bearer {token}"},
                                 data={"item": "Using MyClassBoard : AACHI GLOBAL SCHOOL\nSA1 TIMINGS IMPORTANT\nDear Parents, half days from Thursday.", "visibility": "shared"})
    assert r.status_code == 201, r.text
    feed = (await family.client.get("/v1/inbox?days=7", headers=family.h("appa"))).json()
    row = next(n for n in feed if n["id"] == r.json()["artifact"]["id"])
    assert row["headline"] == "Using MyClassBoard : AACHI GLOBAL SCHOOL"


async def test_an_adults_name_tags_a_share_as_theirs_and_shares_it(family, database):
    """"paati" after a share: the notice is Paati's, and shared so she sees it."""
    r = await family.client.post("/v1/devices", headers=family.h("amma"), json={"label": "Amma's phone"})
    token = r.json()["token"]
    h = {"Authorization": f"Bearer {token}"}
    r = await family.client.post("/v1/inbound/share", headers=h, data={"item": "Passport renewal appointment on 20 Nov at PSK Chennai"})
    assert r.status_code == 201, r.text
    artifact_id = r.json()["artifact"]["id"]
    r = await family.client.post("/v1/inbound/share", headers=h, data={"item": "paati"})
    assert r.status_code == 200 and r.json()["tagged"] == ["Paati"], r.text
    assert await database.fetchval("SELECT member_id FROM artifact_subjects WHERE artifact_id = $1", uuid.UUID(artifact_id)) == uuid.UUID(family.paati["id"])
    assert await database.fetchval("SELECT visibility FROM input_artifacts WHERE id = $1", uuid.UUID(artifact_id)) == "shared"
    feed = (await family.client.get("/v1/inbox?days=7", headers=family.h("paati"))).json()
    assert any(n["id"] == artifact_id for n in feed)
