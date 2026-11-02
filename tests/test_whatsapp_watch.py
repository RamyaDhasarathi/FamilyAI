"""Reading the chats a member names from their own WhatsApp Web: consent first, only named chats, each message once, a lapsed link said once."""
import uuid

import pytest

from familyos import whatsapp_watch as ww
from familyos.db import pool
from familyos.execution import whatsapp_reader as wr
from familyos.identity import Invalid, NotAllowed, Principal
from familyos.settings import settings

PHONE = "919800000001"


class FakeReader:
    def __init__(self):
        self.messages: list[wr.Message] = []
        self.linked_now = False
        self.lapsed = False
        self.asked: list[list[str]] = []
        self.forgotten = False
        self.ambiguous: list[str] = []

    async def start_link(self, member_id, phone):
        return {"linked": False, "code": "ABCD-1234", "expires_in": 180}

    async def linked(self, member_id):
        return self.linked_now

    async def read(self, member_id, chats, known=None):
        self.asked.append(list(chats))
        if self.lapsed:
            raise wr.NeedsLink("WhatsApp Web asks to be linked again")
        return wr.Read(messages=[m for m in self.messages if m.chat in chats and m.chat not in self.ambiguous],
                       missing=[c for c in chats if c not in {m.chat for m in self.messages} and c not in self.ambiguous],
                       ambiguous=[c for c in chats if c in self.ambiguous])

    async def forget(self, member_id):
        self.forgotten = True


def msg(i, chat="Class 2 Parents", text="Sports day moved to 28 November. Send the form by 21 November."):
    return wr.Message(chat=chat, id=f"true_120363@g.us_{i}_9199", stamp="[10:09, 14/10/2026]", author="Priya", text=text, is_group=True)


@pytest.fixture
def reader(monkeypatch):
    fake = FakeReader()
    monkeypatch.setattr(settings, "whatsapp_watch_enabled", True)
    wr.use_reader(fake)
    yield fake
    wr.use_reader(wr.NoReader())


def _p(family, who="amma"):
    m = getattr(family, who)
    return Principal(member_id=uuid.UUID(m["id"]), household_id=uuid.UUID(family.household["id"]), role=m["role"], display_name=m["display_name"])


async def _ready(family, reader, chats=("Class 2 Parents",)):
    p = _p(family)
    await pool().execute("UPDATE members SET phone = $2 WHERE id = $1", p.member_id, PHONE)
    await ww.set_chats(p, list(chats))
    out = await ww.start_link(p)
    assert out["code"] == "ABCD-1234"
    reader.linked_now = True
    assert (await ww.check_link(p))["status"] == "linked"
    await ww.enable(p, understood=True, cloud_ok=True)
    return p


async def test_it_is_off_for_a_deployment_that_has_not_switched_it_on(family, monkeypatch):
    monkeypatch.setattr(settings, "whatsapp_watch_enabled", False)      # .env may switch it on for the person running the suite
    with pytest.raises(Invalid):
        await ww.set_chats(_p(family), ["Class 2 Parents"])
    assert (await ww.status(_p(family)))["available"] is False


async def test_it_needs_chats_a_link_and_a_yes_to_the_costs_and_to_a_hosted_model(family, reader):
    p = _p(family)
    await pool().execute("UPDATE members SET phone = $2 WHERE id = $1", p.member_id, PHONE)
    with pytest.raises(Invalid):
        await ww.enable(p, understood=True)                      # no chats
    await ww.set_chats(p, ["Class 2 Parents"])
    with pytest.raises(Invalid):
        await ww.enable(p, understood=True)                      # not linked
    await ww.start_link(p)
    reader.linked_now = True
    await ww.check_link(p)
    with pytest.raises(Invalid):
        await ww.enable(p, understood=False)                     # costs not accepted
    with pytest.raises(Invalid, match="hosted"):
        await ww.enable(p, understood=True)                      # the notice model is a hosted one: its own yes
    out = await ww.enable(p, understood=True, cloud_ok=True)
    assert out["enabled"] is True and out["status"] == "linked" and len(out["consent"]) == 5


async def test_a_link_needs_the_members_phone_number(family, reader):
    with pytest.raises(Invalid, match="phone"):
        await ww.start_link(_p(family))


