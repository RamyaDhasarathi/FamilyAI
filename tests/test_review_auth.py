"""Found in the self-review of the auth and session work (20 Oct 2026): each test failed before its fix."""
import re
import uuid

from familyos import identity, mail
from familyos.db import pool
from familyos.execution import sessions

CSRF = {"X-FamilyOS-CSRF": "1"}


async def test_a_phone_ticket_is_dead_once_the_token_that_asked_for_it_is_signed_out(family):
    """The ticket lasts ten minutes and carries a member: it must not outlive the session that asked for it."""
    r = await family.client.post("/v1/errands", headers=family.h("amma"),
                                 json={"service": "myclassboard", "kind": "look", "title": "Read the school's notices", "spec": {"what": "Announcements"}})
    errand_id = uuid.UUID(r.json()["id"])
    amma = await identity.authenticate(family.amma_token)
    ticket = await sessions.issue_phone_ticket(amma, errand_id)
    await identity.sign_out(amma)
    assert await sessions.redeem_phone_ticket(ticket, errand_id) is None


async def test_what_a_phone_ticket_says_about_the_member_is_read_again_when_it_is_used(family):
    r = await family.client.post("/v1/errands", headers=family.h("appa"),
                                 json={"service": "myclassboard", "kind": "look", "title": "Read the school's notices", "spec": {"what": "Announcements"}})
    errand_id = uuid.UUID(r.json()["id"])
    appa = await identity.authenticate(family.appa_token)
    ticket = await sessions.issue_phone_ticket(appa, errand_id)
    await pool().execute("UPDATE members SET role = 'adult' WHERE id = $1", appa.member_id)
    again = await sessions.redeem_phone_ticket(ticket, errand_id)
    assert again is not None and again.role == "adult"


async def test_the_cookie_outlives_the_tokens_sliding_window(family, monkeypatch):
    """The token slides forward while it is used; a cookie that ends 30 days after sign-in would sign an active person out. The server's own
    expiry is what ends a session, so the cookie is kept for as long as a browser keeps one."""
    sent = []

    async def fake(to, subject, body, *, ics=None):
        sent.append(body)

    monkeypatch.setattr(mail, "send", fake)
    monkeypatch.setattr(mail, "configured", lambda: True)
    await identity.request_sign_in("amma@example.com")
    link = re.search(r"link=([A-Za-z0-9_\-]+)", sent[-1]).group(1)
    r = await family.client.post("/v1/sign-in/redeem", json={"link": link}, headers=CSRF)
    header = next(h for h in r.headers.get_list("set-cookie") if h.startswith("familyos_session="))
    assert int(re.search(r"Max-Age=(\d+)", header).group(1)) >= 365 * 86400


def test_a_console_lets_go_of_the_old_token_only_when_the_server_has_taken_it_or_refused_it():
    """A rate limit or a server error on /v1/session must not delete the only copy of a live token."""
    import pathlib
    root = pathlib.Path(__file__).resolve().parent.parent / "familyos"
    for name in ("web/app.js", "web_classic/app.js", "web_orbit/orbit.js", "web_guide/guide.js", "web_home/boot.js"):
        text = (root / name).read_text()
        assert "removeItem('familyos.token')" in text, name
        before = text.split("removeItem('familyos.token')")[0][-400:]
        assert ".ok" in before and "401" in before, name


async def test_tickets_are_rate_limited_per_member_and_redoc_is_off(family, database, monkeypatch):
    from familyos.settings import settings
    monkeypatch.setattr(settings, "rate_tickets_per_member", 2)
    sitting = "00000000-0000-0000-0000-000000000001"
    codes = [(await family.client.post(f"/v1/sign-ins/{sitting}/live-ticket", headers=family.h("amma"))).status_code for _ in range(3)]
    assert codes[2] == 429 and 429 not in codes[:2]
    assert (await family.client.post(f"/v1/sign-ins/{sitting}/live-ticket", headers=family.h("appa"))).status_code != 429      # another member's own count
    assert (await family.client.get("/redoc")).status_code == 404


async def test_the_share_shortcut_is_offered_only_when_built_and_only_to_a_member(family, tmp_path, monkeypatch):
    from familyos.settings import settings
    monkeypatch.setattr(settings, "share_shortcut_file", "")          # tests never depend on a file the machine happens to have
    monkeypatch.setattr("familyos.shortcut.can_sign", lambda: False)  # ... or on being able to sign one
    assert (await family.client.get("/v1/shortcut")).status_code in (401, 403)
    assert (await family.client.get("/v1/shortcut", headers=family.h("amma"))).status_code == 404
    built = tmp_path / "s.shortcut"
    built.write_bytes(b"signed")
    monkeypatch.setattr(settings, "share_shortcut_file", str(built))
    r = await family.client.get("/v1/shortcut", headers=family.h("amma"))
    assert r.status_code == 200 and r.content == b"signed" and "FamilyOS.shortcut" in r.headers["content-disposition"]


async def test_the_share_shortcut_is_offered_the_childrens_names_and_a_caregiver_only_nobody(family):
    names = (await family.client.get("/v1/inbound/share/tags", headers=family.h("amma"))).text.split("\n")
    assert names[-1] == "Nobody" and family.older["display_name"] in names and family.younger["display_name"] in names and "Amma" not in names
    await family.client.put(f"/v1/members/{family.paati['id']}/circle-role", headers=family.h("amma"), json={"circle_role": "caregiver"})
    assert (await family.client.get("/v1/inbound/share/tags", headers=family.h("paati"))).text == "Nobody"


async def test_a_personal_shortcut_has_the_members_own_token_inside_and_nothing_to_paste(family, database, monkeypatch):
    from familyos import shortcut
    from familyos.settings import settings
    monkeypatch.setattr(shortcut, "can_sign", lambda: True)
    monkeypatch.setattr(settings, "console_url", "https://home.example.ts.net/app/")
    seen = {}

    async def fake_sign(server, token):
        seen.update(server=server, token=token)
        return b"personal"
    monkeypatch.setattr(shortcut, "signed_for", fake_sign)
    r = await family.client.get("/v1/shortcut", headers=family.h("amma"))
    assert r.status_code == 200 and r.content == b"personal" and seen["server"] == "https://home.example.ts.net"
    assert await database.fetchval("SELECT count(*) FROM member_tokens WHERE kind = 'device' AND label = 'Shortcut' AND revoked_at IS NULL") == 1
    # Another site cannot mint a token by pointing the browser here.
    r = await family.client.get("/v1/shortcut", headers={**family.h("amma"), "Sec-Fetch-Site": "cross-site"})
    assert r.status_code == 403
    # The file itself: the token is the first action's text and nothing is asked at import; the generic one asks.
    with_token, generic = shortcut.build("https://home.example.ts.net", "fosd_abc"), shortcut.build("https://home.example.ts.net")
    assert with_token["WFWorkflowActions"][0]["WFWorkflowActionParameters"]["WFTextActionText"] == "fosd_abc" and with_token["WFWorkflowImportQuestions"] == []
    assert len(generic["WFWorkflowImportQuestions"]) == 1
