"""Our data collecting layer, Google part (famos-notes/COLLECTION_PLAN.md, decided 30 Oct 2026): with
FAMILYOS_GOOGLE_SIGN_IN_COLLECT on, Google sign-in also asks to read Gmail, Calendar and Tasks; the refresh token is
kept sealed in a local cache on this machine (never in the database), and what is read is kept there too, for the
member it belongs to only. Off, sign-in stays the founder's: email only, nothing kept."""
import base64
import json
import os
import sqlite3

import pytest

from familyos import identity
from familyos.collect import google_data, store
from familyos.intake import google
from familyos.settings import settings
from tests.test_google_sign_in import CLIENT, _id_token

REFRESH = "1//refresh-token-that-must-never-be-stored-in-clear"


@pytest.fixture(autouse=True)
def collecting(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "google_client_id", CLIENT)
    monkeypatch.setattr(settings, "google_client_secret", "client-secret")
    monkeypatch.setattr(settings, "google_sign_in_collect", True)
    monkeypatch.setattr(settings, "collect_dir", str(tmp_path / "collect"))
    return tmp_path / "collect"


class FakeGoogle:
    """Google's token endpoint and the three read APIs, as the collector calls them."""

    def __init__(self, *, tasks_enabled=True):
        self.tasks_enabled = tasks_enabled
        self.calls = []
        self.read = []

    async def __call__(self, method, url, *, headers, params, data):
        self.calls.append((method, url))
        if url == google.TOKEN_URL:
            body = {"access_token": "a", "expires_in": 3599, "scope": " ".join(google.SIGN_IN_SCOPES + google_data.COLLECT_SCOPES),
                    "id_token": _id_token("amma@example.com")}
            if data.get("grant_type") == "authorization_code":
                body["refresh_token"] = REFRESH
            return 200, json.dumps(body).encode()
        assert headers.get("Authorization") == "Bearer a"
        if url == f"{google.GMAIL}/messages":
            return 200, json.dumps({"messages": [{"id": "m1"}, {"id": "m2"}]}).encode()
        if url == f"{google.GMAIL}/messages/m1/attachments/A1":
            return 200, json.dumps({"data": base64.urlsafe_b64encode(b"%PDF fee receipt").decode().rstrip("=")}).encode()
        if url.startswith(f"{google.GMAIL}/messages/"):
            mid = url.rsplit("/", 1)[1]
            assert params.get("format") == "full"
            self.read.append(mid)
            heads = [{"name": "From", "value": "School <office@school.example>"}, {"name": "To", "value": "amma@example.com"},
                     {"name": "Cc", "value": "appa@example.com"},
                     {"name": "Subject", "value": "Notice m1" if mid == "m1" else "Your login OTP is 482913"}]
            b64 = lambda t: base64.urlsafe_b64encode(t.encode()).decode().rstrip("=")  # noqa: E731
            payload = ({"mimeType": "multipart/mixed", "headers": heads, "parts": [
                           {"mimeType": "text/plain", "body": {"data": b64("PTM on Saturday at 10. Fees due 5 Nov.")}},
                           {"mimeType": "application/pdf", "filename": "receipt.pdf", "body": {"attachmentId": "A1", "size": 16}}]}
                       if mid == "m1" else
                       {"mimeType": "text/html", "headers": heads, "body": {"data": b64("<p>Use <b>482913</b> to sign in</p>")}})
            return 200, json.dumps({"id": mid, "threadId": "t" + mid, "snippet": f"snippet {mid}", "labelIds": ["INBOX"],
                                    "internalDate": "1761800000000", "historyId": "9", "sizeEstimate": 2048, "payload": payload}).encode()
        if url == f"{google.CALENDAR}/users/me/calendarList":
            return 200, json.dumps({"items": [{"id": "primary", "summary": "amma@example.com", "accessRole": "owner"},
                                              {"id": "en.indian#holiday@group.v.calendar.google.com", "summary": "Holidays in India", "accessRole": "reader"},
                                              {"id": "busy@example.com", "summary": "Boss", "accessRole": "freeBusyReader"}]}).encode()
        if url == f"{google.CALENDAR}/calendars/primary/events":
            return 200, json.dumps({"items": [{"id": "e1", "summary": "PTM", "status": "confirmed", "updated": "2026-10-29T00:00:00Z",
                                               "start": {"dateTime": "2026-11-02T10:00:00+05:30"}, "description": "Bring the report card",
                                               "end": {"dateTime": "2026-11-02T11:00:00+05:30"}, "location": "School",
                                               "organizer": {"email": "office@school.example"},
                                               "attendees": [{"email": "amma@example.com", "responseStatus": "accepted"}]}]}).encode()
        if url == f"{google.CALENDAR}/calendars/en.indian%23holiday%40group.v.calendar.google.com/events":
            return 200, json.dumps({"items": [{"id": "e2", "summary": "Diwali", "start": {"date": "2026-11-08"}, "end": {"date": "2026-11-09"}}]}).encode()
        if url == f"{google_data.TASKS}/users/@me/lists":
            if not self.tasks_enabled:
                return 403, b'{"error": {"code": 403, "status": "PERMISSION_DENIED", "message": "Google Tasks API has not been used in project 1 before or it is disabled. accessNotConfigured"}}'
            return 200, json.dumps({"items": [{"id": "L1", "title": "My Tasks"}]}).encode()
        if url == f"{google_data.TASKS}/lists/L1/tasks":
            return 200, json.dumps({"items": [{"id": "k1", "title": "Pay school fee", "status": "needsAction", "due": "2026-11-05T00:00:00.000Z"}]}).encode()
        raise AssertionError(f"unexpected call {method} {url}")