async def test_only_named_chats_are_asked_for_and_each_message_is_taken_once(family, reader):
    p = await _ready(family, reader)
    reader.messages = [msg(1), msg(2, text="Picnic is on 5 December"), msg(3, chat="Family jokes", text="lol")]
    first = await ww.run_for(p.member_id)
    assert reader.asked == [["Class 2 Parents"]] and first["read"] == 2 and first["taken"] == 2
    again = await ww.run_for(p.member_id)
    assert again["read"] == 2 and again["taken"] == 0            # the same messages are not stored twice
    rows = await pool().fetch("SELECT source FROM input_artifacts WHERE channel = 'whatsapp'")
    assert len(rows) == 2 and all("Class 2 Parents" in str(r["source"]) for r in rows)
    reader.messages.append(msg(4, text="Bring a hat on 6 December"))
    assert (await ww.run_for(p.member_id))["taken"] == 1


async def test_a_named_chat_that_is_not_on_the_account_is_said_not_guessed(family, reader):
    p = await _ready(family, reader, chats=("Nonexistent chat",))
    out = await ww.run_for(p.member_id)
    assert out["missing"] == ["Nonexistent chat"]
    assert "not found" in (await ww.status(p))["last_error"]


async def test_a_chat_name_two_chats_answer_to_is_not_read_and_is_said(family, reader):
    p = await _ready(family, reader)
    reader.messages = [msg(1)]
    reader.ambiguous = ["Class 2 Parents"]                        # a lookalike group with the same name exists
    out = await ww.run_for(p.member_id)
    assert out["read"] == 0 and out["taken"] == 0 and out["ambiguous"] == ["Class 2 Parents"] and out["missing"] == []
    assert "more than one chat" in (await ww.status(p))["last_error"]


async def test_a_lapsed_link_is_said_once_and_the_sweep_leaves_it_alone(family, reader, monkeypatch):
    told = []

    async def member(member_id, subject, body, buttons=None):
        told.append(subject)
        return "telegram"

    monkeypatch.setattr(ww.notify, "member", member)
    p = await _ready(family, reader)
    reader.lapsed = True
    assert (await ww.run_for(p.member_id)) == {"lapsed": True}
    assert (await ww.status(p))["status"] == "lapsed"
    reader.asked.clear()
    assert (await ww.sweep())["members"] == 0 and reader.asked == []     # not read again until relinked
    assert told == ["WhatsApp needs linking again"]


async def test_forget_deletes_the_browser_and_the_settings(family, reader):
    p = await _ready(family, reader)
    out = await ww.forget(p)
    assert reader.forgotten and out["enabled"] is False and out["chats"] == []
    assert await pool().fetchval("SELECT count(*) FROM whatsapp_watches") == 0


async def test_children_cannot_link_and_the_chat_list_is_capped(family, reader):
    with pytest.raises(NotAllowed):
        await ww.set_chats(_p(family, "older"), ["x"])
    with pytest.raises(Invalid):
        wr.clean_chats([f"chat {i}" for i in range(9)])
    assert wr.clean_chats(["  Class  2 Parents ", "class 2 parents", ""]) == ["Class 2 Parents"]


def test_whatsapps_own_timestamp_line_is_split_into_stamp_and_author():
    assert wr.parse_pre_plain("[10:09, 14/10/2026] Emily Carter: ") == ("[10:09, 14/10/2026]", "Emily Carter")
    assert wr.parse_pre_plain("nonsense") == ("", "")


async def test_the_http_surface_needs_the_switch_and_returns_the_costs(family, reader):
    h = family.h("amma")
    got = await family.client.get("/v1/me/whatsapp", headers=h)
    assert got.status_code == 200 and got.json()["available"] is True and len(got.json()["consent"]) == 5
    assert (await family.client.put("/v1/me/whatsapp/chats", headers=h, json={"chats": ["Class 2 Parents"]})).status_code == 200
    assert (await family.client.post("/v1/me/whatsapp/link", headers=h)).status_code in (400, 422)       # no phone number yet


