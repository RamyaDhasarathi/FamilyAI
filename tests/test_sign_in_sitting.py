"""The sign-in sitting: the member signs in themselves in a browser they
watch; what the browser holds for the site is sealed as a class-2 session;
the browser is released. No password passes through FamilyOS."""
import uuid

import pytest

from familyos.execution import sessions, steel
from familyos.identity import Principal


class FakeBrowser:
    """Steel, as far as a sitting cares: opens on a page, holds what the person
    does, can be read, is released."""

    def __init__(self):
        self.opened_at, self.released = [], []
        self.held = {"cookies": [], "localStorage": {}, "sessionStorage": {}}

    async def open_at(self, url, *, minutes):
        self.opened_at.append(url)
        return {"session_id": "steel-1", "live_url": "http://localhost:3000/devtools/inspector.html?ws=x",
                "websocket_url": "ws://localhost:3000/", "user_agent": "Mozilla/5.0 (X11) Chrome/145",
                "dimensions": {"width": 1280, "height": 800}}

    async def open_with(self, context, *, user_agent, minutes):
        self.opened_with = (context, user_agent)
        return {"session_id": "steel-2", "websocket_url": "ws://localhost:3000/", "user_agent": user_agent}

    async def context(self, session_id):
        return self.held

    async def release(self, session_id):
        self.released.append(session_id)


@pytest.fixture
def browser():
    fake = FakeBrowser()
    steel.use_browser(fake)
    yield fake
    steel.use_browser(steel.NoBrowser())


def _p(family, who="amma"):
    m = getattr(family, who)
    return Principal(member_id=uuid.UUID(m["id"]), household_id=uuid.UUID(family.household["id"]),
                     role=m["role"], display_name=m["display_name"])


async def test_a_sitting_opens_on_the_sites_sign_in_page_and_says_how(family, database, browser):
    r = await family.client.get("/v1/sites", headers=family.h("amma"))
    assert [x["service"] for x in r.json()] == ["urbancompany"]
    r = await family.client.post("/v1/sign-ins", headers=family.h("amma"), json={"service": "urbancompany"})
    assert r.status_code == 201, r.text
    s = r.json()
    assert s["label"] == "Urban Company" and "OTP" in s["how"] and s["live_url"].startswith("http://localhost:3000/")
    assert s["ws_url"] == "ws://localhost:3000/"
    assert browser.opened_at == ["https://www.urbancompany.com/"]
    assert (await family.client.get("/v1/sign-ins/open", headers=family.h("amma"))).json()["id"] == s["id"]
    # One browser, one sitting: a second is refused with a sentence.
    r = await family.client.post("/v1/sign-ins", headers=family.h("appa"), json={"service": "urbancompany"})
    assert r.status_code == 422 and "already open" in r.text
    r = await family.client.delete(f"/v1/sign-ins/{s['id']}", headers=family.h("amma"))
    assert r.status_code == 204 and browser.released == ["steel-1"]
    # A site off the list cannot be signed in to.
    r = await family.client.post("/v1/sign-ins", headers=family.h("amma"), json={"service": "bank"})
    assert r.status_code == 422 and "not one FamilyOS can sign in to" in r.text


async def test_sealing_before_signing_in_stores_nothing_and_after_it_seals_only_the_sites_own_state(family, database, browser):
    s = (await family.client.post("/v1/sign-ins", headers=family.h("amma"), json={"service": "urbancompany"})).json()
    r = await family.client.post(f"/v1/sign-ins/{s['id']}/seal", headers=family.h("amma"))
    assert r.status_code == 422 and "not signed in" in r.text
    assert await database.fetchval("SELECT count(*) FROM sealed_sessions") == 0
    # The person signs in: the browser now holds the site's cookies, plus a tracker's.
    # Half-way -- a city cookie but no sign-in -- is still "not signed in".
    browser.held = {"cookies": [{"name": "currentCity", "value": "bengaluru", "domain": "www.urbancompany.com"}], "localStorage": {}, "sessionStorage": {}}
    r = await family.client.post(f"/v1/sign-ins/{s['id']}/seal", headers=family.h("amma"))
    assert r.status_code == 422 and "finish the OTP step" in r.text
    browser.held = {"cookies": [{"name": "_uc_user_token", "value": "SECRET-TOKEN-9", "domain": "www.urbancompany.com"},
                                {"name": "_ga", "value": "GA1.2", "domain": ".google-analytics.com"}],
                    "localStorage": {"https://www.urbancompany.com": {"auth": "SECRET-LS-1"}, "https://cdn.other.com": {"x": "1"}},
                    "sessionStorage": {}, "userAgent": "Mozilla/5.0 (X11) Chrome/145"}
    r = await family.client.post(f"/v1/sign-ins/{s['id']}/seal", headers=family.h("amma"))
    assert r.status_code == 200, r.text
    assert r.json()["service"] == "urbancompany" and r.json()["label"] == "Urban Company" and "secret" not in r.text.lower()
    assert browser.released == ["steel-1"]
    # Sealed: nothing readable in the row; opened for a task, only the site's own state is there.
    raw = await database.fetchval("SELECT sealed_state FROM sealed_sessions")
    assert b"SECRET-TOKEN-9" not in raw and b"SECRET-LS-1" not in raw
    async with sessions.lease(_p(family), "urbancompany", reason="book a clean") as held:
        assert [c["name"] for c in held.state.cookies] == ["_uc_user_token"]
        assert list(held.state.storage["localStorage"]) == ["https://www.urbancompany.com"]
        assert held.state.fingerprint["user_agent"].startswith("Mozilla")
        assert held.state.as_browser_context()["localStorage"]["https://www.urbancompany.com"]["auth"] == "SECRET-LS-1"
        assert held.allow_hosts == frozenset({"www.urbancompany.com", "urbancompany.com"})
    # Listed by name and dates only; signed out, it is gone.
    listed = (await family.client.get("/v1/signed-in", headers=family.h("amma"))).json()
    assert [x["label"] for x in listed] == ["Urban Company"] and listed[0]["uses"] == 1 and "cookies" not in listed[0]
    assert (await family.client.get("/v1/signed-in", headers=family.h("appa"))).json() == []
    r = await family.client.delete(f"/v1/signed-in/{listed[0]['id']}", headers=family.h("amma"))
    assert r.status_code == 204
    with pytest.raises(sessions.SessionLapsed):
        async with sessions.lease(_p(family), "urbancompany", reason="again"):
            pass
    assert (await family.client.get("/v1/sign-ins/open", headers=family.h("amma"))).json() is None
    acts = [r["action"] for r in await database.fetch("SELECT action FROM audit_events WHERE action LIKE 'sign_in.%' ORDER BY at")]
    assert acts == ["sign_in.began", "sign_in.sealed"]


