"""Caring for a parent from far away: the scam guard, the circle's roles, the
constitution in sentences, and one person's care view."""
import datetime as dt
import uuid

import pytest

from familyos import brief, clock, documents, notify, scamguard
from familyos.db import pool
from familyos.extraction import service
from familyos.extraction.claims import Claim, Extraction, ExtractorInfo
from familyos.identity import Principal
from tests.conftest import pdf

GROUNDED = {"page": 1, "start": 0, "end": 16, "boxes": [[60.0, 78.0, 300.0, 93.0]], "match": "exact"}
TODAY = clock.today()
TOMORROW = TODAY + dt.timedelta(days=1)

SCAM = ("This is CBI officer. A parcel in your name has drugs. You are under digital arrest. Stay on the video call and do not tell anyone. "
        "Transfer Rs 50000 to the RBI safe account for verification immediately.")
GENUINE_OTP = "123456 is your OTP for a transaction of INR 500 at Amazon. Do not share this OTP with anyone. The bank never asks for your OTP."
SCHOOL = "Dear parents, the PTM is on Friday at 4 pm. Kindly adhere to the slots. Please pay the term fee by the 16th."


def _p(family, who="amma"):
    m = getattr(family, who)
    return Principal(member_id=uuid.UUID(m["id"]), household_id=uuid.UUID(family.household["id"]), role=m["role"], display_name=m["display_name"])


def _read(title="Pay the verification amount"):
    return Extraction(extractor=ExtractorInfo(name="openai", model="openai/x", prompt_version="p", parser_version="p1"),
                      reference_date=TODAY, actionable=True, page_count=1,
                      claims=[Claim(kind="payment", title=title, date=TOMORROW, quote="Transfer", location=GROUNDED, confidence=0.9)])


@pytest.fixture
def told(monkeypatch):
    sent = []
    async def member(member_id, subject, body):
        sent.append((str(member_id), subject, body))
        return "test"
    monkeypatch.setattr(notify, "member", member)
    return sent


async def _notice(family, text, *, visibility="shared", who="amma", channel="share", source=None):
    r = await family.upload(who, pdf(text[:20]), filename="m.pdf", visibility=visibility)
    artifact_id = uuid.UUID(r.json()["artifact"]["id"])
    await pool().execute("UPDATE input_artifacts SET channel = $2, source = $3 WHERE id = $1", artifact_id, channel, source or {"via": "share"})
    return artifact_id


# ----------------------------------------------------------------------------
# the scam guard
# ----------------------------------------------------------------------------

def test_a_scam_is_read_for_its_shape_and_a_real_bank_message_is_not():
    high = scamguard.assess(SCAM)
    assert high["level"] == "high" and any("digital arrest" in r for r in high["reasons"])
    assert any("1930" in a for a in high["advice"]) and any("OTP" in a for a in high["advice"])
    assert scamguard.assess("Dear customer your KYC is expired and the account will be blocked today. Click http://bit.ly/x1 and share your OTP now.")["level"] == "high"
    assert scamguard.assess("Hi Mom this is my new number, lost my phone. Please send money urgently, will explain later")["level"] == "medium"
    # A genuine OTP message says never to share it; a bank's own KYC mail says it will never ask.
    assert scamguard.assess(GENUINE_OTP) is None
    assert scamguard.assess("Please update your KYC at your nearest branch. We will never ask for OTP, PIN or CVV over call or email.",
                            channel="gmail", source={"from": "alerts@hdfcbank.bank.in", "sender_authenticated": True}, category="banking") is None
    assert scamguard.assess(SCHOOL) is None and scamguard.assess("hi") is None
    # Outside India the advice does not name an Indian helpline.
    assert not any("1930" in a for a in scamguard.advice("high", "GB"))


