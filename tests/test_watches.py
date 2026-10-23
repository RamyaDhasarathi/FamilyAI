"""The generic task, in the shape that costs the architecture nothing."""
import uuid

import httpx
import pytest

from familyos import watches
from familyos.execution import disposable
from familyos.identity import Invalid, Principal
from familyos.settings import settings

PAGE = ("<html><head><title>Cool Air 1.5T Inverter AC</title></head>"
        "<body><h1>Cool Air 1.5T</h1><p>Currently <b>in stock</b> at 32,990.</p></body></html>")
GONE = ("<html><head><title>Cool Air 1.5T Inverter AC</title></head>"
        "<body><h1>Cool Air 1.5T</h1><p>Currently out of stock.</p></body></html>")


def _principal(family, who="amma"):
    m = getattr(family, who)
    return Principal(member_id=uuid.UUID(m["id"]), household_id=uuid.UUID(family.household["id"]),
                     role=m["role"], display_name=m["display_name"])


def _client(pages):
    """A transport that serves canned pages and records nothing else."""
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        body = pages.get(str(request.url))
        if body is None:
            return httpx.Response(404)
        if isinstance(body, tuple):
            return httpx.Response(body[0], headers={"location": body[1]})
        return httpx.Response(200, text=body)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler), follow_redirects=False)
    client.seen = seen
    return client


@pytest.fixture
def sent(monkeypatch):
    out = []

    async def fake(to, subject, body, *, ics=None):
        out.append({"to": to, "subject": subject, "body": body})

    from familyos import mail
    monkeypatch.setattr(mail, "send", fake)
    monkeypatch.setattr(mail, "configured", lambda: True)
    monkeypatch.setattr(settings, "watches_enabled", True)
    return out


# ----------------------------------------------------------------------------
# class 1: what it refuses before it fetches anything
# ----------------------------------------------------------------------------

def test_only_https_and_only_named_public_hosts():
    allow = frozenset({"example.com"})
    for bad in ("http://example.com/x",          # not https
                "https://other.example.com/x",        # outside the grant
                "https://127.0.0.1/x",                # an address, not a source
                "https://169.254.169.254/latest/"):   # the metadata endpoint
        with pytest.raises(disposable.Refused):
            disposable.approved(bad, allow)
    assert disposable.approved("https://example.com/ac", allow)


async def test_a_hostname_that_resolves_inside_the_network_is_refused(monkeypatch):
    """Checking the literal is not enough: a name an attacker controls can
    point at loopback or at the metadata address. Caught at fetch time, after
    the syntactic check passes."""
    import socket
    url = "https://example.com/x"
    allow = frozenset({"example.com"})
    assert disposable.approved(url, allow)  # syntactically fine
    monkeypatch.setattr(socket, "getaddrinfo",
                        lambda *a, **kw: [(2, 1, 6, "", ("169.254.169.254", 443))])
    client = _client({url: PAGE})
    with pytest.raises(disposable.Refused):
        await disposable.read(url, allow, client=client)
    await client.aclose()


async def test_a_redirect_off_the_allowlist_is_refused():
    url = "https://example.com/ac"
    client = _client({url: (302, "https://elsewhere.example.com/ac")})
    with pytest.raises(disposable.Refused):
        await disposable.read(url, frozenset({"example.com"}), client=client)
    await client.aclose()


async def test_a_page_comes_back_as_evidence_with_a_hash():
    url = "https://example.com/ac"
    client = _client({url: PAGE})
    page = await disposable.read(url, frozenset({"example.com"}), client=client)
    await client.aclose()
    assert page.title == "Cool Air 1.5T Inverter AC"
    assert "in stock" in page.text
    assert "<b>" not in page.text and len(page.sha256) == 64


# ----------------------------------------------------------------------------
# the watch
# ----------------------------------------------------------------------------

