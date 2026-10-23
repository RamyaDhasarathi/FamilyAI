"""An app on the phone: an errand that reads it through the phone's own
hands (the XCTest driver). No sealed session, a look only, run only on the
phone; the words on the screen come in as a private notice."""
import asyncio
import uuid

from familyos import errands
from familyos.db import pool
from familyos.execution import apps, phone
from tests.test_errands import _p


async def test_an_app_errand_is_a_look_with_no_sign_in_bound_to_the_phone(family, database):
    r = await family.client.post("/v1/errands", headers=family.h("amma"),
                                 json={"service": "myclassboard", "kind": "look", "title": "Read the school's notices", "spec": {"what": "Announcements"}})
    assert r.status_code == 201, r.text
    e = r.json()
    assert e["status"] == "approved" and e["outcome"] == {"run_on": "phone"}
    assert e["spec"]["where"] == {"service": "myclassboard", "bundle": "com.myclassboard.commonParentPortal", "label": "MyClassBoard school app", "on": "the phone"}
    # The school's own wrapper of the platform's app, by its bundle id; a bundle that is not one is refused.
    r = await family.client.post("/v1/errands", headers=family.h("amma"),
                                 json={"service": "myclassboard", "kind": "look", "title": "x", "spec": {"what": "Announcements", "bundle": "com.mcb.aachiGlobal"}})
    assert r.status_code == 201 and r.json()["spec"]["where"]["bundle"] == "com.mcb.aachiGlobal"
    r = await family.client.post("/v1/errands", headers=family.h("amma"),
                                 json={"service": "myclassboard", "kind": "look", "title": "x", "spec": {"what": "Announcements", "bundle": "not a bundle"}})
    assert r.status_code == 422
    assert e["spec"]["payment"]["mode"] == "none" and e["spec"]["limits"]["max_amount"] == 0
    # Nothing is queued for the server: it has no hands for an app.
    assert await database.fetchval("SELECT count(*) FROM jobs WHERE kind = $1 AND spec->>'errand_id' = $2", errands.KIND, e["id"]) == 0
    # It cannot buy, and an unknown app is refused like an unknown site.
    r = await family.client.post("/v1/errands", headers=family.h("amma"),
                                 json={"service": "myclassboard", "kind": "booking", "title": "x", "spec": {"what": "fees", "max_amount": 100}})
    assert r.status_code == 422 and "never bought from" in r.text
    r = await family.client.post("/v1/errands", headers=family.h("amma"), json={"service": "whatsapp", "kind": "look", "title": "x", "spec": {"what": "x"}})
    assert r.status_code == 422
    assert errands.can_run("myclassboard")


class ScriptedApp:
    """A phone with the school's app on it, answering like the XCTest driver."""

    def __init__(self, driver_ref):
        self.driver_ref = driver_ref
        self.seen = []
        self.screen = "Home · Attendance · Announcements · Fees"

    async def send(self, message):
        self.seen.append(message)
        op = message["op"]
        if op == "click_text" and message["text"] == "Announcement":   # the tile's own word; the family's "Announcements" is the commit label
            self.screen = "Announcements · PTM on 18 October, 9 am · Diwali holidays 20 to 24 October · Science fair entries by 15 October"
        result = {"open": message.get("bundle"), "text": self.screen, "screenshot": "/9j/4AAQ", "click_text": op == "click_text", "close": None}[op]
        asyncio.get_running_loop().call_soon(self.driver_ref[0].answer, {"id": message["id"], "result": result})