async def test_a_scam_proposes_nothing_is_on_the_brief_and_tells_the_guardians_once(family, database, told):
    household_id = uuid.UUID(family.household["id"])
    artifact_id = await _notice(family, SCAM)
    counts = await service.save(household_id, artifact_id, _read(), text=SCAM)
    assert await database.fetchval("SELECT count(*) FROM obligations WHERE artifact_id = $1", artifact_id) == 0
    assert counts["documents"] == 0
    kept = await database.fetchrow("SELECT suspicion FROM input_artifacts WHERE id = $1", artifact_id)
    assert kept["suspicion"]["level"] == "high" and kept["suspicion"]["alerted"] is True
    reason = await database.fetchval("SELECT non_actionable_reason FROM extractions WHERE artifact_id = $1 AND superseded_at IS NULL", artifact_id)
    assert reason.startswith("This looks like a scam")
    # Both guardians were told, once; a second reading tells nobody again.
    assert sorted(t[0] for t in told) == sorted([family.amma["id"], family.appa["id"]])
    assert "scam" in told[0][1] and "1930" in told[0][2]
    await service.save(household_id, artifact_id, _read(), text=SCAM)
    assert len(told) == 2
    # It leads the brief, as a warning and not a task.
    b = await brief.today(_p(family), limit=10)
    first = b["items"][0]
    assert first["reason"] == "scam" and first["title"].startswith("Looks like a scam") and first["artifact_id"] == artifact_id
    assert b["counts"]["scam"] == 1
    # And is in the Inbox with its reading.
    row = next(r for r in (await family.client.get("/v1/inbox", headers=family.h("amma"))).json() if r["id"] == str(artifact_id))
    assert row["suspicion"]["level"] == "high"
    # Dealing with it takes it off the brief.
    await family.client.post(f"/v1/artifacts/{artifact_id}/handled", headers=family.h("amma"), json={"note": "told Appa not to answer"})
    assert (await brief.today(_p(family), limit=10))["counts"]["scam"] == 0


async def test_a_genuine_notice_is_read_as_usual_and_the_switch_turns_the_guard_off(family, database, told):
    household_id = uuid.UUID(family.household["id"])
    artifact_id = await _notice(family, GENUINE_OTP)
    await service.save(household_id, artifact_id, _read("Pay the term fee"), text=GENUINE_OTP)
    assert await database.fetchval("SELECT count(*) FROM obligations WHERE artifact_id = $1", artifact_id) == 1
    assert await database.fetchval("SELECT suspicion FROM input_artifacts WHERE id = $1", artifact_id) is None and told == []
    r = await family.client.put("/v1/household/rules", headers=family.h("amma"), json={"scam_guard": False})
    assert r.status_code == 200 and next(x for x in r.json()["rules"] if x["key"] == "scam_guard")["on"] is False
    second = await _notice(family, SCAM)
    await service.save(household_id, second, _read(), text=SCAM)
    assert await database.fetchval("SELECT suspicion FROM input_artifacts WHERE id = $1", second) is None
    assert await database.fetchval("SELECT count(*) FROM obligations WHERE artifact_id = $1", second) == 1


async def test_a_reported_call_is_filed_read_and_always_answered(family, database, told):
    r = await family.client.post("/v1/scam/reports", headers=family.h("amma"),
                                 json={"text": SCAM, "caller": "+91 98xxxxxx", "about_member_id": family.paati["id"]})
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["level"] == "high" and body["reasons"] and any("1930" in a for a in body["advice"])
    filed = await database.fetchrow("SELECT visibility, suspicion, note FROM input_artifacts WHERE id = $1", uuid.UUID(body["artifact_id"]))
    assert filed["visibility"] == "shared" and filed["suspicion"]["level"] == "high" and filed["note"] == "reported as suspicious"
    assert await database.fetchval("SELECT member_id FROM artifact_subjects WHERE artifact_id = $1", uuid.UUID(body["artifact_id"])) == uuid.UUID(family.paati["id"])
    assert len(told) == 2
    # A call that matches nothing still gets the one thing worth saying.
    r = await family.client.post("/v1/scam/reports", headers=family.h("paati"), json={"text": "Somebody rang and asked for my son by name, then hung up"})
    assert r.status_code == 201 and r.json()["level"] == "none" and any("OTP" in a for a in r.json()["advice"])
    assert (await family.client.post("/v1/scam/reports", headers=family.h("amma"), json={"text": "x" * 4})).status_code == 422