async def test_telegram_whatsapp_shows_status_and_a_tap_gets_the_link_code(family, reader, monkeypatch):
    from familyos.intake import telegram
    from tests.test_telegram import BOT, CHAT, SECRET, _linked, post, update
    said = []

    async def send(chat_id, text, **kw):
        said.append(text)

    async def noop(*a, **k):
        return None

    monkeypatch.setattr(telegram, "send_message", send)
    monkeypatch.setattr(telegram, "answer_callback", noop)
    monkeypatch.setattr(telegram, "edit_message", noop)
    monkeypatch.setattr(settings, "telegram_webhook_secret", SECRET)
    monkeypatch.setattr(settings, "telegram_bot_token", "7:TESTTOKEN")
    monkeypatch.setattr(settings, "telegram_bot_username", BOT)
    await _linked(family)
    p = _p(family)
    await pool().execute("UPDATE members SET phone = $2 WHERE id = $1", p.member_id, PHONE)
    assert (await post(family, update(text="/whatsapp", forwarded=False))).json()["command"] == "whatsapp"
    assert "WhatsApp: off" in said[-1]
    press = {"update_id": 21, "callback_query": {"id": "c", "from": {"id": CHAT, "is_bot": False}, "data": "wa:link",
                                                "message": {"message_id": 5, "chat": {"id": CHAT, "type": "private"}}}}
    assert (await post(family, press)).json()["whatsapp"] == "link"
    assert "ABCD-1234" in said[-1]


async def test_a_member_sets_their_own_phone_number_once_per_number(family):
    h = family.h("amma")
    ok = await family.client.put("/v1/me/phone", headers=h, json={"phone": "+91 98765 43210"})
    assert ok.status_code == 200 and ok.json()["phone"].endswith("9876543210")
    assert (await family.client.put("/v1/me/phone", headers=family.h("paati"), json={"phone": "+91 98765 43210"})).status_code in (400, 422)
    assert (await family.client.put("/v1/me/phone", headers=h, json={"phone": "12"})).status_code in (400, 422)


def test_a_country_row_gives_its_dial_code_and_the_selected_one_gives_none():
    assert wr.code_of("India\n+91") == ("India", "91")
    assert wr.code_of("United Arab Emirates\nالإمارات العربية المتحدة\n+971") == ("United Arab Emirates", "971")
    assert wr.code_of("India") == ("India", None)
    assert wr.code_of("") == ("", None)


async def test_a_guardian_says_which_school_a_chat_belongs_to_and_only_a_guardian(family, reader):
    from familyos import origin
    await pool().execute("UPDATE members SET school = 'Bright Start' WHERE id = $1", uuid.UUID(family.older["id"]))
    p = _p(family)                                         # amma is a guardian
    out = await ww.set_chats(p, ["Class 2 Parents"], {"Class 2 Parents": "Bright Start"})
    assert out["tags"] == {"Class 2 Parents": "Bright Start"} and out["schools"][0]["school"] == "Bright Start"
    async with pool().acquire() as conn:
        assert await origin.school_for(conn, p.household_id, "whatsapp:group:class 2 parents") == "Bright Start"
    with pytest.raises(Invalid):
        await ww.set_chats(p, ["Class 2 Parents"], {"Class 2 Parents": "Nowhere School"})
    out = await ww.set_chats(p, ["Class 2 Parents"], {"Class 2 Parents": ""})
    assert out["tags"] == {}
    with pytest.raises(NotAllowed):
        await ww.set_chats(Principal(member_id=p.member_id, household_id=p.household_id, role="adult", display_name="x"), ["A"], {"A": "Bright Start"})


async def test_a_picture_in_a_named_chat_reaches_intake_as_media_with_the_chat_in_its_source(family, reader):
    import base64

    p = await _ready(family, reader)
    png = base64.b64encode(b"\x89PNG\r\n\x1a\n" + b"x" * 64).decode()
    m = msg(7, text="")
    m.media_b64, m.media_type = png, "image/png"
    reader.messages = [m]
    out = await ww.run_for(p.member_id)
    assert out["read"] == 1
    kids = await pool().fetch("SELECT media_type, source FROM input_artifacts WHERE channel = 'whatsapp_media'")
    assert len(kids) == 1 and kids[0]["media_type"] == "image/png" and "Class 2 Parents" in str(kids[0]["source"])
    assert (await ww.run_for(p.member_id))["taken"] == 0               # the same picture is not taken twice


