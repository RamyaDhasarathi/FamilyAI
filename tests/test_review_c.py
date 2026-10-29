"""Findings from the self-review of the areas never read before (20 Oct 2026): each test failed before its fix."""
import uuid

from familyos import chat, clock
from familyos.identity import Principal


async def test_a_caregiver_is_not_shown_the_households_standing_payments(family, database):
    """Standing payments (rent, a payee and an amount) went by `visibility = 'shared'` alone, so the rule that keeps a caregiver to what is
    handed to them did not reach them: the list, Ask's facts and the stop button all showed them the household's money."""
    r = await family.client.post("/v1/standing", headers=family.h("amma"), json={
        "title": "Rent", "payee": "Mr Raman", "amount": 18000, "day_of_month": 5})
    assert r.status_code == 201, r.text
    standing_id = r.json()["id"]
    paati = family.h("paati")
    assert [s["title"] for s in (await family.client.get("/v1/standing", headers=paati)).json()] == ["Rent"]      # an adult sees what is shared
    await family.client.put(f"/v1/members/{family.paati['id']}/circle-role", headers=family.h("amma"), json={"circle_role": "caregiver"})
    assert (await family.client.get("/v1/standing", headers=paati)).json() == []
    assert (await family.client.delete(f"/v1/standing/{standing_id}", headers=paati)).status_code == 404
    facts = await chat.context(Principal(member_id=uuid.UUID(family.paati["id"]), household_id=uuid.UUID(family.household["id"]),
                                         role="adult", display_name="Paati"))
    text = "\n".join(facts.lines)
    assert "Mr Raman" not in text and "standing payment" not in text
    # The guardian still has it.
    assert [s["title"] for s in (await family.client.get("/v1/standing", headers=family.h("amma"))).json()] == ["Rent"]


async def test_a_line_of_spaces_cannot_stall_the_rule_reader():
    """The 'is this the notice's own date line' pattern backtracked cubically on a run of spaces: a line of a few thousand spaces after a date
    held the worker (and the event loop, the reader being synchronous) for minutes."""
    import datetime as dt
    import time

    from familyos.extraction import rules
    from familyos.extraction.parse import Page, ParsedDocument
    line = "Sports day on 5 November 2026" + " " * 1500 + "bring a hat please"
    doc = ParsedDocument("text/plain", [Page(1, line, [], None, None, "text")], [])
    started = time.monotonic()
    claims = await rules.RulesExtractor().run(doc, dt.date(2026, 10, 20))
    assert time.monotonic() - started < 1.0, "the rule reader backtracked on a run of spaces"
    assert any(c.date == dt.date(2026, 11, 5) for c in claims)
    # The notice's own date line is still not a claim.
    for own in ("Date: 20 October 2026", "Dated 20/10/2026"):
        doc = ParsedDocument("text/plain", [Page(1, own, [], None, None, "text")], [])
        assert not [c for c in await rules.RulesExtractor().run(doc, dt.date(2026, 10, 20)) if c.date == dt.date(2026, 10, 20)], own


def test_html_that_never_closes_its_tags_cannot_stall_the_readers_of_mail():
    """`<script.*?</script>`, `<a ...>(.*?)</a>` and `<[^>]+>` each rescan to the end of the text from every opener, so a mail of unclosed tags
    (16000 of them took ten seconds, a megabyte of them minutes) held the worker and its event loop. Run at arrival, on any sender's mail."""
    import email.message
    import time

    from familyos import htmltext, paylinks
    from familyos.execution import disposable
    from familyos.extraction import parse
    from familyos.intake import email as email_adapter
    hostile = ("<script>" * 40000) + ('<a href="https://x.example/pay">' * 40000) + ("<p " * 40000) + "Pay the fee"
    msg = email.message.EmailMessage()
    msg["From"] = "a@example.com"
    msg["Subject"] = "Fees"
    msg.set_content("plain", subtype="plain")
    msg.add_alternative(hostile, subtype="html")
    raw = msg.as_bytes()
    started = time.monotonic()
    email_adapter.parse(raw)
    paylinks.from_email(raw)
    parse._strip_html(hostile)
    disposable._text_of("<title>" + hostile)
    htmltext.strip_blocks(hostile)
    assert time.monotonic() - started < 3.0, "an HTML reader backtracked on tags that never close"
    # And the ordinary mail still reads as it did.
    good = '<div><p>Dear parent</p><script>x()</script><p>Pay <a href="https://school.example/pay?id=1">now</a> &amp; sign</p></div>'
    text = htmltext.text_of(good)
    assert "Dear parent" in text and "x()" not in text and "& sign" in text
    assert htmltext.anchors(good) == [("now", "https://school.example/pay?id=1")]


