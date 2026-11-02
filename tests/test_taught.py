"""Teaching by showing: steps kept by their words, never a step that pays or submits, and a replay that stops instead of guessing."""
import json
import uuid

import pytest

from familyos import taught
from familyos.execution import screens
from familyos.identity import Invalid, Principal
from familyos.intake import gateway


class Phone:
    """A scripted app: screens, and which words open which."""

    def __init__(self, screens=None, start="home"):
        self.screens = screens or {
            "home": ("Hello\nAnnouncements\nFees\nPay now\nSign out", {"Announcements": "news", "Fees": "fees"}),
            "news": ("Circulars\nPTM on Friday at 4 pm, please attend with both parents.\nBack", {"Back": "home"}),
            "fees": ("Term 2 fee due 20 Oct\nBack", {"Back": "home"})}
        self.at, self.start, self.opened, self.taps = None, start, [], []

    async def open(self, bundle):
        self.opened.append(bundle)
        self.at = self.start
        return ""

    async def goto(self, url):
        self.opened.append(url)
        self.at = self.start

    async def text(self):
        return self.screens[self.at][0] if self.at else ""

    async def click_text(self, text):
        self.taps.append(text)
        nxt = self.screens[self.at][1].get(text)
        if nxt is None:
            return False
        self.at = nxt
        return True

    async def swipe(self, direction="up"):
        return False

    async def screenshot(self):
        return b"jpeg"


@pytest.fixture(autouse=True)
def _fast(monkeypatch):
    monkeypatch.setattr(screens, "SETTLE_STEP", 0)
    monkeypatch.setattr(screens, "SETTLE_READS", 2)
    taught._lessons.clear()


def _p(family, who="amma"):
    m = getattr(family, who)
    return Principal(member_id=uuid.UUID(m["id"]), household_id=uuid.UUID(family.household["id"]), role=m["role"], display_name=m["display_name"])


def _shares(monkeypatch):
    got = []

    async def share(p, **kw):
        got.append(kw)
        return {"artifact": {"id": str(uuid.uuid4())}}
    monkeypatch.setattr(gateway, "receive_share", share)
    return got


async def _teach(family, phone, steps):
    h = family.h("amma")
    r = await family.client.post("/v1/me/teach", headers=h, json={"kind": "phone", "target": "com.example.schoolapp"})
    assert r.status_code == 201, r.text
    lid = r.json()["id"]
    assert r.json()["connected"] is False
    taught._lessons[uuid.UUID(lid)]._driver = phone           # the phone driver joining
    out = (await family.client.post(f"/v1/me/teach/{lid}/step", headers=h, json={"op": "open"})).json()
    assert "Announcements" in out["labels"]
    for s in steps:
        r = await family.client.post(f"/v1/me/teach/{lid}/step", headers=h, json=s)
        assert r.status_code == 200, r.text
    return lid


async def test_show_it_once_then_it_does_it_again(family, monkeypatch):
    shares = _shares(monkeypatch)
    phone = Phone()
    lid = await _teach(family, phone, [{"op": "tap", "text": "Announcements"}, {"op": "read"}])
    h = family.h("amma")
    saved = (await family.client.post(f"/v1/me/teach/{lid}/save", headers=h, json={"title": "School announcements"})).json()
    assert [s["op"] for s in saved["steps"]] == ["tap", "read"] and saved["steps"][0]["text"] == "Announcements" and phone.opened == ["com.example.schoolapp"]
    assert (await family.client.get(f"/v1/me/teach/{lid}", headers=h)).status_code == 404     # the lesson is over

    skill = (await family.client.get("/v1/me/skills", headers=h)).json()[0]
    fresh = Phone()
    out = await taught.replay(_p(family), skill, fresh)
    assert out == {"status": "done", "handed_in": 1, "stopped": None} and fresh.taps == ["Announcements"]
    assert "PTM on Friday" in shares[-1]["text"] and shares[-1]["visibility"] == "private" and "School announcements" in shares[-1]["note"]
    assert (await family.client.get("/v1/me/skills", headers=h)).json()[0]["runs"] == 1


async def test_a_label_that_would_do_something_is_not_taught_and_not_offered(family, monkeypatch):
    phone = Phone()
    lid = await _teach(family, phone, [])
    h = family.h("amma")
    screen = (await family.client.get(f"/v1/me/teach/{lid}", headers=h)).json()
    assert "Pay now" not in screen["labels"] and "Sign out" not in screen["labels"] and set(screen["not_offered"]) == {"Pay now", "Sign out"}
    for label in ("Pay now", "Sign out", "Submit form", "delete"):
        r = await family.client.post(f"/v1/me/teach/{lid}/step", headers=h, json={"op": "tap", "text": label})
        assert r.status_code in (400, 422), label
    assert phone.taps == []                                                                    # nothing was pressed
    assert (await family.client.post(f"/v1/me/teach/{lid}/step", headers=h, json={"op": "type", "text": "x"})).status_code in (400, 422)


