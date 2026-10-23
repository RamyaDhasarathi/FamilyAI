"""The household's rules: a short list of sentences with switches, plus what
the household taught by a tap. A guardian flips a switch; a built-in rule
cannot be flipped; the switch is honoured where the thing happens."""
import datetime as dt
import uuid
from zoneinfo import ZoneInfo

import pytest

from familyos import calendar, digest, notify
from familyos.settings import settings


@pytest.fixture
def sent(monkeypatch):
    out = []

    async def member(member_id, subject, body):
        out.append(member_id)
        return "telegram"

    monkeypatch.setattr(notify, "member", member)
    return out


async def test_the_rules_are_listed_as_sentences_with_what_was_taught(family, database, monkeypatch):
    monkeypatch.setattr(settings, "digest_enabled", True)
    monkeypatch.setattr(settings, "calendar_write_enabled", True)
    await family.client.put("/v1/household/source-schools", headers=family.h("amma"),
                            json={"source_key": "telegram:chat:-1001", "school": "Aachi Global"})
    r = await family.client.get("/v1/household/rules", headers=family.h("paati"))
    assert r.status_code == 200, r.text
    rules = {x["key"]: x for x in r.json()["rules"]}
    assert set(rules) == {"childrens_notices_shared", "weekly_digest", "calendar_follows_decisions", "local_models", "holidays_accepted",
                          "receipts_close_bills", "bills_handed_to", "investments_quiet", "pictures_by_model", "promos_never_obligate", "receipts_feed_meals",
                          "home_place", "work_place", "weather_lines", "travel_time", "public_holidays", "exam_dates"}
    off_by_default = ("local_models", "holidays_accepted", "bills_handed_to", "pictures_by_model", "home_place", "work_place", "weather_lines", "travel_time", "public_holidays", "exam_dates")
    assert all(x["on"] for k, x in rules.items() if k not in off_by_default)
    assert all(x["sentence"].endswith(".") for x in rules.values())
    assert not rules["holidays_accepted"]["on"] and not rules["bills_handed_to"]["on"] and rules["receipts_close_bills"]["on"]
    assert rules["local_models"]["fixed"] and rules["local_models"]["why_fixed"] == "no local model on this deployment"
    assert rules["promos_never_obligate"]["fixed"] and rules["promos_never_obligate"]["why_fixed"] == "built in"
    [learned] = r.json()["learned"]
    assert learned["label"] == "a Telegram group" and "Aachi Global" in learned["says"]


async def test_a_deployment_with_the_feature_off_says_so_instead_of_offering_a_switch(family, database, monkeypatch):
    monkeypatch.setattr(settings, "digest_enabled", False)
    r = await family.client.get("/v1/household/rules", headers=family.h("amma"))
    rule = next(x for x in r.json()["rules"] if x["key"] == "weekly_digest")
    assert rule["fixed"] and not rule["on"] and rule["why_fixed"] == "off for this deployment"


async def test_only_a_guardian_flips_a_switch_and_only_the_named_ones(family, database):
    r = await family.client.put("/v1/household/rules", headers=family.h("paati"), json={"weekly_digest": False})
    assert r.status_code == 403
    r = await family.client.put("/v1/household/rules", headers=family.h("appa"), json={"weekly_digest": False, "promos_never_obligate": False})
    assert r.status_code == 200, r.text
    rules = {x["key"]: x for x in r.json()["rules"]}
    assert rules["weekly_digest"]["on"] is False and rules["promos_never_obligate"]["on"] is True
    row = await database.fetchrow("SELECT detail FROM audit_events WHERE action = 'household.rules_set'")
    assert row["detail"]["set"] == {"weekly_digest": False} and row["detail"]["was"] == {"weekly_digest": True}


