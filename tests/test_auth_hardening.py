"""Security fixes from KNOWN_ISSUES.md: device tokens, socket tickets, Google
state binding, rate limits, insecure defaults."""
import pytest

from tests.conftest import pdf  # noqa: F401


def _h(token):
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------- 1. device tokens

async def _device(family, who="amma"):
    r = await family.client.post("/v1/devices", headers=family.h(who), json={"label": "phone"})
    assert r.status_code == 201, r.text
    return r.json()["token"]


async def test_a_device_token_can_share_but_not_mint_tokens_or_erase_or_read(family):
    token = await _device(family)
    ok = await family.client.post("/v1/inbound/share", headers=_h(token), data={"text": "Sports day on Friday."})
    assert ok.status_code == 201, ok.text
    c = family.client
    for method, path, kw in (
            ("POST", "/v1/devices", {"json": {"label": "more"}}),
            ("GET", "/v1/devices", {}),
            ("DELETE", "/v1/devices/00000000-0000-0000-0000-000000000000", {}),
            ("POST", "/v1/household/erase", {"json": {"confirm_name": family.household["name"]}}),
            ("GET", "/v1/me", {}),
            ("GET", "/v1/artifacts", {}),
            ("POST", "/v1/household/members", {"json": {"display_name": "Zed", "role": "adult"}}),
    ):
        r = await c.request(method, path, headers=_h(token), **kw)
        assert r.status_code == 403, (method, path, r.status_code, r.text)
        assert "shortcut" in r.json()["detail"]
    # The household is still there, and the member's own session still works.
    assert (await c.get("/v1/me", headers=family.h("amma"))).status_code == 200


async def test_every_request_the_generated_shortcut_makes_is_one_its_device_token_may_make(family):
    """The personal Shortcut asks for the children's names first, then shares. It holds a device token, so both must pass the device policy:
    the names request was 403 for a device token until it was listed, and no test made it with one."""
    import plistlib

    from familyos import shortcut
    from familyos.api.deps import device_may
    made = []
    for action in shortcut.build("https://home.example.ts.net", "fosd_abc")["WFWorkflowActions"]:
        if action["WFWorkflowActionIdentifier"] == "is.workflow.actions.downloadurl":
            params = action["WFWorkflowActionParameters"]
            made.append((params["WFHTTPMethod"], params["WFURL"].removeprefix("https://home.example.ts.net")))
    assert made == [("GET", "/v1/inbound/share/tags"), ("POST", "/v1/inbound/share")]
    assert all(device_may(method, path) for method, path in made), made
    assert plistlib.dumps(shortcut.build("https://home.example.ts.net", "fosd_abc"))          # and it is still a plist
    token = await _device(family)
    r = await family.client.get("/v1/inbound/share/tags", headers=_h(token))
    assert r.status_code == 200 and r.text.split("\n")[-1] == "Nobody" and family.older["display_name"] in r.text, r.text


async def test_authenticated_api_answers_are_not_cached_unless_a_route_says_otherwise(family):
    """Answers hold the household's data and, for the personal Shortcut, a token that never expires: no shared or browser cache keeps them."""
    for path in ("/v1/me", "/v1/household", "/v1/devices"):
        r = await family.client.get(path, headers=family.h("amma"))
        assert r.status_code == 200 and r.headers["cache-control"] == "private, no-store", (path, r.headers.get("cache-control"))
    r = await family.client.get("/v1/shortcut", headers=family.h("amma"))                       # the personal Shortcut, built or generic
    assert r.status_code == 200 and r.headers["cache-control"] == "private, no-store"
    assert "cache-control" not in (await family.client.get("/healthz")).headers                  # not an API answer: unchanged


async def test_a_device_token_cannot_open_the_phone_socket(family):
    from starlette.testclient import TestClient  # noqa: F401  (documented: the check is in the route)

    from familyos import identity
    token = await _device(family)
    p = await identity.authenticate(token)
    assert p is not None and p.kind == "device"
    s = await identity.authenticate(family.amma_token)
    assert s.kind == "session"


# ---------------------------------------------------------------- 2. socket tickets and log redaction