async def test_an_errands_live_browser_address_is_not_handed_to_the_household(family, database):
    """A stopped errand keeps its browser's DevTools address in `outcome.browser`, and the errand's JSON returned it verbatim to every member
    who listed or fetched it: the address of another member's signed-in session, whose take-over is the asker's alone."""
    r = await family.client.post("/v1/errands", headers=family.h("amma"),
                                 json={"service": "myclassboard", "kind": "look", "title": "Read the school's notices", "spec": {"what": "Announcements"}})
    assert r.status_code == 201, r.text
    errand_id = r.json()["id"]
    await database.execute("UPDATE errands SET outcome = outcome || $2::jsonb WHERE id = $1", uuid.UUID(errand_id),
                           {"browser": {"session_id": "sess-secret", "ws_url": "ws://10.0.0.5:3000/devtools"}, "steps": []})
    for who in ("amma", "appa"):
        for path in (f"/v1/errands/{errand_id}", "/v1/errands"):
            body = (await family.client.get(path, headers=family.h(who))).text
            assert "ws://10.0.0.5" not in body and "sess-secret" not in body, (who, path)
    # What the console needs is still said: the run stopped with a browser the asker can take over.
    got = (await family.client.get(f"/v1/errands/{errand_id}", headers=family.h("amma"))).json()
    assert got["outcome"]["browser"] == {"held": True}


def _nested_mail(depth: int) -> bytes:
    parts = "".join(f'Content-Type: multipart/mixed; boundary="b{i}"\n\n--b{i}\n' for i in range(depth))
    return ("From: office@school.example.com\nTo: amma@gmail.com\nSubject: fees\nMIME-Version: 1.0\n" + parts + "Content-Type: text/plain\n\nhello\n").encode()


async def test_a_mail_nested_past_the_parsers_limit_is_refused_not_crashed_on(family, database):
    """A mail nested a thousand multiparts deep raised RecursionError out of the parser. In Gmail intake that is an error that 'might work next
    time', so one such mail stalled the member's mailbox for good; on the forwarding address it was a 500 and a retry storm."""
    import pytest

    from familyos.intake import gateway
    raw = _nested_mail(1500)
    with pytest.raises(gateway.Rejected) as caught:
        await gateway.receive_gmail(uuid.UUID(family.household["id"]), uuid.UUID(family.amma["id"]), raw, gmail_id="hostile-1")
    assert caught.value.reason == "unreadable_mail"
    with pytest.raises(gateway.Rejected):
        await gateway.receive_email(raw, recipient=None)


async def test_a_nul_in_a_mails_headers_is_stored_not_a_poison_pill(family, database):
    """Postgres jsonb cannot hold U+0000. A NUL in the Subject or From went into the artifact's `source` and the insert failed with an ordinary
    database error, which a mailbox poll reads as 'might work next time': one such mail stalled that mailbox for good."""
    from familyos.intake import gateway
    raw = (b"From: Office <office@school.example.com>\nTo: amma@gmail.com\nSubject: Fees due\x00 now\nMessage-ID: <n\x00ul@school.example.com>\n"
           b"MIME-Version: 1.0\nContent-Type: text/plain\n\nPlease pay the fee by Friday.\n")
    parent, duplicate = await gateway.receive_gmail(uuid.UUID(family.household["id"]), uuid.UUID(family.amma["id"]), raw, gmail_id="nul-1")
    assert not duplicate and "\x00" not in str(parent["source"]) and "Fees due" in parent["source"]["subject"]