# ----------------------------------------------------------------------------
# the circle's roles
# ----------------------------------------------------------------------------

async def test_a_caregiver_sees_only_what_is_handed_to_them(family, database):
    household_id = uuid.UUID(family.household["id"])
    shared = await _notice(family, "Electricity bill for the house", visibility="shared")
    paati = family.h("paati")
    # An adult sees what the household shares ...
    assert any(a["id"] == str(shared) for a in (await family.client.get("/v1/artifacts", headers=paati)).json())
    # ... until a guardian makes them the caregiver.
    r = await family.client.put(f"/v1/members/{family.paati['id']}/circle-role", headers=family.h("amma"), json={"circle_role": "caregiver"})
    assert r.status_code == 200 and r.json()["circle_role"] == "caregiver"
    assert not any(a["id"] == str(shared) for a in (await family.client.get("/v1/artifacts", headers=paati)).json())
    assert (await family.client.get(f"/v1/artifacts/{shared}", headers=paati)).status_code == 404
    assert (await family.client.get("/v1/plans", headers=paati)).json() == []
    assert (await family.client.get("/v1/errands", headers=paati)).json() == []
    # To-dos: only their own.
    await family.client.post("/v1/todos", headers=family.h("amma"), json={"title": "Buy the household's groceries"})
    await family.client.post("/v1/todos", headers=family.h("amma"), json={"title": "Give Amma her tablets", "assigned_to": family.paati["id"]})
    titles = {t["title"] for t in (await family.client.get("/v1/todos", headers=paati)).json()}
    assert titles == {"Give Amma her tablets"}
    # What a guardian hands them, they see: the appointment, never the notice it came from.
    artifact_id = uuid.UUID((await family.upload("amma", pdf("clinic"))).json()["artifact"]["id"])
    xid, cid, oid = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    await database.execute("INSERT INTO extractions (id, household_id, artifact_id, extractor, prompt_version, parser_version, actionable, page_count) "
                           "VALUES ($1, $2, $3, 'rules', 'v1', 'v1', TRUE, 1)", xid, household_id, artifact_id)
    await database.execute("INSERT INTO claims (id, extraction_id, household_id, artifact_id, ordinal, kind, title, quote, confidence) "
                           "VALUES ($1, $2, $3, $4, 0, 'event', 'Cardiology appointment', 'the words', 0.9)", cid, xid, household_id, artifact_id)
    await database.execute("INSERT INTO obligations (id, household_id, artifact_id, claim_id, subject_member_id, kind, action, title, due_date, status) "
                           "VALUES ($1, $2, $3, $4, $5, 'task', 'attend', 'Cardiology appointment', $6, 'accepted')", oid, household_id, artifact_id, cid,
                           uuid.UUID(family.paati["id"]), TOMORROW)
    assert "Cardiology appointment" not in {i["title"] for i in (await brief.today(_p(family, "paati"), limit=50))["items"]}
    r = await family.client.post("/v1/grants", headers=family.h("amma"), json={"grantee_member_id": family.paati["id"], "actions": ["attend", "prepare"],
                                                                                "reason": "she takes Amma to the clinic", "days": 30})
    assert r.status_code == 201, r.text
    assert "Cardiology appointment" in {i["title"] for i in (await brief.today(_p(family, "paati"), limit=50))["items"]}
    assert (await family.client.get(f"/v1/artifacts/{artifact_id}", headers=paati)).status_code == 404


