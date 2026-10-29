"""One sitting, a person present, nothing kept afterwards but what they picked."""
import uuid

import pytest

from familyos.execution import disposable, harvest, sessions
from familyos.identity import Invalid, NotFound, Principal

HOSTS = ["portal.example.com"]


def _principal(family, who="amma"):
    m = getattr(family, who)
    return Principal(member_id=uuid.UUID(m["id"]), household_id=uuid.UUID(family.household["id"]),
                     role=m["role"], display_name=m["display_name"])


def _page(path="/circulars/1", title="Circular 1", text="Sports day on 14 November."):
    body = text.encode()
    import hashlib
    return disposable.Page(url=f"https://portal.example.com{path}", title=title, text=text,
                           sha256=hashlib.sha256(body).hexdigest(), bytes=len(body), truncated=False)


async def _sitting(family, who="amma"):
    return await harvest.begin(_principal(family, who), label="School portal backfill", allow_hosts=HOSTS)


# ----------------------------------------------------------------------------
# the rule this exists to keep
# ----------------------------------------------------------------------------

async def test_a_harvest_never_stores_a_session(family, database):
    """The whole point. Class 2 leaves a live credential in custody; a sitting
    leaves nothing at all."""
    h = await _sitting(family)
    await harvest.offer(_principal(family), h["id"], _page())
    await harvest.keep(_principal(family), (await harvest.candidates(_principal(family), h["id"]))[0]["id"])
    await harvest.finish(_principal(family), h["id"])

    assert await database.fetchval("SELECT count(*) FROM sealed_sessions") == 0
    assert await sessions.list_for(_principal(family)) == []


async def test_nothing_enters_the_record_until_a_person_picks_it(family, database):
    h = await _sitting(family)
    await harvest.offer(_principal(family), h["id"], _page())
    await harvest.offer(_principal(family), h["id"], _page("/circulars/2", "Circular 2", "Fee due 20 Nov."))

    # Collected, and nothing is an artifact yet.
    assert len(await harvest.candidates(_principal(family), h["id"])) == 2
    assert await database.fetchval("SELECT count(*) FROM input_artifacts") == 0

    picked = (await harvest.candidates(_principal(family), h["id"]))[0]
    artifact = await harvest.keep(_principal(family), picked["id"])
    assert artifact["channel"] == "harvest" and artifact["visibility"] == "private"
    assert await database.fetchval("SELECT count(*) FROM input_artifacts") == 1


async def test_what_is_not_picked_is_gone_when_the_sitting_ends(family, database):
    h = await _sitting(family)
    await harvest.offer(_principal(family), h["id"], _page())
    await harvest.offer(_principal(family), h["id"], _page("/c/2", "Two", "Nothing useful."))
    kept = (await harvest.candidates(_principal(family), h["id"]))[0]
    await harvest.keep(_principal(family), kept["id"])

    await harvest.finish(_principal(family), h["id"])
    left = await database.fetch("SELECT decision FROM harvest_candidates")
    assert [r["decision"] for r in left] == ["kept"]
    assert await database.fetchval("SELECT state FROM harvests") == "done"


# ----------------------------------------------------------------------------
# what a candidate is, and is not
# ----------------------------------------------------------------------------

async def test_a_candidate_is_sealed_with_the_members_own_key(family, database):
    h = await _sitting(family)
    await harvest.offer(_principal(family), h["id"], _page(text="Sports day on 14 November."))
    raw = await database.fetchval("SELECT sealed_text FROM harvest_candidates")
    assert b"Sports day" not in raw

    # And the member reading their own sitting sees it plainly.
    [seen] = await harvest.candidates(_principal(family), h["id"])
    assert seen["text"] == "Sports day on 14 November."
    assert seen["sealed_text"] is None


async def test_another_member_cannot_read_the_sitting(family, database):
    h = await _sitting(family, "amma")
    await harvest.offer(_principal(family, "amma"), h["id"], _page())
    with pytest.raises(NotFound):
        await harvest.candidates(_principal(family, "appa"), h["id"])