async def test_a_mailbox_consent_only_completes_in_the_browser_that_began_it(family, database, monkeypatch):
    """The state of a mailbox connection was bound to the member who began it but not to the browser: begin one's own, send the Google link to a
    victim, and the victim's Gmail is connected to the attacker's member (login CSRF; the sign-in flow already binds its state to a cookie)."""
    import httpx

    from familyos.main import create_app
    from familyos.settings import settings
    monkeypatch.setattr(settings, "google_client_id", "client-id.apps.googleusercontent.com")
    monkeypatch.setattr(settings, "google_client_secret", "client-secret")
    monkeypatch.setattr(settings, "google_redirect_uri", "http://localhost:8000/v1/google/callback")
    monkeypatch.setattr(settings, "gmail_enabled", True)
    monkeypatch.setattr(settings, "console_url", "http://localhost:8000/app/")      # a Secure cookie is not sent back over the test's plain http
    from familyos.intake import google

    async def no_google(*a, **k):
        raise google.GoogleError("no Google in a test", status=401)
    monkeypatch.setattr(google, "exchange_code", no_google)
    r = await family.client.post("/v1/google/mailboxes/authorize", headers=family.h("amma"))
    assert r.status_code == 200, r.text
    state = r.json()["state"]
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=create_app(with_lifespan=False)), base_url="http://test") as victim:
        got = await victim.get("/v1/google/callback", params={"state": state, "code": "attackers-code"})
    assert "mailbox=failed" in got.headers["location"]
    assert await database.fetchval("SELECT used_at FROM google_auth_states WHERE state = $1", state) is None      # refused before the state is spent
    # The browser that began it carries the cookie, and the flow goes on (the exchange then fails: there is no Google here).
    await family.client.get("/v1/google/callback", params={"state": state, "code": "my-code"})
    assert await database.fetchval("SELECT used_at FROM google_auth_states WHERE state = $1", state) is not None


async def test_no_read_route_answers_another_households_ids(client, family, database):
    """A sweep for cross-household reads: every row of every table the first household owns (its ids, as a stranger would have to guess them)
    is asked for by a guardian of a different household on every GET route that takes one id in its path. The answer must never be 200."""
    import re

    from tests.conftest import Family, pdf
    from tests.test_brief import _obligation
    other = await Family(client).setup(name="Neighbours", guardian_email="n@example.com")
    shared = (await family.upload("amma", pdf("shared"), filename="s.pdf", visibility="shared")).json()["artifact"]["id"]
    private = (await family.upload("amma", pdf("private"), filename="p.pdf", visibility="private")).json()["artifact"]["id"]
    import datetime as dt
    await _obligation(database, family, artifact_id=shared, due=clock.today() + dt.timedelta(days=3))
    await family.client.post("/v1/todos", headers=family.h("amma"), json={"title": "A's todo"})
    await family.client.post("/v1/errands", headers=family.h("amma"),
                             json={"service": "myclassboard", "kind": "look", "title": "Read the notices", "spec": {"what": "Announcements"}})
    await family.client.post("/v1/standing", headers=family.h("amma"), json={"title": "Rent", "payee": "Mr Raman", "amount": 100, "day_of_month": 5})
    household_id = uuid.UUID(family.household["id"])
    ids: set[str] = {shared, private, family.amma["id"], family.older["id"]}
    for t in await database.fetch("SELECT table_name FROM information_schema.columns WHERE table_schema = 'public' AND column_name = 'household_id' "
                                  "AND table_name IN (SELECT table_name FROM information_schema.columns WHERE table_schema = 'public' AND column_name = 'id' "
                                  "AND data_type = 'uuid')"):
        for r in await database.fetch(f'SELECT id FROM "{t["table_name"]}" WHERE household_id = $1 LIMIT 40', household_id):
            ids.add(str(r["id"]))
    assert len(ids) > 8
    from familyos.main import create_app
    routes = sorted(path for path, ops in create_app(with_lifespan=False).openapi()["paths"].items()
                    if "get" in ops and path.startswith("/v1/") and len(re.findall(r"\{[^}]+\}", path)) == 1)
    assert len(routes) > 10
    leaks = []
    for path in routes:
        for i in ids:
            r = await other.client.get(re.sub(r"\{[^}]+\}", i, path), headers=other.h("amma"))
            if r.status_code == 200:
                leaks.append((path, i, r.text[:80]))
    assert not leaks, leaks[:10]


async def test_no_read_route_shows_one_member_anothers_private_notice(family, database):
    """The same sweep inside a household: a private notice (and the date and claim read from it) is amma's alone, whoever else asks, on every
    GET route that takes one id, a guardian included."""
    import datetime as dt
    import re

    from familyos.main import create_app
    from tests.conftest import pdf
    from tests.test_brief import _obligation
    private = (await family.upload("amma", pdf("private"), filename="p.pdf", visibility="private")).json()["artifact"]["id"]
    oid = await _obligation(database, family, artifact_id=private, due=clock.today() + dt.timedelta(days=3), title="Amma's private appointment")
    ids = {private, str(oid)}
    for r in await database.fetch("SELECT id FROM claims WHERE artifact_id = $1", uuid.UUID(private)):
        ids.add(str(r["id"]))
    routes = sorted(path for path, ops in create_app(with_lifespan=False).openapi()["paths"].items()
                    if "get" in ops and path.startswith("/v1/") and len(re.findall(r"\{[^}]+\}", path)) == 1)
    leaks = []
    for who in ("appa", "paati"):
        for path in routes:
            for i in ids:
                r = await family.client.get(re.sub(r"\{[^}]+\}", i, path), headers=family.h(who))
                if r.status_code == 200 and ("Amma's private" in r.text or private in r.text):
                    leaks.append((who, path, i, r.text[:80]))
    assert not leaks, leaks[:10]