async def test_a_household_that_turned_the_digest_off_is_skipped_by_the_sweep_but_can_still_ask_for_one(family, database, sent, monkeypatch):
    monkeypatch.setattr(settings, "digest_enabled", True)
    monkeypatch.setattr(settings, "digest_weekday", 6)
    monkeypatch.setattr(settings, "digest_hour", 8)
    monkeypatch.setattr(settings, "timezone", "Asia/Kolkata")
    await family.client.put("/v1/household/rules", headers=family.h("amma"), json={"weekly_digest": False})
    sunday_9am = dt.datetime(2026, 10, 11, 9, 0, tzinfo=ZoneInfo("Asia/Kolkata"))
    assert (await digest.sweep(sunday_9am))["sent"] == 0 and sent == []
    r = await family.client.post("/v1/digest/send", headers=family.h("amma"))
    assert r.status_code == 200 and r.json()["sent"] and len(sent) == 1


async def test_a_household_that_turned_the_calendar_off_queues_no_write(family, database, monkeypatch):
    monkeypatch.setattr(settings, "calendar_write_enabled", True)
    from tests.test_calendar_write import _obligation
    await family.client.put("/v1/household/rules", headers=family.h("amma"), json={"calendar_follows_decisions": False})
    _, oid = await _obligation(family)
    r = await family.client.post(f"/v1/obligations/{oid}/decision", headers=family.h("amma"), json={"status": "accepted"})
    assert r.status_code == 200, r.text
    assert await database.fetchval("SELECT count(*) FROM jobs WHERE kind = $1", calendar.WRITE_KIND) == 0
    # And a write already queued is not made.
    assert (await calendar.sync_obligation(oid))["skipped"] == "rule_off"


async def test_a_household_that_switched_to_its_own_model_is_read_and_answered_by_it(family, database, monkeypatch):
    """With a model named in settings, a guardian flips the switch and from
    then on the chat, the plans, the chooser and the reader use that model
    through its OpenAI-compatible address. Off again, the cloud one."""
    from familyos import chat
    from familyos.execution import generalist
    from familyos.extraction import pipeline
    monkeypatch.setattr(settings, "local_model", "qwen3:32b")
    monkeypatch.setattr(settings, "local_model_url", "http://localhost:11434/v1")
    monkeypatch.setattr(settings, "extractor", "model")
    monkeypatch.setattr(settings, "openai_api_key", "cloud-key")
    household_id = uuid.UUID(family.household["id"])
    cloud = chat.current_model()
    assert (await chat.model_for(household_id)) is cloud
    r = await family.client.get("/v1/household/rules", headers=family.h("amma"))
    rule = next(x for x in r.json()["rules"] if x["key"] == "local_models")
    assert not rule["fixed"] and not rule["on"] and "qwen3:32b" in rule["sentence"]

    r = await family.client.put("/v1/household/rules", headers=family.h("amma"), json={"local_models": True})
    assert r.status_code == 200, r.text
    own = await chat.model_for(household_id)
    assert own is not cloud and own.name == "local" and own.model == "qwen3:32b" and own._base_url == "http://localhost:11434/v1"
    reader = pipeline.make_extractor(local=await chat.local_models_on(household_id))
    assert reader.name == "local" and reader.model == "local/qwen3:32b" and reader.effort is None and reader._base_url == "http://localhost:11434/v1"
    # The generalist needs a cloud model: it does not run for this household.
    monkeypatch.setattr(settings, "anthropic_api_key", "k")
    monkeypatch.setattr(settings, "errand_generalist", "looks")
    monkeypatch.setattr(settings, "errand_model", "claude-x")
    assert generalist.wants("look", has_runbook=True) and await chat.local_models_on(household_id)

    r = await family.client.put("/v1/household/rules", headers=family.h("amma"), json={"local_models": False})
    assert r.status_code == 200
    assert (await chat.model_for(household_id)) is cloud
    # Without a model named, the switch is not offered and nothing changes.
    monkeypatch.setattr(settings, "local_model", "")
    assert not await chat.local_models_on(household_id) and pipeline.make_extractor().name != "local"


# ----------------------------------------------------------------------------
# standing decisions
# ----------------------------------------------------------------------------