async def test_without_a_browser_the_sitting_says_so(family, database):
    r = await family.client.post("/v1/sign-ins", headers=family.h("amma"), json={"service": "urbancompany"})
    assert r.status_code in (422, 503) and "no browser" in r.text


async def test_the_live_view_is_relayed_through_this_server_on_a_one_time_ticket(family, database, browser):
    import asyncio
    import json

    import websockets

    from familyos.execution import livebridge
    from familyos.execution import sessions as sealed

    # A stand-in for the browser's socket: answers one CDP call, echoes the rest.
    async def fake_browser(ws):
        async for raw in ws:
            m = json.loads(raw)
            if m.get("method") == "Target.getTargets":
                await ws.send(json.dumps({"id": m["id"], "result": {"targetInfos": [{"type": "page", "targetId": "T1", "url": "https://www.urbancompany.com/"}]}}))
            else:
                await ws.send(json.dumps({"echo": m}))
    server = await websockets.serve(fake_browser, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    browser.open_at = _opens_at(port)
    try:
        s = (await family.client.post("/v1/sign-ins", headers=family.h("amma"), json={"service": "urbancompany"})).json()
        assert s["ws_url"] == f"ws://127.0.0.1:{port}/"
        # Another member cannot get a ticket for it; the owner can, once per ticket.
        r = await family.client.post(f"/v1/sign-ins/{s['id']}/live-ticket", headers=family.h("appa"))
        assert r.status_code == 404
        r = await family.client.post(f"/v1/sign-ins/{s['id']}/live-ticket", headers=family.h("amma"))
        assert r.status_code == 200 and r.json()["path"].startswith(f"/v1/sign-ins/{s['id']}/live?ticket=")
        ticket = r.json()["path"].split("ticket=")[1]
        row = await sealed.redeem_live_ticket(ticket, uuid.UUID(s["id"]))
        assert row and row["ws_url"].endswith(f":{port}/")
        assert await sealed.redeem_live_ticket(ticket, uuid.UUID(s["id"])) is None        # once
        assert await sealed.redeem_live_ticket("nope", uuid.UUID(s["id"])) is None

        # The bridge: what the console sends reaches the browser; what it answers comes back.
        class Client:
            def __init__(self):
                self.outbox = asyncio.Queue()
                self.inbox = []
            async def receive_text(self):
                return await self.outbox.get()
            async def send_text(self, text):
                self.inbox.append(json.loads(text))
        client = Client()
        task = asyncio.create_task(livebridge.bridge(client, row["ws_url"], origin="http://test"))
        await client.outbox.put(json.dumps({"id": 1, "method": "Target.getTargets"}))
        await client.outbox.put(json.dumps({"id": 2, "method": "Input.insertText", "params": {"text": "9876"}}))
        for _ in range(50):
            if len(client.inbox) >= 2:
                break
            await asyncio.sleep(0.05)
        assert client.inbox[0]["result"]["targetInfos"][0]["targetId"] == "T1"
        assert client.inbox[1]["echo"]["params"]["text"] == "9876"
        task.cancel()
    finally:
        server.close()
        await server.wait_closed()


def _opens_at(port):
    async def open_at(url, *, minutes):
        return {"session_id": "steel-9", "live_url": "http://localhost:3000/x", "websocket_url": f"ws://127.0.0.1:{port}/",
                "user_agent": "Mozilla/5.0", "dimensions": {"width": 1280, "height": 800}}
    return open_at