async def test_no_list_route_shows_a_caregiver_what_the_household_shares(family, database):
    """The caregiver rule (they see only what is handed to them) across every GET route that takes no id, with markers planted in what the
    household shares: a notice's date, a standing payment, a to-do. The standing payment was the one that leaked."""
    import datetime as dt
    import re

    from familyos.main import create_app
    from tests.conftest import pdf
    from tests.test_brief import _obligation
    shared = (await family.upload("amma", pdf("shared"), filename="s.pdf", visibility="shared")).json()["artifact"]["id"]
    await _obligation(database, family, artifact_id=shared, due=clock.today() + dt.timedelta(days=3), title="SECRETOBLIGATION")
    await family.client.post("/v1/standing", headers=family.h("amma"), json={"title": "SECRETRENT", "payee": "SECRETPAYEE", "amount": 100, "day_of_month": (clock.today() + dt.timedelta(days=3)).day})
    await family.client.post("/v1/todos", headers=family.h("amma"), json={"title": "SECRETTODO"})
    await family.client.put(f"/v1/members/{family.paati['id']}/circle-role", headers=family.h("amma"), json={"circle_role": "caregiver"})
    markers = ("SECRETOBLIGATION", "SECRETRENT", "SECRETPAYEE", "SECRETTODO")
    paths = sorted(p for p, ops in create_app(with_lifespan=False).openapi()["paths"].items()
                   if "get" in ops and p.startswith("/v1/") and not re.search(r"\{[^}]+\}", p))
    assert len(paths) > 30
    leaks = []
    for path in paths:
        r = await family.client.get(path, headers=family.h("paati"))
        if r.status_code == 200 and any(m in r.text for m in markers):
            leaks.append((path, [m for m in markers if m in r.text]))
    assert not leaks, leaks


async def test_a_caregiver_cannot_read_or_cancel_the_households_errands_by_id(family, database):
    """`errands.list_for` hides the household's errands from a caregiver, but `get` and `cancel` went by household alone: with an id (they appear
    in links and in the activity trail) a caregiver could read what a member had asked for and call it off."""
    r = await family.client.post("/v1/errands", headers=family.h("amma"),
                                 json={"service": "myclassboard", "kind": "look", "title": "Read the school's notices", "spec": {"what": "Announcements"}})
    errand_id = r.json()["id"]
    paati = family.h("paati")
    assert (await family.client.get(f"/v1/errands/{errand_id}", headers=paati)).status_code == 200          # an adult may
    await family.client.put(f"/v1/members/{family.paati['id']}/circle-role", headers=family.h("amma"), json={"circle_role": "caregiver"})
    assert (await family.client.get(f"/v1/errands/{errand_id}", headers=paati)).status_code == 404
    assert (await family.client.post(f"/v1/errands/{errand_id}/cancel", headers=paati)).status_code == 404
    assert (await family.client.get(f"/v1/errands/{errand_id}", headers=family.h("amma"))).json()["status"] == "approved"      # untouched


def test_a_mail_with_thousands_of_attachments_is_cut_to_a_page_of_them():
    """Each attachment became an artifact and an extraction job: a few hundred kilobytes of mail made thousands of them."""
    from email.message import EmailMessage

    from familyos.intake import email as email_adapter
    msg = EmailMessage()
    msg["From"] = "a@example.com"
    msg["To"] = "x@example.com"
    msg.set_content("hi")
    for i in range(300):
        msg.add_attachment(b"%PDF-1.4\n%%EOF\n", maintype="application", subtype="pdf", filename=f"{i}.pdf")
    parsed = email_adapter.parse(msg.as_bytes())
    assert len(parsed.attachments) == email_adapter.MAX_ATTACHMENTS and parsed.attachments_over == 300 - email_adapter.MAX_ATTACHMENTS