async def _school_notice(family, claims, *, who="amma"):
    """A school's circular, read, with the given claims."""
    from familyos.db import pool
    from familyos.extraction import service
    from familyos.extraction.claims import Extraction, ExtractorInfo
    from tests.conftest import pdf
    r = await family.upload(who, pdf("Circular " + claims[0].title), filename="c.pdf", visibility="shared")
    artifact_id = uuid.UUID(r.json()["artifact"]["id"])
    await pool().execute("UPDATE input_artifacts SET channel = 'gmail', source = $2 WHERE id = $1", artifact_id,
                         {"from": "Aachi Global <office@aachiglobal.edu.in>", "subject": "School circular: " + claims[0].title,
                          "date": dt.date.today().strftime("%a, %d %b %Y 09:00:00 +0530")})
    reading = Extraction(extractor=ExtractorInfo(name="openai", model="openai/x", prompt_version="p", parser_version="p1"),
                         reference_date=dt.date.today(), actionable=True, page_count=1, claims=claims)
    return artifact_id, await service.save(uuid.UUID(family.household["id"]), artifact_id, reading)


def _event(title, on, **kw):
    from familyos.extraction.claims import Claim
    return Claim(kind="event", title=title, date=on, quote=title, location={"page": 1, "start": 0, "end": 5, "match": "exact"}, confidence=0.9, **kw)


async def test_a_holiday_is_accepted_as_it_is_read_when_the_household_said_so(family, database, monkeypatch):
    from familyos.extraction.claims import Claim
    soon = dt.date.today() + dt.timedelta(days=12)
    a1, counts = await _school_notice(family, [_event("Diwali holidays", soon)])
    assert counts["holidays_accepted"] == 0
    assert await database.fetchval("SELECT status FROM obligations WHERE artifact_id = $1", a1) == "proposed"
    r = await family.client.put("/v1/household/rules", headers=family.h("amma"), json={"holidays_accepted": True})
    assert r.status_code == 200
    fee = Claim(kind="deadline", title="Term 2 fee", date=soon, requires=["payment"], quote="fee", location={"page": 1, "start": 0, "end": 3, "match": "exact"}, confidence=0.9)
    a2, counts = await _school_notice(family, [_event("Pongal holidays", soon + dt.timedelta(days=1)), _event("Annual day", soon + dt.timedelta(days=2), requires=["parent_attendance"]), fee])
    assert counts["holidays_accepted"] == 1
    rows = {r["title"]: (r["status"], r["decided_by"]) for r in await database.fetch("SELECT title, status, decided_by FROM obligations WHERE artifact_id = $1", a2)}
    assert rows["Pongal holidays"] == ("accepted", None) and rows["Annual day"][0] == "proposed" and rows["Term 2 fee"][0] == "proposed"
    assert await database.fetchval("SELECT detail->>'rule' FROM audit_events WHERE action = 'obligation.accepted' AND target_id = (SELECT id FROM obligations WHERE title = 'Pongal holidays')") == "holidays_accepted"
    # Not a school's notice: a "holiday" in a shop's mail is asked as before.
    from familyos.db import pool
    a3, counts = await _school_notice(family, [_event("Holiday sale closure", soon)])
    await pool().execute("UPDATE input_artifacts SET source = source || '{\"from\": \"deals@amazon.in\"}'::jsonb WHERE id = $1", a3)