async def test_who_may_set_a_circle_role_and_to_whom(family):
    r = await family.client.put(f"/v1/members/{family.paati['id']}/circle-role", headers=family.h("paati"), json={"circle_role": "parent"})
    assert r.status_code == 403
    r = await family.client.put(f"/v1/members/{family.paati['id']}/circle-role", headers=family.h("amma"), json={"circle_role": "parent"})
    assert r.status_code == 200 and r.json()["circle_role"] == "parent"
    assert (await family.client.put(f"/v1/members/{family.appa['id']}/circle-role", headers=family.h("amma"), json={"circle_role": "caregiver"})).status_code == 422
    assert (await family.client.put(f"/v1/members/{family.older['id']}/circle-role", headers=family.h("amma"), json={"circle_role": "sibling"})).status_code == 422
    assert (await family.client.put(f"/v1/members/{family.paati['id']}/circle-role", headers=family.h("amma"), json={"circle_role": "neighbour"})).status_code == 422
    r = await family.client.put(f"/v1/members/{family.paati['id']}/circle-role", headers=family.h("amma"), json={"circle_role": None})
    assert r.status_code == 200 and r.json()["circle_role"] is None


# ----------------------------------------------------------------------------
# the constitution
# ----------------------------------------------------------------------------

async def test_the_constitution_says_in_words_what_each_person_sees(family):
    await family.client.put(f"/v1/members/{family.paati['id']}/circle-role", headers=family.h("amma"), json={"circle_role": "caregiver"})
    await family.client.post("/v1/grants", headers=family.h("amma"), json={"grantee_member_id": family.paati["id"], "actions": ["attend", "prepare"],
                                                                            "reason": "she takes Amma to the clinic", "days": 30})
    r = await family.client.get("/v1/household/constitution", headers=family.h("paati"))   # any member may read it
    assert r.status_code == 200, r.text
    body = r.json()
    assert any("never holds a card" in w for w in body["walls"]) and any("matches" in w or "match" in w for w in body["walls"])
    people = {p["display_name"]: p for p in body["people"]}
    amma, paati = people["Amma"], people["Paati"]
    assert amma["sees"][0].startswith("Sees everything shared") and "changes these rules" in amma["sees"][1]
    assert paati["circle_role"] == "caregiver" and paati["sees"][0].startswith("Sees only what they send")
    assert any(s.startswith("Also sees things to attend and what to prepare about anyone") and "because she takes Amma to the clinic" in s for s in paati["sees"])
    assert [g["reason"] for g in paati["grants"]] == ["she takes Amma to the clinic"]
    assert any(x["key"] == "scam_guard" for x in body["rules"]) and {"appointments", "bills", "everything_dated", "pickup", "school_one_child", "medicines", "while_we_travel", "emergency_only"} == {x["key"] for x in body["presets"]}
    kids = [p for p in body["people"] if p["role"] == "child"]
    assert kids and kids[0]["sees"][0].startswith("Is someone the household keeps records for")


async def test_the_constitutions_numbers_are_bounded_and_do_something(family, database):
    r = await family.client.put("/v1/household/rules", headers=family.h("amma"), json={"doc_warn_days": 30, "bill_flag_percent": 40})
    assert r.status_code == 200, r.text
    by = {x["key"]: x for x in r.json()["rules"]}
    assert by["doc_warn_days"]["kind"] == "number" and by["doc_warn_days"]["value"] == 30 and by["bill_flag_percent"]["value"] == 40
    for body in ({"doc_warn_days": 999}, {"bill_flag_percent": 1}, {"doc_warn_days": "a lot"}):
        assert (await family.client.put("/v1/household/rules", headers=family.h("amma"), json=body)).status_code == 422
    assert (await family.client.put("/v1/household/rules", headers=family.h("paati"), json={"doc_warn_days": 10})).status_code == 403
    # A visa is warned 45 days ahead; with 30 more, a visa 60 days from running out is already expiring.
    assert documents.status_of(TODAY + dt.timedelta(days=60), "visa", TODAY)[0] == "ok"
    assert documents.status_of(TODAY + dt.timedelta(days=60), "visa", TODAY, 30)[0] == "expiring"


# ----------------------------------------------------------------------------
# the care view
# ----------------------------------------------------------------------------