async def test_consent_follows_the_model_that_reads_the_chats_not_the_one_at_the_time_of_yes(family, reader, monkeypatch):
    import json as _json
    monkeypatch.setattr(settings, "model_profiles", _json.dumps([{"name": "tee", "kind": "openai_compatible", "base_url": "https://llm.family.example/v1", "model": "q", "trust": "own"}]))
    p = _p(family)
    await pool().execute("UPDATE members SET phone = $2 WHERE id = $1", p.member_id, PHONE)
    h = family.h("amma")
    assert (await family.client.put("/v1/household/models", headers=h, json={"extraction": "tee", "ask": "tee"})).status_code == 200
    await ww.set_chats(p, ["Class 2 Parents"])
    await ww.start_link(p)
    reader.linked_now = True
    await ww.check_link(p)
    await ww.enable(p, understood=True)                                  # a private model reads it: no hosted yes was asked for or given
    reader.messages = [msg(1)]
    assert (await ww.run_for(p.member_id))["taken"] == 1
    # the household later moves its notices to a hosted model: the earlier yes does not cover that
    assert (await family.client.put("/v1/household/models", headers=h, json={"extraction": "default", "ask": "default"})).status_code == 200
    assert not await ww.destination_ok(p.household_id, p.member_id)
    reader.messages = [msg(1), msg(2, text="Picnic on 5 December")]
    assert (await ww.run_for(p.member_id)) == {"paused": "consent"}
    assert "hosted" in (await ww.status(p))["last_error"]
    # a message already stored (or queued) before the change is not sent to the hosted model either
    from familyos import jobs
    from familyos.intake import gateway, wa_bridge
    payload = _payload_for(msg(9, text="Fees due on 20 November"), p)
    parsed, extra = wa_bridge.parse(payload)
    stored = await gateway.receive_whatsapp(parsed, extra_source={**extra, "via": "whatsapp_watch"})
    job_id = await pool().fetchval("SELECT id::text FROM jobs WHERE kind = 'extract_artifact' AND spec->>'artifact_id' = $1", str(stored[0][0]["id"]))
    done = await jobs.attach(job_id)
    assert "waiting for consent" in str(done)


def _payload_for(m, p):
    return ww._payload(m, PHONE)


def test_a_whatsapp_time_is_read_in_the_accounts_own_order_which_is_learned_from_the_data_never_guessed():
    mdy = ["[13:11, 8/29/2026]", "[09:14, 9/1/2026]"]
    assert wr.date_order(mdy) == "mdy" and wr.date_order(["[10:00, 29/08/2026]"]) == "dmy"
    assert wr.date_order(["[09:14, 9/1/2026]"]) is None                       # every stamp ambiguous: unknown
    assert wr.parse_stamp("[09:14, 9/1/2026]", "Asia/Kolkata", "mdy") == "2026-09-01T09:14:00+05:30"
    assert wr.parse_stamp("[09:14, 9/1/2026]", "Asia/Kolkata", "dmy") == "2026-01-09T09:14:00+05:30"
    assert wr.parse_stamp("[09:14, 9/1/2026]", "Asia/Kolkata") is None        # ambiguous and no order known: refused
    assert wr.parse_stamp("[13:11, 8/29/2026]", "Asia/Kolkata") == "2026-08-29T13:11:00+05:30"   # unambiguous by itself
    assert wr.parse_stamp("[4:05 pm, 29/10/2026]", "Asia/Kolkata") == "2026-10-29T16:05:00+05:30"
    assert wr.parse_stamp("[16:59, 31/02/2026]") is None and wr.parse_stamp("yesterday") is None


async def test_a_message_from_two_days_ago_is_read_against_its_own_day_not_the_day_it_was_imported(family):
    import datetime as dt

    from familyos.extraction.service import reference_date
    art = {"source": {"sent_at": "2026-10-14T09:00:00+05:30"}, "received_at": dt.datetime(2026, 10, 16, 12, 0, tzinfo=dt.UTC)}
    assert reference_date(art) == dt.date(2026, 10, 14)
    assert reference_date({"source": {}, "received_at": art["received_at"]}) == dt.date(2026, 10, 16)


async def test_erasing_a_household_removes_a_members_linked_browser_profile(family, database, tmp_path, monkeypatch):
    from familyos import erasure
    monkeypatch.setattr(settings, "whatsapp_profile_dir", str(tmp_path))
    p = _p(family)
    folder = wr.profile_dir(p.member_id)
    folder.mkdir(parents=True)
    (folder / "Default").write_text("session")
    wr.use_reader(wr.NoReader())                                         # even with reading switched off, the folder is a credential on disk
    assert await erasure._forget_browsers(p.household_id) >= 1
    assert not folder.exists()