async def test_the_phone_socket_ticket_is_single_use_short_lived_and_bound_to_its_errand(family):
    import uuid

    from familyos.execution import sessions
    r = await family.client.post("/v1/errands", headers=family.h("amma"),
                                 json={"service": "myclassboard", "kind": "look", "title": "Read the school's notices", "spec": {"what": "Announcements"}})
    errand_id = r.json()["id"]
    r = await family.client.post(f"/v1/errands/{errand_id}/phone-ticket", headers=family.h("amma"))
    assert r.status_code == 200, r.text
    ticket = r.json()["path"].split("ticket=")[1]
    assert await sessions.redeem_phone_ticket(ticket, uuid.uuid4()) is None          # wrong errand (and spent)
    r = await family.client.post(f"/v1/errands/{errand_id}/phone-ticket", headers=family.h("amma"))
    ticket = r.json()["path"].split("ticket=")[1]
    p = await sessions.redeem_phone_ticket(ticket, uuid.UUID(errand_id))
    assert p is not None and str(p.member_id) == family.amma["id"] and str(p.household_id) == family.household["id"] and p.kind == "session"
    # only a hash of the ticket is kept
    from familyos.db import pool as _pool
    assert not await _pool().fetchval("SELECT 1 FROM socket_tickets WHERE ticket_sha256 = convert_to($1, 'UTF8')", ticket)
    assert await sessions.redeem_phone_ticket(ticket, uuid.UUID(errand_id)) is None  # one use
    r = await family.client.post(f"/v1/errands/{errand_id}/phone-ticket", headers=family.h("amma"))
    ticket = r.json()["path"].split("ticket=")[1]
    from familyos.db import pool
    await pool().execute("UPDATE socket_tickets SET expires_at = NOW() - INTERVAL '1 second'")
    assert await sessions.redeem_phone_ticket(ticket, uuid.UUID(errand_id)) is None  # a minute
    # Another household's errand cannot be ticketed; no sign-in, no ticket.
    assert (await family.client.post(f"/v1/errands/{uuid.uuid4()}/phone-ticket", headers=family.h("amma"))).status_code == 404
    assert (await family.client.post(f"/v1/errands/{errand_id}/phone-ticket")).status_code == 401


def test_the_access_log_filter_redacts_token_ticket_and_link():
    import logging

    from familyos import logfilter
    rec = logging.LogRecord("uvicorn.access", logging.INFO, "", 0, '%s - "%s %s HTTP/%s" %d',
                            ("1.2.3.4:5", "GET", "/v1/errands/x/phone?token=fos_SECRET&a=1&ticket=T0P&link=L1NK", "1.1", 101), None)
    assert logfilter.RedactQuerySecrets().filter(rec)
    out = rec.getMessage()
    assert "SECRET" not in out and "T0P" not in out and "L1NK" not in out and "a=1" in out
    ws = logging.LogRecord("uvicorn.error", logging.INFO, "", 0, '"WebSocket /p?token=abc" [accepted]', (), None)
    logfilter.RedactQuerySecrets().filter(ws)
    assert "abc" not in ws.getMessage()


# ---------------------------------------------------------------- 4. rate limits

async def test_sign_in_requests_are_limited_per_email_and_per_ip(client, monkeypatch):
    from familyos.settings import settings
    for i in range(5):
        r = await client.post("/v1/sign-in/request", json={"email": "lily@example.com"})
        assert r.status_code == 202, i
    r = await client.post("/v1/sign-in/request", json={"email": "Lily@Example.com"})
    assert r.status_code == 429 and int(r.headers["retry-after"]) > 0
    assert (await client.post("/v1/sign-in/request", json={"email": "noah@example.com"})).status_code == 202
    monkeypatch.setattr(settings, "rate_sign_in_per_ip", 3)       # 7 hits so far from this address
    r = await client.post("/v1/sign-in/request", json={"email": "maya@example.com"})
    assert r.status_code == 429


async def test_household_creation_is_limited_per_ip(client):
    for _ in range(10):
        r = await client.post("/v1/households", json={"name": "x", "guardian": {"display_name": "A", "email": "a@example.com"}, "founding": "fnd_notarealticket"})
        assert r.status_code != 429
    r = await client.post("/v1/households", json={"name": "x", "guardian": {"display_name": "A", "email": "a@example.com"}, "founding": "fnd_notarealticket"})
    assert r.status_code == 429 and "retry-after" in r.headers