async def test_the_phone_opens_the_app_reads_the_notices_and_hands_them_in(family, database):
    r = await family.client.post("/v1/errands", headers=family.h("amma"),
                                 json={"service": "myclassboard", "kind": "look", "title": "Read the school's notices", "spec": {"what": "Announcements"}})
    errand_id = uuid.UUID(r.json()["id"])
    ref = []
    scripted = ScriptedApp(ref)
    driver = phone.attach(errand_id, scripted.send)
    ref.append(driver)
    out = await errands.run_on_phone(_p(family), errand_id, driver)
    assert out["status"] == "done", out
    row = await database.fetchrow("SELECT status, outcome FROM errands WHERE id = $1", errand_id)
    assert row["status"] == "done"
    assert [m["op"] for m in scripted.seen] == ["open", "screenshot", "text", "click_text", "screenshot", "text", "screenshot", "close"]
    assert scripted.seen[0]["bundle"] == "com.myclassboard.commonParentPortal"
    assert row["outcome"]["committed"] == ["tap Announcements"] and row["outcome"]["run_on"] == "phone"
    # The words came in as Amma's private notice, from the app by name.
    shared = await database.fetchrow("SELECT visibility, submitted_by, channel FROM input_artifacts WHERE id = $1", uuid.UUID(row["outcome"]["shared"]))
    assert shared["visibility"] == "private" and shared["submitted_by"] == uuid.UUID(family.amma["id"])
    text = await database.fetchval("SELECT convert_from(b.data, 'UTF8') FROM artifact_blobs b JOIN input_artifacts a ON a.blob_id = b.id WHERE a.id = $1",
                                   uuid.UUID(row["outcome"]["shared"])) if await database.fetchval("SELECT to_regclass('artifact_blobs') IS NOT NULL") else None
    if text is not None:
        assert "PTM on 18 October" in text
    # The run's step pictures belong to the errand page: the Inbox never lists them.
    assert await database.fetchval("SELECT count(*) FROM input_artifacts WHERE channel = 'errand'") >= 1
    feed = (await family.client.get("/v1/inbox", headers=family.h("amma"))).json()
    assert all(r["channel"] != "errand" for r in feed)


class DrawnApp(ScriptedApp):
    """An app that draws its own screen: the tree says nothing, the picture says it all."""

    def __init__(self, driver_ref):
        super().__init__(driver_ref)
        self.screen = ""
        self.page = 0

    async def send(self, message):
        self.seen.append(message)
        op = message["op"]
        if op == "swipe":
            self.page += 1
        jpeg = JPEG_HEAD + bytes([self.page]) + b"\x00" * 40
        import base64
        result = {"open": message.get("bundle"), "text": "", "screenshot": base64.b64encode(jpeg).decode(), "swipe": True, "close": None}[op]
        asyncio.get_running_loop().call_soon(self.driver_ref[0].answer, {"id": message["id"], "result": result})


JPEG_HEAD = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00"


async def test_an_app_that_names_nothing_is_handed_in_as_pictures_one_per_screen(family, database, monkeypatch):
    monkeypatch.setattr(apps, "SETTLE_STEP", 0)
    r = await family.client.post("/v1/errands", headers=family.h("amma"),
                                 json={"service": "myclassboard", "kind": "look", "title": "Read the school's notices", "spec": {"what": "Announcements", "bundle": "com.mcb.aachiGlobal"}})
    errand_id = uuid.UUID(r.json()["id"])
    ref = []
    scripted = DrawnApp(ref)
    driver = phone.attach(errand_id, scripted.send)
    ref.append(driver)
    out = await errands.run_on_phone(_p(family), errand_id, driver)
    assert out["status"] == "done", out
    row = await database.fetchrow("SELECT status, outcome FROM errands WHERE id = $1", errand_id)
    assert scripted.seen[0]["bundle"] == "com.mcb.aachiGlobal"
    ops = [m["op"] for m in scripted.seen]
    assert ops.count("swipe") == 2 and ops.count("screenshot") >= 3 and "click_text" not in ops
    pictures = row["outcome"]["pictures"]
    assert len(pictures) == 3
    for pid in pictures:
        a = await database.fetchrow("SELECT visibility, media_type, submitted_by, note FROM input_artifacts WHERE id = $1", uuid.UUID(pid))
        assert a["visibility"] == "private" and a["media_type"] == "image/jpeg" and a["submitted_by"] == uuid.UUID(family.amma["id"])
        assert "taken by the phone" in a["note"]