async def test_a_persons_care_view_gathers_their_papers_bills_appointments_and_warnings(family, database, told):
    household_id = uuid.UUID(family.household["id"])
    paati_id = uuid.UUID(family.paati["id"])
    passport = Claim(kind="document", title="Passport of Paati", document_kind="passport", subject_name="Paati", issuer="Passport Seva",
                     identifier_tail="Z1234567", date=TODAY - dt.timedelta(days=3000), end_date=TODAY + dt.timedelta(days=100),
                     quote="Date of expiry", location=GROUNDED, confidence=0.95)
    a_doc = await _notice(family, "Paati passport scan")
    await service.save(household_id, a_doc, Extraction(extractor=ExtractorInfo(name="openai", model="openai/x", prompt_version="p", parser_version="p1"),
                                                      reference_date=TODAY, actionable=True, page_count=1, claims=[passport]))
    assert await database.fetchval("SELECT holder_member_id FROM documents WHERE artifact_id = $1", a_doc) == paati_id
    async def obligation(action, title):
        artifact_id = uuid.UUID((await family.upload("amma", pdf(title), visibility="shared")).json()["artifact"]["id"])
        xid, cid = uuid.uuid4(), uuid.uuid4()
        await database.execute("INSERT INTO extractions (id, household_id, artifact_id, extractor, prompt_version, parser_version, actionable, page_count) "
                               "VALUES ($1, $2, $3, 'rules', 'v1', 'v1', TRUE, 1)", xid, household_id, artifact_id)
        await database.execute("INSERT INTO claims (id, extraction_id, household_id, artifact_id, ordinal, kind, title, quote, confidence) "
                               "VALUES ($1, $2, $3, $4, 0, 'event', $5, 'words', 0.9)", cid, xid, household_id, artifact_id, title)
        await database.execute("INSERT INTO obligations (id, household_id, artifact_id, claim_id, subject_member_id, kind, action, title, due_date, status) "
                               "VALUES ($1, $2, $3, $4, $5, 'task', $6, $7, $8, 'accepted')", uuid.uuid4(), household_id, artifact_id, cid, paati_id, action, title, TOMORROW)
    await obligation("pay", "Pay the electricity bill")
    await obligation("attend", "Eye check-up")
    await family.client.post("/v1/scam/reports", headers=family.h("amma"), json={"text": SCAM, "about_member_id": family.paati["id"]})
    r = await family.client.get(f"/v1/members/{family.paati['id']}/care", headers=family.h("amma"))
    assert r.status_code == 200, r.text
    care = r.json()
    assert care["member"]["display_name"] == "Paati"
    assert [d["kind"] for d in care["documents"]] == ["passport"] and care["documents"][0]["status"] == "expiring"
    assert [b["title"] for b in care["bills"]] == ["Pay the electricity bill"]
    assert [a["title"] for a in care["appointments"]] == ["Eye check-up"]
    assert len(care["scams"]) == 1 and care["scams"][0]["suspicion"]["level"] == "high"
    # Nobody else's papers are in it, and a member of another household has no such person.
    other = await family.client.get(f"/v1/members/{uuid.uuid4()}/care", headers=family.h("amma"))
    assert other.status_code == 404
    # A caregiver is shown nothing the household shared.
    await family.client.put(f"/v1/members/{family.appa['id']}/circle-role", headers=family.h("amma"), json={"circle_role": None})


async def test_the_constitution_has_the_shape_the_iphone_decodes(family):
    """ios/Kit/Constitution.swift: walls, rules (key, title, sentence, on, fixed, kind...), people (member_id, display_name, role, sees)."""
    r = await family.client.get("/v1/household/constitution", headers=family.h("paati"))      # any member may read it
    assert r.status_code == 200
    body = r.json()
    assert body["walls"] and all(isinstance(w, str) for w in body["walls"])
    for rule in body["rules"]:
        assert {"key", "title", "sentence", "on", "fixed"} <= set(rule) and rule["kind"] in ("switch", "text", "place", "number", "who")
    assert any(rule["kind"] == "switch" for rule in body["rules"])
    for person in body["people"]:
        assert {"member_id", "display_name", "role", "sees"} <= set(person) and isinstance(person["sees"], list)