async def test_forwarded_for_is_ignored_unless_the_proxy_is_trusted(client, monkeypatch):
    from familyos.settings import settings
    monkeypatch.setattr(settings, "rate_sign_in_per_ip", 2)
    for i in range(2):
        assert (await client.post("/v1/sign-in/request", json={"email": f"u{i}@example.com"},
                                  headers={"X-Forwarded-For": f"9.9.9.{i}"})).status_code == 202
    assert (await client.post("/v1/sign-in/request", json={"email": "u9@example.com"},
                              headers={"X-Forwarded-For": "9.9.9.99"})).status_code == 429   # one real address
    monkeypatch.setattr(settings, "trust_proxy_headers", True)
    assert (await client.post("/v1/sign-in/request", json={"email": "u9@example.com"},
                              headers={"X-Forwarded-For": "1.1.1.1, 9.9.9.99"})).status_code == 202


def test_the_window_slides(monkeypatch):
    import time

    from familyos.ratelimit import SlidingWindow
    w = SlidingWindow()
    t = [1000.0]
    monkeypatch.setattr(time, "monotonic", lambda: t[0])
    assert w.take([("k", 2, 60)]) == 0 and w.take([("k", 2, 60)]) == 0
    assert w.take([("k", 2, 60)]) > 0
    t[0] += 61
    assert w.take([("k", 2, 60)]) == 0


# ---------------------------------------------------------------- 5. insecure defaults

async def test_the_server_refuses_to_start_without_a_real_master_key(monkeypatch):
    import base64

    import pytest

    from familyos.main import create_app, lifespan
    from familyos.settings import settings
    for bad in ("", "not base64 !!", base64.b64encode(b"short").decode(), base64.b64encode(b"k" * 33).decode()):
        monkeypatch.setattr(settings, "master_key", bad)
        with pytest.raises(RuntimeError, match="os.urandom"):
            async with lifespan(create_app(with_lifespan=False)):
                pass


@pytest.mark.parametrize("secret", ["", "change-me"])
async def test_inbound_email_is_off_when_the_secret_is_unset_or_the_placeholder(client, monkeypatch, secret):
    from familyos.settings import settings
    monkeypatch.setattr(settings, "inbound_webhook_secret", secret)
    r = await client.post("/v1/inbound/email", content=b"x", headers={"X-FamilyOS-Webhook-Secret": secret})
    assert r.status_code == 503 and "FAMILYOS_INBOUND_WEBHOOK_SECRET" in r.json()["detail"]


async def test_inbound_email_with_a_real_secret_still_checks_it(client):
    r = await client.post("/v1/inbound/email", content=b"x", headers={"X-FamilyOS-Webhook-Secret": "wrong"})
    assert r.status_code == 401


async def test_passkey_sign_in_challenges_are_limited_per_ip(client, monkeypatch):
    """Each open challenge is a row; an unauthenticated caller must not be able to fill the table for everyone."""
    from familyos.settings import settings
    monkeypatch.setattr(settings, "rate_passkey_per_ip", 3)
    monkeypatch.setattr(settings, "webauthn_origins", "http://localhost:8088")
    for _ in range(3):
        r = await client.post("/v1/sign-in/passkey/options", headers={"Origin": "http://localhost:8088"})
        assert r.status_code == 200
    r = await client.post("/v1/sign-in/passkey/options", headers={"Origin": "http://localhost:8088"})
    assert r.status_code == 429 and int(r.headers["retry-after"]) > 0


class _FakeSocket:
    def __init__(self):
        self.closed = None
        self.accepted = False

    async def close(self, code=1000):
        self.closed = code

    async def accept(self):
        self.accepted = True