def test_a_receipt_line_of_spaces_cannot_stall_the_item_reader():
    """`_QTY_X_ITEM` and `_ITEM_X_QTY` backtrack quadratically on a long run of spaces inside a line."""
    import time

    from familyos.extraction import items
    text = "1 x Tomatoes ₹24.00\n1 x a" + " " * 20000 + "y\nChicken Popcorn x2\n₹180.00\n" + "a" + " " * 20000 + "x y"
    started = time.monotonic()
    found = items.parse_items(text)
    assert time.monotonic() - started < 1.0, "the receipt reader backtracked on a run of spaces"
    assert [i["item"] for i in found] == ["Tomatoes", "Chicken Popcorn"]


async def test_a_burst_of_mail_bigger_than_one_page_is_all_read_after_the_backfill(family, database, monkeypatch):
    """After the first pass a poll asked for one page (gmail_max_per_poll, newest first) and then moved `last_polled_at` to now, so a burst
    or a day of downtime of more than a page silently lost everything older than the newest page."""
    import datetime as dt
    import json

    from familyos.intake import mailbox
    from familyos.settings import settings
    from tests.test_gmail import FakeGoogle, _connect, _raw

    class Paged(FakeGoogle):
        async def __call__(self, method, url, *, headers, params, data):
            if url.endswith("/messages"):
                self.queries.append(params.get("q", ""))
                ids = list(self.messages)[::-1]                       # newest first, as Gmail lists
                size, start = int(params["maxResults"]), int(params.get("pageToken") or 0)
                body = {"messages": [{"id": i, "threadId": "t-" + i} for i in ids[start:start + size]]}
                if start + size < len(ids):
                    body["nextPageToken"] = str(start + size)
                return 200, json.dumps(body).encode()
            return await super().__call__(method, url, headers=headers, params=params, data=data)

    monkeypatch.setattr(settings, "gmail_max_per_poll", 3)
    monkeypatch.setattr(settings, "gmail_enabled", True)
    monkeypatch.setattr(settings, "google_client_id", "client-id.apps.googleusercontent.com")
    monkeypatch.setattr(settings, "google_client_secret", "client-secret")
    monkeypatch.setattr(settings, "google_redirect_uri", "http://localhost:8000/v1/google/callback")
    monkeypatch.setattr(settings, "gmail_query", "subject:school")
    fake = Paged(messages={})
    account = await _connect(family, fake)
    await mailbox.poll(account["id"], transport=fake)                 # an empty first pass: the backfill is done
    assert await database.fetchval("SELECT backfill_done FROM google_accounts WHERE id = $1", account["id"])
    for n in range(8):
        fake.messages[f"m{n}"] = _raw(subject=f"Notice {n}")
    later = dt.datetime.now(dt.UTC) + dt.timedelta(minutes=10)
    result = await mailbox.poll(account["id"], now=later, transport=fake)
    assert result["stored"] == 8 and not result["stalled"], result
    assert len(fake.fetched) == 8


def test_gmail_s_own_verdict_counts_for_a_connected_mailbox_and_a_forged_one_does_not():
    from familyos.intake import email as mail
    def raw(server):
        return (f"Authentication-Results: {server}; dkim=pass header.d=bank.example; dmarc=pass header.from=bank.example\r\n"
                "From: Bank <alerts@bank.example>\r\nTo: me@example.com\r\nSubject: Bill\r\n\r\nPay.\r\n").encode()
    assert mail.parse(raw("mx.google.com"), authserv_id="mx.google.com").sender_authenticated
    assert not mail.parse(raw("evil.example"), authserv_id="mx.google.com").sender_authenticated
    assert not mail.parse(raw("mx.google.com")).sender_authenticated          # the forwarding address trusts only its own provider's name



async def test_a_caregivers_ask_is_not_told_the_households_structure(family, database):
    """Ask's facts named every member, school and class, the signed-in sites and the phone apps, to a caregiver as to a guardian."""
    def facts_for(who):
        m = getattr(family, who)
        return chat.context(Principal(member_id=uuid.UUID(m["id"]), household_id=uuid.UUID(family.household["id"]),
                                      role=m["role"], display_name=m["display_name"]))
    before = "\n".join((await facts_for("paati")).lines)
    assert "[MEMBERS]" in before and "PHONE APPS" in before and "SIGNED-IN SITES" in before
    await family.client.put(f"/v1/members/{family.paati['id']}/circle-role", headers=family.h("amma"), json={"circle_role": "caregiver"})
    after = "\n".join((await facts_for("paati")).lines)
    assert "PHONE APPS" not in after and "SIGNED-IN SITES" not in after
    assert family.amma["display_name"] not in after.split("\n")[0] and family.appa["display_name"] not in after.split("\n")[0]
    assert "PHONE APPS" in "\n".join((await facts_for("amma")).lines)