class ColdApp(ScriptedApp):
    """The school app from a cold start: a splash that names nothing, then
    the list of children, then (one tap in) the child's home with its tabs.
    As seen on Arunmozhi's phone at 23:35 on 9 Oct 2026."""

    def __init__(self, driver_ref):
        super().__init__(driver_ref)
        self.reads = 0
        self.screen = ""

    async def send(self, message):
        self.seen.append(message)
        op = message["op"]
        if op == "text":
            self.reads += 1
            if self.reads == 3 and not self.screen:
                self.screen = "Aachi Global School · Older one · CIE 4-A · 25AAGS0132"
        if op == "click_text" and message["text"] == "Older":
            self.screen = "Open navigation menu · Attendance · Newsletter · Announcement 24 · Gallery · Circular"   # the tiles, as the phone read them
        if op == "click_text" and message["text"] == "Announcement":
            self.screen = "Announcements · PTM on 18 October, 9 am · Diwali holidays 20 to 24 October"
        result = {"open": message.get("bundle"), "text": self.screen, "screenshot": "/9j/4AAQ", "click_text": op == "click_text", "close": None}[op]
        asyncio.get_running_loop().call_soon(self.driver_ref[0].answer, {"id": message["id"], "result": result})


async def test_a_cold_start_waits_for_the_screen_then_picks_the_child_then_the_notices(family, database, monkeypatch):
    monkeypatch.setattr(apps, "SETTLE_STEP", 0)
    r = await family.client.post("/v1/errands", headers=family.h("amma"),
                                 json={"service": "myclassboard", "kind": "look", "title": "Read the school's notices", "spec": {"what": "Announcements", "bundle": "com.mcb.aachiGlobal"}})
    errand_id = uuid.UUID(r.json()["id"])
    ref = []
    scripted = ColdApp(ref)
    driver = phone.attach(errand_id, scripted.send)
    ref.append(driver)
    out = await errands.run_on_phone(_p(family), errand_id, driver)
    assert out["status"] == "done", out
    row = await database.fetchrow("SELECT status, outcome FROM errands WHERE id = $1", errand_id)
    # The splash was read past, not handed in as a picture; the child was picked by name, then the notices.
    assert row["outcome"]["committed"] == ["tap Older", "tap Announcements"]
    assert "pictures" not in row["outcome"] and row["outcome"]["characters"] > 20
    assert [m["text"] for m in scripted.seen if m["op"] == "click_text"] == ["Older", "Announcement"]


async def test_a_settled_screen_without_the_word_is_read_as_it_is(family, database, monkeypatch):
    """A screen that names things but none of them the notices, and no child
    of the household: read as it is after it stops changing, not after the
    whole wait."""
    monkeypatch.setattr(apps, "SETTLE_STEP", 0)
    r = await family.client.post("/v1/errands", headers=family.h("amma"),
                                 json={"service": "myclassboard", "kind": "look", "title": "Read the school's notices", "spec": {"what": "Announcements"}})
    errand_id = uuid.UUID(r.json()["id"])
    ref = []
    scripted = ScriptedApp(ref)
    scripted.screen = "Sign in · Mobile number · OTP · Terms of use and privacy policy"
    driver = phone.attach(errand_id, scripted.send)
    ref.append(driver)
    out = await errands.run_on_phone(_p(family), errand_id, driver)
    assert out["status"] == "done", out
    assert [m["op"] for m in scripted.seen].count("text") == 2 and "click_text" not in [m["op"] for m in scripted.seen]


async def test_an_app_errand_from_the_server_side_waits_for_the_phone(family, database):
    r = await family.client.post("/v1/errands", headers=family.h("amma"),
                                 json={"service": "iossettings", "kind": "look", "title": "trial", "spec": {"what": "General"}})
    row = dict(await pool().fetchrow("SELECT * FROM errands WHERE id = $1", uuid.UUID(r.json()["id"])))
    out = await apps.read_app(row)
    assert out["status"] == "needs_you" and "phone" in out["error"]
    assert await database.fetchval("SELECT status FROM errands WHERE id = $1", row["id"]) == "needs_you"


async def test_the_phone_driver_asks_the_phone_to_open_an_app():
    ref = []
    scripted = ScriptedApp(ref)
    driver = phone.attach(uuid.uuid4(), scripted.send)
    ref.append(driver)
    assert await driver.open("com.apple.Preferences") == "com.apple.Preferences"
    assert scripted.seen[0] == {**scripted.seen[0], "op": "open", "bundle": "com.apple.Preferences"}
    phone.detach(driver.errand_id)