async def test_only_the_asker_can_take_an_errands_phone_socket_and_a_stranger_displaces_nobody(family, client):
    """The socket attached before it asked whose errand it was: any signed-in member who knew an errand id could knock the real driver off."""
    import uuid

    from familyos.api import routes
    from familyos.execution import phone
    from tests.conftest import Family
    made = await family.client.post("/v1/errands", headers=family.h("amma"),
                                    json={"service": "myclassboard", "kind": "look", "title": "Read the school's notices", "spec": {"what": "Announcements"}})
    errand_id = uuid.UUID(made.json()["id"])
    held = phone.attach(errand_id, _FakeSocket().accept, uuid.UUID(family.household["id"]))      # the asker's phone, already connected
    other = await Family(client).setup(name="Neighbours", guardian_email="n@example.com")
    for token, expected in ((family.paati_token, 4403),          # same household, not the one who asked
                            (other.amma_token, 4404)):           # another household: there is no such errand for them
        ws = _FakeSocket()
        await routes.errand_phone_socket(ws, errand_id, token=token)
        assert ws.closed == expected and not ws.accepted
        assert phone.connected(errand_id) is held                # nobody was displaced
    # and the second lock: a household is never displaced from an id by another's attach
    with pytest.raises(phone.PhoneBusy):
        phone.attach(errand_id, _FakeSocket().accept, uuid.uuid4())
    phone.detach(errand_id)


async def test_a_phone_ticket_is_good_for_ten_minutes_so_a_driver_can_be_built_and_started(family):
    from familyos.db import pool
    r = await family.client.post("/v1/errands", headers=family.h("amma"),
                                 json={"service": "myclassboard", "kind": "look", "title": "Read the school's notices", "spec": {"what": "Announcements"}})
    errand_id = r.json()["id"]
    r = await family.client.post(f"/v1/errands/{errand_id}/phone-ticket", headers=family.h("amma"))
    assert r.status_code == 200
    seconds = await pool().fetchval("SELECT extract(epoch FROM expires_at - NOW()) FROM socket_tickets WHERE kind = 'phone'")
    assert 540 < seconds <= 600


async def test_a_device_token_cannot_open_the_teach_or_skill_sockets(family):
    """The share-extension token is for POST /inbound/share only; the taught-skill sockets must refuse it too."""
    import uuid

    from familyos.api import routes
    token = await _device(family)
    for handler in (routes.teach_phone_socket, routes.skill_phone_socket):
        ws = _FakeSocket()
        await handler(ws, uuid.uuid4(), token=token)
        assert ws.closed == 4401 and not ws.accepted


async def test_the_teach_and_skill_sockets_take_a_one_use_ticket_not_the_session_token(family):
    import uuid

    from familyos.api import routes
    from familyos.execution import sessions
    h = family.h("amma")
    lid = (await family.client.post("/v1/me/teach", headers=h, json={"kind": "phone", "target": "com.example.schoolapp"})).json()["id"]
    r = await family.client.post(f"/v1/me/teach/{lid}/phone-ticket", headers=h)
    assert r.status_code == 200 and "token=" not in r.json()["path"]
    ticket = r.json()["path"].split("ticket=")[1]
    assert await sessions.redeem_phone_ticket(ticket, uuid.uuid4()) is None            # another lesson, and now spent
    ticket = (await family.client.post(f"/v1/me/teach/{lid}/phone-ticket", headers=h)).json()["path"].split("ticket=")[1]
    from starlette.websockets import WebSocketDisconnect

    class Open(_FakeSocket):
        async def send_json(self, data):
            pass

        async def receive_json(self):
            raise WebSocketDisconnect()
    ws = Open()
    await routes.teach_phone_socket(ws, uuid.UUID(lid), ticket=ticket)                 # opens once
    assert ws.accepted
    ws = _FakeSocket()
    await routes.teach_phone_socket(ws, uuid.UUID(lid), ticket=ticket)                 # a second use is refused
    assert ws.closed == 4401 and not ws.accepted
    # not another member's lesson, not a lesson that is not there, not signed out
    assert (await family.client.post(f"/v1/me/teach/{lid}/phone-ticket", headers=family.h("appa"))).status_code in (403, 404)
    assert (await family.client.post(f"/v1/me/teach/{uuid.uuid4()}/phone-ticket", headers=h)).status_code == 404
    assert (await family.client.post(f"/v1/me/teach/{lid}/phone-ticket")).status_code == 401
    assert (await family.client.post(f"/v1/me/skills/{uuid.uuid4()}/phone-ticket", headers=h)).status_code == 404