async def test_a_skill_needs_a_read_and_a_tap_that_misses_is_not_kept(family):
    phone = Phone()
    lid = await _teach(family, phone, [{"op": "tap", "text": "Fees"}])
    h = family.h("amma")
    assert (await family.client.post(f"/v1/me/teach/{lid}/save", headers=h, json={"title": "No read"})).status_code in (400, 422)
    miss = await family.client.post(f"/v1/me/teach/{lid}/step", headers=h, json={"op": "tap", "text": "Gallery"})
    assert miss.status_code in (400, 422) and "could not find" in miss.text
    undone = (await family.client.post(f"/v1/me/teach/{lid}/undo", headers=h)).json()
    assert undone["steps"] == []


async def test_a_replay_stops_where_the_words_are_gone_and_a_tampered_skill_is_refused(family, monkeypatch):
    shares = _shares(monkeypatch)
    skill = {"id": uuid.uuid4(), "title": "t", "kind": "phone", "target": "com.example.schoolapp", "steps": [{"op": "tap", "text": "Gallery"}, {"op": "read"}]}
    await _insert(family, skill)
    out = await taught.replay(_p(family), skill, Phone())
    assert out["status"] == "needs_you" and "“Gallery” is not on the screen" in out["stopped"] and shares == []
    evil = {**skill, "id": uuid.uuid4(), "steps": [{"op": "tap", "text": "Pay now"}, {"op": "read"}]}
    await _insert(family, evil)
    phone = Phone()
    out = await taught.replay(_p(family), evil, phone)
    assert out["status"] == "needs_you" and phone.taps == []


async def _insert(family, skill):
    from familyos.db import pool
    await pool().execute("INSERT INTO taught_skills (id, household_id, member_id, title, kind, target, steps) VALUES ($1, $2, $3, 't', $4, $5, $6::jsonb)",
                         skill["id"], uuid.UUID(family.household["id"]), uuid.UUID(family.amma["id"]), skill["kind"], skill["target"], json.dumps(skill["steps"]))


async def test_a_web_lesson_and_run_use_a_browser_that_is_released(family, monkeypatch):
    shares = _shares(monkeypatch)
    released = []

    async def browser(url):
        async def release():
            released.append(url)
        return Phone(), release
    monkeypatch.setattr(taught, "web_browser", browser)
    h = family.h("amma")
    r = await family.client.post("/v1/me/teach", headers=h, json={"kind": "web", "target": "https://school.example.com/news"})
    assert r.status_code == 201 and r.json()["connected"] is True
    lid = r.json()["id"]
    await family.client.post(f"/v1/me/teach/{lid}/step", headers=h, json={"op": "tap", "text": "Announcements"})
    await family.client.post(f"/v1/me/teach/{lid}/step", headers=h, json={"op": "read"})
    sid = (await family.client.post(f"/v1/me/teach/{lid}/save", headers=h, json={"title": "School site"})).json()["id"]
    assert released == ["https://school.example.com/news"]
    out = (await family.client.post(f"/v1/me/skills/{sid}/run", headers=h)).json()
    assert out["status"] == "done" and out["handed_in"] == 1 and len(released) == 2 and "PTM" in shares[-1]["text"]
    assert (await family.client.delete(f"/v1/me/skills/{sid}", headers=h)).status_code == 204
    assert (await family.client.get("/v1/me/skills", headers=h)).json() == []


async def test_lessons_are_private_and_children_do_not_teach(family):
    h = family.h("amma")
    lid = (await family.client.post("/v1/me/teach", headers=h, json={"kind": "phone", "target": "com.example.schoolapp"})).json()["id"]
    assert (await family.client.get(f"/v1/me/teach/{lid}", headers=family.h("paati"))).status_code == 404
    assert (await family.client.post("/v1/me/teach", headers=h, json={"kind": "phone", "target": "not a bundle"})).status_code in (400, 422)
    assert (await family.client.post("/v1/me/teach", headers=h, json={"kind": "web", "target": "http://school.example.com"})).status_code in (400, 422)
    kid = Principal(member_id=uuid.UUID(family.younger["id"]), household_id=uuid.UUID(family.household["id"]), role="child", display_name="Younger one")
    with pytest.raises(Exception, match="children"):
        await taught.start(kid, "phone", "com.example.schoolapp")
    with pytest.raises(Invalid):
        taught.clean_steps("phone", "com.example.schoolapp", [{"op": "tap", "text": "Fees"}])


# --- the phone driver taps one exact label, and the lesson lifecycle does not leak -------------------------------------------

class _Ask:
    """A PhoneDriver whose phone answers click_text with a fixed reply."""

    def __init__(self, reply):
        import asyncio

        from familyos.execution import phone as ph
        self.sent = []

        async def send(message):
            self.sent.append(message)
            asyncio.get_running_loop().call_soon(self.driver.answer, {"id": message["id"], "result": reply})
        self.driver = ph.PhoneDriver(uuid.uuid4(), send)