async def _sign_in(database):
    begun = await identity.google_sign_in_url()
    return begun


async def test_sign_in_asks_to_read_gmail_calendar_and_tasks_when_collecting(database):
    url = (await identity.google_sign_in_url())["url"]
    for scope in ("gmail.readonly", "calendar.readonly", "tasks.readonly", "userinfo.email"):
        assert scope in url, scope


async def test_off_sign_in_is_the_founders_email_only_and_keeps_nothing(database, monkeypatch, collecting, family):
    monkeypatch.setattr(settings, "google_sign_in_collect", False)
    begun = await identity.google_sign_in_url()
    assert "gmail.readonly" not in begun["url"]
    await identity.complete_google_sign_in(begun["state"], "code", transport=FakeGoogle())
    assert store.google_account("amma@example.com") is None


async def test_the_refresh_token_is_kept_sealed_in_the_local_cache_never_in_clear(database, family, collecting):
    begun = await identity.google_sign_in_url()
    await identity.complete_google_sign_in(begun["state"], "code", transport=FakeGoogle())
    kept = store.google_account("amma@example.com")
    assert kept is not None and "gmail.readonly" in " ".join(kept["scopes"])
    assert store.google_refresh_token("amma@example.com") == REFRESH
    raw = (collecting / "collect.sqlite3").read_bytes()
    assert REFRESH.encode() not in raw
    assert oct((collecting / "collect.sqlite3").stat().st_mode)[-3:] == "600"


async def test_a_run_reads_gmail_calendar_and_tasks_into_the_cache(database, family):
    store.keep_google("amma@example.com", REFRESH, google_data.COLLECT_SCOPES)
    out = await google_data.run("amma@example.com", transport=FakeGoogle())
    assert out["counts"] == {"gmail": 2, "calendar": 2, "tasks": 1} and out["errors"] == {}
    mail = store.items("gmail", "amma@example.com")
    assert {m["subject"] for m in mail} == {"Notice m1", "Your login OTP is 482913"} and mail[0]["sender"].startswith("School")
    events = store.items("calendar", "amma@example.com")
    assert {e["summary"] for e in events} == {"PTM", "Diwali"} and any(e["all_day"] for e in events)
    assert store.items("tasks", "amma@example.com")[0]["title"] == "Pay school fee"
    # Again: the same items, not twice -- and mail already read in full is not read again.
    again = FakeGoogle()
    await google_data.run("amma@example.com", transport=again)
    assert len(store.items("gmail", "amma@example.com")) == 2 and again.read == []


async def test_everything_google_lets_it_read_full_mail_attachments_every_calendar(database, family, collecting):
    store.keep_google("amma@example.com", REFRESH, google_data.COLLECT_SCOPES)
    await google_data.run("amma@example.com", transport=FakeGoogle())
    mail = {m["id"]: m for m in store.items("gmail", "amma@example.com")}
    assert mail["m1"]["body"] == "PTM on Saturday at 10. Fees due 5 Nov." and mail["m1"]["cc"] == "appa@example.com"
    assert mail["m1"]["attachments"] == 1 and mail["m1"]["otp"] is None
    assert "482913" in mail["m2"]["body_html"] and mail["m2"]["otp"] == "482913"
    [att] = store.attachments("amma@example.com")
    assert att["filename"] == "receipt.pdf" and att["saved"]
    path = store.attachment_path("amma@example.com", "m1", "A1")
    assert open(path, "rb").read() == b"%PDF fee receipt" and oct(os.stat(path).st_mode)[-3:] == "600"
    events = {e["id"]: e for e in store.items("calendar", "amma@example.com")}
    assert events["e2"]["calendar_name"] == "Holidays in India" and events["e1"]["description"] == "Bring the report card"
    assert json.loads(events["e1"]["attendees"])[0]["response"] == "accepted"
    # The newest code, for the browser agent waiting on one.
    assert store.latest_otp("amma@example.com", "2025-10-01T00:00:00+00:00")["otp"] == "482913"