async def test_paused_reading_resumes_through_the_same_yes_and_the_card_says_so(family, reader, monkeypatch):
    import json as _json
    monkeypatch.setattr(settings, "model_profiles", _json.dumps([{"name": "tee", "kind": "openai_compatible", "base_url": "https://llm.family.example/v1", "model": "q", "trust": "own"}]))
    p = _p(family)
    await pool().execute("UPDATE members SET phone = $2 WHERE id = $1", p.member_id, PHONE)
    h = family.h("amma")
    await family.client.put("/v1/household/models", headers=h, json={"extraction": "tee", "ask": "tee"})
    await ww.set_chats(p, ["Class 2 Parents"])
    await ww.start_link(p)
    reader.linked_now = True
    await ww.check_link(p)
    await ww.enable(p, understood=True)
    await family.client.put("/v1/household/models", headers=h, json={"extraction": "default", "ask": "default"})
    reader.messages = [msg(1)]
    assert await ww.run_for(p.member_id) == {"paused": "consent"}
    st = await ww.status(p)
    assert st["status"] == "linked" and st["enabled"] and st["needs_consent"]            # connection fine, consent stale: not an error state
    with pytest.raises(Invalid, match="hosted"):
        await ww.enable(p, understood=True)                                               # the renewed yes must cover the hosted model
    out = await ww.enable(p, understood=True, cloud_ok=True)
    assert not out["needs_consent"]
    assert (await ww.run_for(p.member_id))["taken"] == 1


async def test_a_picture_inherits_its_messages_time_and_an_undated_message_is_marked_uncertain_not_today(family, reader):
    import base64
    p = await _ready(family, reader)
    await pool().execute("UPDATE whatsapp_watches SET cursors = '{}'::jsonb WHERE member_id = $1", p.member_id)
    pic = msg(7, text="")
    pic.stamp = "[09:14, 29/09/2026]"                                      # unambiguous: a 29
    pic.media_b64, pic.media_type = base64.b64encode(b"\x89PNG\r\n\x1a\n" + b"x" * 64).decode(), "image/png"
    undated = msg(8, text="Meeting tomorrow")
    undated.stamp = "[09:14, 3/4/2026]"                                      # ambiguous, and no order learned from this pass
    reader.messages = [pic]
    await ww.run_for(p.member_id)
    await pool().execute("UPDATE whatsapp_watches SET cursors = '{}'::jsonb WHERE member_id = $1", p.member_id)      # forget the order learned from the 29
    reader.messages = [undated]
    await ww.run_for(p.member_id)
    child = await pool().fetchrow("SELECT source FROM input_artifacts WHERE channel = 'whatsapp_media'")
    assert "2026-09-29" in str(child["source"]["sent_at"] if isinstance(child["source"], dict) else child["source"])
    rows = await pool().fetch("SELECT source FROM input_artifacts WHERE channel = 'whatsapp' AND source->>'chat_name' = 'Class 2 Parents'")
    assert any("sent_at_unknown" in str(r["source"]) for r in rows)


async def test_a_locked_household_is_not_read_at_all(family, reader):
    from familyos import familykey
    from tests.test_familykey import _enable
    p = await _ready(family, reader)
    await _enable(family)
    familykey._unlocked.clear()                                            # locked: the key is not in memory
    reader.messages = [msg(1)]
    reader.asked.clear()
    assert await ww.run_for(p.member_id) == {"paused": "locked"}
    assert reader.asked == []                                              # no chat was opened, so nothing was marked read for the sender


async def test_the_status_card_survives_a_model_choice_below_the_floor(family, reader, monkeypatch):
    import json as _json
    monkeypatch.setattr(settings, "model_profiles", _json.dumps([{"name": "tee", "kind": "openai_compatible", "base_url": "https://llm.family.example/v1", "model": "q", "trust": "own"}]))
    p = await _ready(family, reader)
    await family.client.put("/v1/household/models", headers=family.h("amma"), json={"extraction": "tee", "ask": "tee", "floor": "own"})
    monkeypatch.setattr(settings, "model_profiles", "")                    # the profile is gone: the household's own choice can no longer be resolved
    out = await ww.status(p)
    assert out["model"] is None and out["needs_consent"] is True