async def test_a_page_outside_the_grant_is_refused(family):
    h = await _sitting(family)
    stray = _page()
    stray = disposable.Page(url="https://elsewhere.example.com/x", title=stray.title, text=stray.text,
                            sha256=stray.sha256, bytes=stray.bytes, truncated=False)
    with pytest.raises(disposable.Refused):
        await harvest.offer(_principal(family), h["id"], stray)


async def test_the_same_page_twice_is_one_candidate(family, database):
    h = await _sitting(family)
    first = await harvest.offer(_principal(family), h["id"], _page())
    again = await harvest.offer(_principal(family), h["id"], _page())
    assert first["id"] == again["id"]
    assert await database.fetchval("SELECT count(*) FROM harvest_candidates") == 1


async def test_discarding_a_candidate_destroys_what_it_held(family, database):
    h = await _sitting(family)
    c = await harvest.offer(_principal(family), h["id"], _page(text="Something private."))
    await harvest.discard(_principal(family), c["id"])
    row = await database.fetchrow("SELECT decision, sealed_text FROM harvest_candidates")
    assert row["decision"] == "discarded"
    assert row["sealed_text"] == b"\x00"


# ----------------------------------------------------------------------------
# a sitting ends
# ----------------------------------------------------------------------------

async def test_an_expired_sitting_takes_no_more_and_is_swept(family, database):
    h = await _sitting(family)
    await harvest.offer(_principal(family), h["id"], _page())
    await database.execute("UPDATE harvests SET expires_at = NOW() - interval '1 minute' WHERE id = $1", h["id"])

    with pytest.raises(harvest.HarvestClosed):
        await harvest.offer(_principal(family), h["id"], _page("/c/9", "Nine", "Late."))

    assert await harvest.sweep() == {"abandoned": 1, "dropped": 1}
    assert await database.fetchval("SELECT state FROM harvests") == "abandoned"
    assert await database.fetchval("SELECT count(*) FROM harvest_candidates") == 0


async def test_a_finished_sitting_cannot_be_reopened(family):
    h = await _sitting(family)
    await harvest.finish(_principal(family), h["id"])
    with pytest.raises(harvest.HarvestClosed):
        await harvest.offer(_principal(family), h["id"], _page())


async def test_a_sitting_needs_a_name_a_site_and_a_sane_length(family):
    me = _principal(family)
    for bad in ({"label": "  ", "allow_hosts": HOSTS},
                {"label": "x", "allow_hosts": []},
                {"label": "x", "allow_hosts": HOSTS, "minutes": 0},
                {"label": "x", "allow_hosts": HOSTS, "minutes": 999},
                {"label": "x", "allow_hosts": ["127.0.0.1"]}):
        with pytest.raises((Invalid, disposable.Refused)):
            await harvest.begin(me, **bad)


async def test_the_whole_sitting_over_http(family):
    begun = await family.client.post("/v1/harvests", headers=family.h("amma"), json={
        "label": "School portal backfill", "allow_hosts": HOSTS, "minutes": 60})
    assert begun.status_code == 201, begun.text
    h = begun.json()
    assert h["state"] == "collecting"

    # Pages arrive from the driver, not over HTTP: a member does not get to
    # assert what a page said.
    await harvest.offer(_principal(family), uuid.UUID(h["id"]), _page())

    listed = await family.client.get(f"/v1/harvests/{h['id']}/candidates", headers=family.h("amma"))
    assert listed.status_code == 200
    [c] = listed.json()
    assert c["text"] == "Sports day on 14 November." and c["decision"] is None

    kept = await family.client.post(f"/v1/harvest-candidates/{c['id']}/keep", headers=family.h("amma"))
    assert kept.status_code == 201, kept.text
    assert kept.json()["channel"] == "harvest"

    done = await family.client.post(f"/v1/harvests/{h['id']}/finish", headers=family.h("amma"))
    assert done.status_code == 200 and done.json()["state"] == "done"


# ----------------------------------------------------------------------------
# the browser behind it
# ----------------------------------------------------------------------------