async def test_an_api_google_has_not_switched_on_is_said_and_the_others_still_run(database, family):
    store.keep_google("amma@example.com", REFRESH, google_data.COLLECT_SCOPES)
    out = await google_data.run("amma@example.com", transport=FakeGoogle(tasks_enabled=False))
    assert out["counts"]["gmail"] == 2 and out["counts"]["calendar"] == 2
    assert "Google Tasks API" in out["errors"]["tasks"] and "enable" in out["errors"]["tasks"].lower()
    assert store.status("amma@example.com")["last_errors"] == out["errors"]


async def test_the_routes_show_a_member_only_their_own(family, database):
    store.keep_google("amma@example.com", REFRESH, google_data.COLLECT_SCOPES)
    await google_data.run("amma@example.com", transport=FakeGoogle())
    r = await family.client.get("/v1/collect/status", headers=family.h("amma"))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["google"]["connected"] and body["google"]["counts"] == {"gmail": 2, "calendar": 2, "tasks": 1}
    mail = await family.client.get("/v1/collect/google/gmail", headers=family.h("amma"))
    assert mail.status_code == 200 and len(mail.json()) == 2
    got = await family.client.get("/v1/collect/google/attachments/m1/A1", headers=family.h("amma"))
    assert got.status_code == 200 and got.content == b"%PDF fee receipt"
    assert (await family.client.get("/v1/collect/google/attachments/m1/A1", headers=family.h("appa"))).status_code == 404
    # Appa signed in: none of Amma's.
    other = await family.client.get("/v1/collect/google/gmail", headers=family.h("appa"))
    assert other.status_code == 200 and other.json() == []
    status = await family.client.get("/v1/collect/status", headers=family.h("appa"))
    assert status.json()["google"]["connected"] is False
    assert (await family.client.get("/v1/collect/google/nonsense", headers=family.h("amma"))).status_code == 404
    assert (await family.client.get("/v1/collect/status")).status_code == 401


async def test_collect_now_needs_a_connected_google(family, database):
    r = await family.client.post("/v1/collect/google/run", headers=family.h("appa"))
    assert r.status_code == 409


def test_the_cache_lives_outside_the_database_in_its_own_file(collecting):
    store.keep_google("x@example.com", REFRESH, google_data.COLLECT_SCOPES)
    tables = {r[0] for r in sqlite3.connect(collecting / "collect.sqlite3").execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"google_accounts", "gmail_messages", "calendar_events", "google_tasks", "runs"} <= tables


class QuotaGoogle(FakeGoogle):
    """Google refusing reads for a while: the per-user quota (403 'Quota exceeded'), or failing outright."""

    def __init__(self, *, quota_refusals=0, fail_on=None):
        super().__init__()
        self.quota_refusals, self.fail_on = quota_refusals, fail_on

    async def __call__(self, method, url, *, headers, params, data):
        if url.startswith(f"{google.GMAIL}/messages/m") and "/attachments/" not in url:
            if self.quota_refusals:
                self.quota_refusals -= 1
                return 403, (b'{"error": {"code": 403, "message": "Quota exceeded for quota metric \'Total Query Cost\' and limit '
                             b'\'Units per minute per user\'", "status": "RESOURCE_EXHAUSTED"}}')
            if self.fail_on and url.endswith(self.fail_on):
                return 500, b'{"error": {"code": 500, "message": "backend error"}}'
        return await super().__call__(method, url, headers=headers, params=params, data=data)


async def test_googles_per_user_quota_is_waited_out_not_given_up(database, family, monkeypatch):
    waited = []

    async def wait(s):
        waited.append(s)
    monkeypatch.setattr(google_data.asyncio, "sleep", wait)
    store.keep_google("amma@example.com", REFRESH, google_data.COLLECT_SCOPES)
    out = await google_data.run("amma@example.com", transport=QuotaGoogle(quota_refusals=3))
    assert out["errors"] == {} and out["counts"]["gmail"] == 2
    assert sorted(w for w in waited if w > 1) == [2, 4, 8]                  # three refusals, each wait twice the last
    assert all(m["body"] is not None for m in store.items("gmail", "amma@example.com"))


async def test_mail_read_before_a_failure_is_kept_and_the_next_run_goes_on_from_there(database, family, monkeypatch):
    async def wait(s):
        return None
    monkeypatch.setattr(google_data.asyncio, "sleep", wait)
    monkeypatch.setattr(google_data, "GMAIL_AT_ONCE", 1)
    store.keep_google("amma@example.com", REFRESH, google_data.COLLECT_SCOPES)
    out = await google_data.run("amma@example.com", transport=QuotaGoogle(fail_on="/m2"))
    assert "gmail" in out["errors"]
    assert [m["id"] for m in store.items("gmail", "amma@example.com")] == ["m1"]                    # kept, not lost
    again = QuotaGoogle()
    await google_data.run("amma@example.com", transport=again)
    assert again.read == ["m2"] and len(store.items("gmail", "amma@example.com")) == 2