async def test_the_phone_driver_asks_for_the_whole_label_and_refuses_zero_or_many():
    from familyos.execution import phone as ph
    one = _Ask({"tapped": True, "matches": 1})
    assert await one.driver.click_text("  Term 2   Fees ") is True
    assert one.sent[0]["text"] == "Term 2 Fees"                                  # whitespace folded before it is asked
    none = _Ask({"tapped": False, "matches": 0})
    assert await none.driver.click_text("Gallery") is False
    many = _Ask({"tapped": False, "matches": 2})
    with pytest.raises(ph.TapRefused, match="2 things on the screen are labelled “Fees”"):
        await many.driver.click_text("Fees")
    assert await _Ask(True).driver.click_text("Fees") is True                    # the web view's plain answer still works


async def test_a_taught_tap_on_an_ambiguous_label_is_refused_clearly(family):
    from familyos.execution import phone as ph
    phone = Phone()

    async def refuse(text):
        raise ph.TapRefused("2 things on the screen are labelled “Fees”; not tapping a guess")
    lid = await _teach(family, phone, [])
    phone.click_text = refuse
    r = await family.client.post(f"/v1/me/teach/{lid}/step", headers=family.h("amma"), json={"op": "tap", "text": "Fees"})
    assert r.status_code in (400, 422) and "2 things on the screen" in r.text
    assert (await family.client.get(f"/v1/me/teach/{lid}", headers=family.h("amma"))).json()["steps"] == []


async def test_a_replay_stops_on_an_ambiguous_label_and_says_so(family):
    from familyos.execution import phone as ph
    skill = {"id": uuid.uuid4(), "title": "t", "kind": "phone", "target": "com.example.schoolapp", "steps": [{"op": "tap", "text": "Fees"}, {"op": "read"}]}
    await _insert(family, skill)
    phone = Phone()

    async def refuse(text):
        raise ph.TapRefused("2 things on the screen are labelled “Fees”; not tapping a guess")
    phone.click_text = refuse
    out = await taught.replay(_p(family), skill, phone)
    assert out["status"] == "needs_you" and out["stopped"].startswith("step 1: 2 things on the screen")


class _Browser(Phone):
    def __init__(self, fail_goto=False):
        super().__init__()
        self.fail_goto = fail_goto

    async def goto(self, url):
        if self.fail_goto:
            raise RuntimeError("the page never loaded")
        await super().goto(url)


async def test_a_lesson_whose_first_page_fails_is_unregistered_and_its_browser_released_once(family):
    released = []

    async def release():
        released.append(1)
    with pytest.raises(RuntimeError):
        await taught.start(_p(family), "web", "https://school.example.com/news", driver=_Browser(fail_goto=True), release=release)
    assert taught._lessons == {} and released == [1]


async def test_a_refused_start_still_releases_the_browser(family):
    released = []

    async def release():
        released.append(1)
    kid = Principal(member_id=uuid.UUID(family.younger["id"]), household_id=uuid.UUID(family.household["id"]), role="child", display_name="Noah")
    with pytest.raises(Exception, match="children"):
        await taught.start(kid, "web", "https://school.example.com/news", driver=_Browser(), release=release)
    assert released == [1] and taught._lessons == {}


async def test_a_lesson_is_registered_before_the_first_page_loads(family):
    seen = []

    class Watching(_Browser):
        async def goto(self, url):
            seen.append(len(taught._lessons))
            await super().goto(url)
    await taught.start(_p(family), "web", "https://school.example.com/news", driver=Watching(), release=None)
    assert seen == [1]


async def test_the_sweep_ends_an_expired_lesson_and_releases_its_browser_and_ending_twice_releases_once(family):
    released = []

    async def release():
        released.append(1)
    screen = await taught.start(_p(family), "web", "https://school.example.com/news", driver=_Browser(), release=release)
    lesson = taught._lessons[screen["id"]]
    assert await taught.expire_stale() == 0 and released == []                    # still fresh
    lesson.started -= (taught.LESSON_MINUTES + 1) * 60
    with pytest.raises(Exception, match="lesson"):
        await taught.show(_p(family), screen["id"])                              # an expired lesson is not usable even before the sweep
    assert await taught.expire_stale() == 1 and released == [1] and taught._lessons == {}
    await lesson.end()
    assert released == [1]


async def test_an_expired_lesson_does_not_count_against_the_limit(family):
    for _ in range(taught.MAX_LESSONS):
        await taught.start(_p(family), "phone", "com.example.schoolapp")
    for lesson in taught._lessons.values():
        lesson.started -= (taught.LESSON_MINUTES + 1) * 60
    await taught.start(_p(family), "phone", "com.example.schoolapp")
    assert len(taught._lessons) == 1