def test_a_bind_address_is_rewritten_to_somewhere_a_browser_can_go():
    """Steel reports its own URLs as 0.0.0.0, which no browser can open."""
    from familyos.execution.steel import _reachable
    assert _reachable("http://0.0.0.0:3000/v1/devtools/inspector.html",
                      "http://localhost:3000") == "http://localhost:3000/v1/devtools/inspector.html"
    # The port Steel named is kept: the DevTools frontend is on another one.
    assert _reachable("http://0.0.0.0:9223/devtools/devtools_app.html",
                      "http://localhost:3000") == "http://localhost:9223/devtools/devtools_app.html"
    # And the websocket in the query, which fails just as silently in a frame.
    assert _reachable("http://0.0.0.0:9223/x?ws=//0.0.0.0:9223/devtools/page/A",
                      "http://steel.lan:3000") == "http://steel.lan:9223/x?ws=//steel.lan:9223/devtools/page/A"
    # Anything already reachable is left exactly as it is.
    assert _reachable("https://steel.internal/x", "http://localhost:3000") == "https://steel.internal/x"
    assert _reachable(None, "http://localhost:3000") is None


async def test_a_sitting_carries_the_live_view_its_browser_gave_it(family, database):
    class FakeSteel:
        async def open(self, *, allow_hosts, minutes):
            return {"session_id": "s-1", "live_url": "http://localhost:3000/v1/devtools/inspector.html"}

        async def close(self, session):
            return None

    harvest.use_collector(FakeSteel())
    try:
        h = await _sitting(family)
        assert h["live_url"].endswith("/inspector.html")
    finally:
        harvest.use_collector(harvest.ManualCollector())


async def test_without_a_browser_a_sitting_still_works_and_says_so(family):
    """Pages handed in by some other means is a real mode, not a failure."""
    h = await _sitting(family)
    assert h["live_url"] is None
    assert "handed in" in harvest.describe()


async def test_the_live_view_follows_the_inspectors_redirect():
    """Found by looking at it: the inspector is a 302 to the DevTools frontend
    on another port, so a frame pointed at the inspector shows "0.0.0.0 refused
    to connect" and nothing else."""
    import httpx

    from familyos.execution.steel import SteelCollector

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v1/sessions":
            return httpx.Response(200, json={
                "id": "s-1", "debuggerUrl": "http://0.0.0.0:3000/v1/devtools/inspector.html",
                "websocketUrl": "ws://0.0.0.0:3000/"})
        if request.url.path == "/v1/devtools/inspector.html":
            return httpx.Response(302, headers={
                "location": "http://0.0.0.0:9223/devtools/devtools_app.html?ws=//0.0.0.0:9223/devtools/page/A"})
        return httpx.Response(404)

    transport = httpx.MockTransport(handler)
    real = httpx.AsyncClient

    class Patched(real):
        def __init__(self, *a, **kw):
            kw["transport"] = transport
            super().__init__(*a, **kw)

    httpx.AsyncClient = Patched
    try:
        opened = await SteelCollector("http://localhost:3000").open(
            allow_hosts=frozenset({"x.example.com"}), minutes=5)
    finally:
        httpx.AsyncClient = real

    assert opened["live_url"] == (
        "http://localhost:9223/devtools/devtools_app.html?ws=//localhost:9223/devtools/page/A")


async def test_a_second_sitting_is_refused_rather_than_evicting_the_first(family, database):
    """Steel's single container replaces a live session when a second is asked
    for: the first member's view dies silently and their browser is still
    signed in to whatever it was. Refusing is the honest behaviour."""
    class OneAtATime:
        async def open(self, *, allow_hosts, minutes):
            return {"session_id": "s-1", "live_url": "http://localhost:9223/x"}

        async def close(self, session):
            return None

    harvest.use_collector(OneAtATime())
    try:
        await _sitting(family, "amma")
        with pytest.raises(harvest.Busy):
            await harvest.begin(_principal(family, "appa"), label="Another", allow_hosts=HOSTS)
    finally:
        harvest.use_collector(harvest.ManualCollector())


async def test_without_a_browser_sittings_do_not_contend(family):
    """Manual sittings hold no browser, so there is nothing to collide over."""
    await _sitting(family, "amma")
    assert await harvest.begin(_principal(family, "appa"), label="Another", allow_hosts=HOSTS)