async def test_a_bill_is_handed_to_the_adult_the_household_named(family, database, monkeypatch):
    from familyos import notify
    from familyos.extraction.claims import Amount, Claim
    told = []
    async def member(member_id, subject, body): told.append((member_id, subject))
    return "test"
    monkeypatch.setattr(notify, "member", member)
    r = await family.client.put("/v1/household/rules", headers=family.h("amma"), json={"bills_handed_to": family.older["id"]})
    assert r.status_code == 403                                  # a child cannot be handed bills
    r = await family.client.put("/v1/household/rules", headers=family.h("amma"), json={"bills_handed_to": family.appa["id"]})
    assert r.status_code == 200, r.text
    rule = next(x for x in r.json()["rules"] if x["key"] == "bills_handed_to")
    assert rule["on"] and rule["member_id"] == family.appa["id"] and "Appa" in rule["sentence"] and {o["name"] for o in rule["options"]} >= {"Amma", "Appa", "Paati"}
    bill = Claim(kind="deadline", title="Pay the Airtel bill", date=dt.date.today() + dt.timedelta(days=9), requires=["payment"],
                 amount=Amount(value=1940.98, currency="INR"), quote="Pay by", location={"page": 1, "start": 0, "end": 3, "match": "exact"}, confidence=0.9)
    a1, counts = await _school_notice(family, [bill])
    assert counts["handed_to"] == family.appa["id"]
    row = await database.fetchrow("SELECT assigned_to, assigned_by, assigned_note FROM input_artifacts WHERE id = $1", a1)
    assert row["assigned_to"] == uuid.UUID(family.appa["id"]) and row["assigned_by"] is None and "bills go to Appa" in row["assigned_note"]
    assert told and told[0][0] == uuid.UUID(family.appa["id"]) and told[0][1].startswith("A bill for you")
    # Nobody again: the next bill waits for a hand.
    r = await family.client.put("/v1/household/rules", headers=family.h("amma"), json={"bills_handed_to": None})
    assert not next(x for x in r.json()["rules"] if x["key"] == "bills_handed_to")["on"]
    a2, counts = await _school_notice(family, [Claim(kind="deadline", title="Pay the Jio bill", date=dt.date.today() + dt.timedelta(days=9), requires=["payment"],
                                                     amount=Amount(value=599, currency="INR"), quote="Pay by", location={"page": 1, "start": 0, "end": 3, "match": "exact"}, confidence=0.9)])
    assert counts["handed_to"] is None and await database.fetchval("SELECT assigned_to FROM input_artifacts WHERE id = $1", a2) is None


async def test_receipts_settling_bills_is_a_switch(family, database, monkeypatch):
    from tests.test_loops import _bill, _receipt_for
    r = await family.client.put("/v1/household/rules", headers=family.h("amma"), json={"receipts_close_bills": False})
    assert r.status_code == 200
    bill = await _bill(family)
    _, counts = await _receipt_for(family)
    assert counts["loops_closed"] == [] and await database.fetchval("SELECT handled_at FROM input_artifacts WHERE id = $1", bill) is None
    await family.client.put("/v1/household/rules", headers=family.h("amma"), json={"receipts_close_bills": True})
    _, counts = await _receipt_for(family, subject="Thank you for your payment, Airtel")
    assert counts["loops_closed"] == [str(bill)]


async def test_investment_mail_asks_nothing_until_the_household_says_otherwise(family, database):
    """A postal-ballot notice from the depository: filed in Investments,
    nothing proposed. Off, its e-vote date is proposed like any other; on
    again, what was waiting is filed."""
    from familyos.db import pool
    from familyos.extraction.claims import Claim
    deadline = Claim(kind="deadline", title="Cast remote e-vote", date=dt.date.today() + dt.timedelta(days=9), quote="e-voting ends",
                     location={"page": 1, "start": 0, "end": 5, "match": "exact"}, confidence=0.9, optional=True)
    a1, counts = await _school_notice(family, [deadline])
    await pool().execute("UPDATE input_artifacts SET source = source || $2::jsonb WHERE id = $1", a1, {"from": "NSDL <evoting@nsdl.com>"})
    from familyos.extraction import service
    from familyos.extraction.claims import Extraction, ExtractorInfo
    reading = Extraction(extractor=ExtractorInfo(name="openai", model="openai/x", prompt_version="p", parser_version="p1"),
                         reference_date=dt.date.today(), actionable=True, page_count=1, claims=[deadline])
    counts = await service.save(uuid.UUID(family.household["id"]), a1, reading)
    assert counts["category"] == "trading" and counts["obligations"] == 0 and counts["records_kept"] == 1
    r = await family.client.put("/v1/household/rules", headers=family.h("amma"), json={"investments_quiet": False})
    assert r.status_code == 200
    counts = await service.save(uuid.UUID(family.household["id"]), a1, reading)
    assert counts["obligations"] == 1
    oid = await database.fetchval("SELECT id FROM obligations WHERE artifact_id = $1 AND superseded_at IS NULL", a1)
    r = await family.client.put("/v1/household/rules", headers=family.h("amma"), json={"investments_quiet": True})
    assert await database.fetchval("SELECT status FROM obligations WHERE id = $1", oid) == "dismissed"
    assert await database.fetchval("SELECT detail->>'rule' FROM audit_events WHERE action = 'obligation.dismissed' AND target_id = $1", oid) == "investments_quiet"