async def test_it_says_nothing_on_the_first_look_and_speaks_when_it_changes(family, database, sent):
    url = "https://example.com/ac"
    w = await watches.create(_principal(family), url=url, look_for="in stock",
                             label="Cool Air 1.5T AC")

    rows = await watches.due()
    client = _client({url: GONE})
    assert await watches.check_one(rows[0], client=client) == "same"   # nothing to compare to
    await client.aclose()
    assert sent == []

    rows = await watches.due(limit=20)
    row = next(r for r in await database.fetch(
        "SELECT w.*, m.email, m.display_name FROM watches w JOIN members m ON m.id = w.member_id "
        "WHERE w.id = $1", w["id"]))
    client = _client({url: PAGE})
    assert await watches.check_one(dict(row), client=client) == "notified"
    await client.aclose()

    assert sent[0]["to"] == family.amma["email"]
    assert "Cool Air 1.5T AC: found" == sent[0]["subject"]
    assert "in stock" in sent[0]["body"]
    # It says plainly what it did not do.
    assert "did not sign in, buy anything, or act on your behalf" in sent[0]["body"]


async def test_an_unreadable_page_records_why_and_does_not_shout(family, database, sent):
    url = "https://example.com/ac"
    await watches.create(_principal(family), url=url, look_for="in stock", label="AC")
    client = _client({})  # 404
    assert await watches.check_one((await watches.due())[0], client=client) == "failed"
    await client.aclose()
    assert sent == []
    assert "404" in await database.fetchval("SELECT last_error FROM watches")


async def test_a_watch_belongs_to_the_member_who_asked(family, database, sent):
    await watches.create(_principal(family), url="https://example.com/ac",
                         look_for="in stock", label="AC")
    assert len(await watches.list_for(_principal(family))) == 1
    assert await watches.list_for(_principal(family, "appa")) == []


async def test_a_watch_is_checked_against_its_grant_when_it_is_made(family):
    for bad in ({"url": "http://example.com/ac"},
                {"url": "https://127.0.0.1/ac"}):
        with pytest.raises((Invalid, disposable.Refused)):
            await watches.create(_principal(family), look_for="x", label="x", **bad)


async def test_a_watch_needs_words_a_name_and_a_sane_schedule(family):
    me = _principal(family)
    url = "https://example.com/ac"
    for bad in ({"look_for": "  ", "label": "x"},
                {"look_for": "x", "label": "  "},
                {"look_for": "x", "label": "x", "every_hours": 0},
                {"look_for": "x", "label": "x", "days": 999}):
        with pytest.raises(Invalid):
            await watches.create(me, url=url, **bad)


async def test_the_sweep_is_off_unless_turned_on(family, database, monkeypatch):
    await watches.create(_principal(family), url="https://example.com/ac",
                         look_for="in stock", label="AC")
    monkeypatch.setattr(settings, "watches_enabled", False)
    assert await watches.sweep() == {"notified": 0, "same": 0, "failed": 0}
    assert "off" in watches.describe()


async def test_the_whole_thing_over_http(family, sent):
    r = await family.client.post("/v1/watches", headers=family.h("amma"), json={
        "url": "https://example.com/ac", "look_for": "in stock",
        "label": "Cool Air 1.5T AC", "every_hours": 6})
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["label"] == "Cool Air 1.5T AC" and body["last_checked_at"] is None

    listed = await family.client.get("/v1/watches", headers=family.h("amma"))
    assert [w["id"] for w in listed.json()] == [body["id"]]

    stopped = await family.client.delete(f"/v1/watches/{body['id']}", headers=family.h("amma"))
    assert stopped.status_code == 200
    assert (await family.client.get("/v1/watches", headers=family.h("amma"))).json()[0]["paused_at"] is not None


async def test_a_name_that_points_inside_is_refused_at_creation_not_at_fetch(family):
    """Found live: https://localhost/ was accepted and created a watch that
    could only ever fail. "localhost" is not an address literal, so every
    syntactic check passes it."""
    with pytest.raises(disposable.Refused):
        await watches.create(_principal(family), url="https://localhost/",
                             look_for="x", label="probe")
    assert await watches.list_for(_principal(family)) == []


async def test_a_refused_url_is_the_callers_fault_not_a_server_error(family):
    """Found live: these produced bare 500s, so the reason never reached anyone."""
    for url in ("http://example.com/", "https://169.254.169.254/latest/", "https://localhost/"):
        r = await family.client.post("/v1/watches", headers=family.h("amma"), json={
            "url": url, "look_for": "x", "label": "probe"})
        assert r.status_code == 422, f"{url} -> {r.status_code}"
        assert r.json()["error"] in ("refused", "invalid")
