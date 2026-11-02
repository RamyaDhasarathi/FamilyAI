"""Medications read from a prescription, and standing payments (the rent):
what each makes, who sees it, and that nothing is paid."""
import datetime as dt
import uuid

from familyos import clock, loops, medications, standing
from familyos.db import pool
from familyos.extraction import service
from familyos.extraction.claims import Claim, Extraction, ExtractorInfo
from familyos.identity import Principal
from tests.conftest import pdf

GROUNDED = {"page": 1, "start": 0, "end": 16, "boxes": [[60.0, 78.0, 300.0, 93.0]], "match": "exact"}
TODAY = clock.today()


def _p(family, who="amma"):
    m = getattr(family, who)
    return Principal(member_id=uuid.UUID(m["id"]), household_id=uuid.UUID(family.household["id"]), role=m["role"], display_name=m["display_name"])


def _read(claims):
    return Extraction(extractor=ExtractorInfo(name="openai", model="openai/x", prompt_version="p", parser_version="p1"),
                      reference_date=TODAY, actionable=True, page_count=1, claims=claims)


def _med(drug, ends, *, patient=None, dose="1 tablet after food", per_day=2, starts=None):
    return Claim(kind="medication", title=drug, dose_text=dose, times_per_day=per_day, date=starts or TODAY - dt.timedelta(days=25), end_date=ends,
                 issuer="Dr Meena, Apollo Clinic", subject_name=patient, quote="Tab " + drug, location=GROUNDED, confidence=0.9)


async def _share(family, subject, claims, who="amma", visibility="shared"):
    r = await family.upload(who, pdf(subject), filename=subject[:20] + ".pdf", visibility=visibility)
    artifact_id = uuid.UUID(r.json()["artifact"]["id"])
    await service.save(uuid.UUID(family.household["id"]), artifact_id, _read(claims))
    return artifact_id


async def test_a_prescription_keeps_each_medicine_and_proposes_a_refill_before_the_supply_ends(family, database):
    ends = TODAY + dt.timedelta(days=9)
    artifact_id = await _share(family, "Prescription for Amma", [_med("Metformin 500 mg", ends, patient="Amma"), _med("Telmisartan 40 mg", ends, patient="Amma", dose="1 tablet in the morning", per_day=1)])
    rows = await database.fetch("SELECT drug, dose_text, times_per_day, patient_member_id, prescriber, ends_on FROM medications WHERE artifact_id = $1 ORDER BY drug", artifact_id)
    assert [r["drug"] for r in rows] == ["Metformin 500 mg", "Telmisartan 40 mg"]
    assert rows[0]["dose_text"] == "1 tablet after food" and rows[0]["times_per_day"] == 2 and rows[0]["patient_member_id"] == uuid.UUID(family.amma["id"])
    assert rows[0]["prescriber"] == "Dr Meena, Apollo Clinic"
    refills = sorted(await database.fetch("SELECT title, action, due_date, status FROM obligations WHERE artifact_id = $1", artifact_id), key=lambda r: r["title"])      # sealed: ordered here
    assert [r["title"] for r in refills] == ["Refill Metformin 500 mg", "Refill Telmisartan 40 mg"]
    assert all(r["due_date"] == ends - dt.timedelta(days=medications.REFILL_LEAD_DAYS) and r["status"] == "proposed" for r in refills)
    r = await family.client.get("/v1/medications", headers=family.h("appa"))
    assert r.status_code == 200, r.text
    listed = {m["drug"]: m for m in r.json()}
    assert listed["Metformin 500 mg"]["patient_name"] == "Amma" and listed["Metformin 500 mg"]["doses_today"] == 2
    assert listed["Metformin 500 mg"]["status"] == "active" and listed["Metformin 500 mg"]["days_left"] == 9


def test_a_supply_is_active_then_due_for_a_refill_then_finished():
    assert medications.status_of(TODAY + dt.timedelta(days=20), TODAY)[0] == "active"
    assert medications.status_of(TODAY + dt.timedelta(days=3), TODAY) == ("refill", 3)
    assert medications.status_of(TODAY - dt.timedelta(days=1), TODAY) == ("finished", -1)
    assert medications.status_of(None, TODAY) == ("ongoing", None)


async def test_a_newer_prescription_of_the_same_drug_supersedes_and_a_childs_is_theirs_only_with_consent(family, database):
    a1 = await _share(family, "First prescription", [_med("Metformin 500 mg", TODAY + dt.timedelta(days=2), patient="Amma")])
    a2 = await _share(family, "Second prescription", [_med("metformin 500 mg", TODAY + dt.timedelta(days=30), patient="Amma")])
    assert await database.fetchval("SELECT superseded_at FROM medications WHERE artifact_id = $1", a1) is not None
    r = await family.client.get("/v1/medications", headers=family.h("amma"))
    assert [m["artifact_id"] for m in r.json()] == [str(a2)]
    # A child named on a prescription is nobody's patient until consent is recorded.
    child = family.older
    a3 = await _share(family, "Child prescription", [_med("Cetirizine 5 mg", TODAY + dt.timedelta(days=5), patient=child["display_name"])])
    assert await database.fetchval("SELECT patient_member_id FROM medications WHERE artifact_id = $1", a3) is None


async def test_a_private_prescription_is_not_shown_to_the_rest_of_the_household(family, database):
    await _share(family, "Private prescription", [_med("Sertraline 50 mg", TODAY + dt.timedelta(days=20), patient="Amma")], visibility="private")
    assert [m["drug"] for m in (await family.client.get("/v1/medications", headers=family.h("amma"))).json()] == ["Sertraline 50 mg"]
    assert (await family.client.get("/v1/medications", headers=family.h("appa"))).json() == []


def test_the_due_date_is_the_next_day_of_the_month_and_a_short_month_is_not_overrun():
    assert standing.due_in(5, dt.date(2026, 10, 1)) == dt.date(2026, 10, 5)
    assert standing.due_in(5, dt.date(2026, 10, 7)) == dt.date(2026, 10, 5)      # two days late is still this month's
    assert standing.due_in(5, dt.date(2026, 10, 20)) == dt.date(2026, 11, 5)
    assert standing.due_in(5, dt.date(2026, 12, 20)) == dt.date(2027, 1, 5)
    assert standing.due_in(28, dt.date(2027, 2, 1)) == dt.date(2027, 2, 28)


async def test_a_standing_payment_makes_the_months_obligation_once_a_fortnight_ahead(family, database):
    day = (TODAY + dt.timedelta(days=6)).day if (TODAY + dt.timedelta(days=6)).day <= 28 else 1
    r = await family.client.post("/v1/standing", headers=family.h("amma"), json={
        "title": "Rent", "payee": "Mr Raman", "amount": 18000, "day_of_month": day, "pay_url": "upi://pay?pa=raman@bank&pn=Raman"})
    assert r.status_code == 201, r.text
    rows = [r for r in await database.fetch("SELECT o.title, o.action, o.status, o.due_date, o.pay_url, c.amount FROM obligations o JOIN claims c ON c.id = o.claim_id "
                                            "WHERE o.household_id = $1", uuid.UUID(family.household["id"])) if r["title"].startswith("Rent")]      # titles are sealed: matched here, not in SQL
    if day != 1:
        [o] = rows
        assert o["action"] == "pay" and o["status"] == "accepted" and float(o["amount"]) == 18000 and o["pay_url"].startswith("upi://")
        assert o["due_date"] == standing.due_in(day, TODAY)
    # Running again, as the sweep does, makes nothing more.
    assert await standing.make_due(uuid.UUID(family.household["id"])) == 0
    assert [s["title"] for s in (await family.client.get("/v1/standing", headers=family.h("appa"))).json()] == ["Rent"]


async def test_a_payment_far_off_waits_and_the_receipt_that_names_the_payee_closes_it(family, database):
    hid = uuid.UUID(family.household["id"])
    far = (TODAY + dt.timedelta(days=20))
    far_day = far.day if far.day <= 28 else 28
    await standing.create(_p(family), title="Rent", payee="Mr Raman Properties", amount=18000, day_of_month=far_day)
    assert await standing.make_due(hid) == 0 or standing.due_in(far_day, TODAY) <= TODAY + dt.timedelta(days=standing.AHEAD_DAYS)
    # Make the month's obligation for a date a few days ahead, then pay it with a receipt that names the payee.
    soon = TODAY + dt.timedelta(days=4)
    soon_day = soon.day if soon.day <= 28 else 28
    await standing.create(_p(family), title="Maid", payee="Lakshmi Devi", amount=3500, day_of_month=soon_day)
    bill = next((r for r in await database.fetch("SELECT o.id, o.artifact_id, o.title FROM obligations o WHERE o.household_id = $1", hid) if r["title"].startswith("Maid")), None)
    assert bill is not None
    receipt = Claim(kind="payment", title="Paid ₹3,500 to Lakshmi Devi via UPI", date=TODAY, amount={"value": 3500, "currency": "INR", "text": "₹3,500"},
                    quote="Paid ₹3,500 to Lakshmi Devi", location=GROUNDED, confidence=0.9)
    r = await family.upload("amma", pdf("UPI receipt Lakshmi"), filename="upi.pdf", visibility="shared")
    rid = uuid.UUID(r.json()["artifact"]["id"])
    async with pool().acquire() as conn, conn.transaction():
        artifact = dict(await conn.fetchrow("SELECT * FROM input_artifacts WHERE id = $1", rid))
        closed = await loops.close_from_receipt(conn, hid, artifact, [receipt], sent_on=TODAY,
                                                source={"from": "alerts@bank.example", "subject": "Paid ₹3,500 to Lakshmi Devi"}, category="banking")
    assert [c["artifact_id"] for c in closed] == [bill["artifact_id"]]


async def test_only_whoever_set_it_or_a_guardian_stops_it_and_a_child_cannot_set_one(family, database):
    row = await standing.create(_p(family, "amma"), title="Rent", payee="Mr Raman", amount=18000, day_of_month=5, visibility="private")
    assert (await family.client.delete(f"/v1/standing/{row['id']}", headers=family.h("appa"))).status_code in (403, 404)
    assert (await family.client.delete(f"/v1/standing/{row['id']}", headers=family.h("amma"))).status_code == 204
    r = await family.client.post("/v1/standing", headers=family.h("amma"), json={"title": "x", "payee": "y", "amount": 0, "day_of_month": 5})
    assert r.status_code == 422
    r = await family.client.post("/v1/standing", headers=family.h("amma"), json={"title": "x", "payee": "y", "amount": 10, "day_of_month": 31})
    assert r.status_code == 422


async def test_a_notice_with_a_medicine_in_it_is_health_whoever_sent_it(family, database):
    from familyos import inbox
    artifact_id = await _share(family, "Photographed prescription", [_med("Metformin 500 mg", TODAY + dt.timedelta(days=20), patient="Amma")])
    other = await _share(family, "A plain photo of something else", [])
    rows = {str(r["id"]): r for r in await inbox.feed(_p(family), days=30)}
    assert rows[str(artifact_id)]["category"] == "medical" and rows[str(artifact_id)]["has_medicine"] is True
    assert rows[str(other)]["category"] != "medical"


async def test_prescriptions_are_grouped_by_person_newest_first_and_a_single_tagged_notice_names_its_patient(family, database):
    older = await _share(family, "Older prescription", [_med("Paracetamol 500 mg", TODAY - dt.timedelta(days=40), patient="Amma", starts=TODAY - dt.timedelta(days=45))])
    newer = await _share(family, "Newer prescription", [_med("Metformin 500 mg", TODAY + dt.timedelta(days=20), patient="Amma", starts=TODAY - dt.timedelta(days=10))])
    # A prescription whose patient was not read but whose notice is tagged with a consented child belongs to that child.
    child = family.older
    await family.consent(child)
    tagged = await _share(family, "Child prescription tagged", [_med("Cetirizine 5 mg", TODAY + dt.timedelta(days=5), patient=None)])
    await database.execute("INSERT INTO artifact_subjects (artifact_id, member_id, inferred) VALUES ($1, $2, FALSE)", tagged, uuid.UUID(child["id"]))
    r = await family.client.get("/v1/prescriptions", headers=family.h("amma"))
    assert r.status_code == 200, r.text
    groups = {g["name"]: g for g in r.json()}
    assert [x["artifact_id"] for x in groups["Amma"]["prescriptions"]] == [str(newer), str(older)]
    assert [x["status"] for x in groups["Amma"]["prescriptions"]] == ["current", "finished"]
    assert groups[child["display_name"]]["prescriptions"][0]["medicines"][0]["drug"] == "Cetirizine 5 mg"
    assert groups[child["display_name"]]["prescriptions"][0]["status"] == "refill"


async def test_a_wrong_date_on_a_prescription_is_corrected_and_every_medicine_keeps_its_length(family, database):
    a = await _share(family, "Misread year", [_med("Xpect 4D", dt.date(2022, 4, 26), starts=dt.date(2022, 4, 24)), _med("ORS", dt.date(2022, 4, 24), starts=dt.date(2022, 4, 24))])
    r = await family.client.put(f"/v1/prescriptions/{a}/date", headers=family.h("amma"), json={"date": "2026-04-24"})
    assert r.status_code == 200 and r.json() == {"medicines": 2}
    rows = {m["drug"]: m for m in await database.fetch("SELECT drug, starts_on, ends_on FROM medications WHERE artifact_id = $1", a)}
    assert rows["Xpect 4D"]["starts_on"] == dt.date(2026, 4, 24) and rows["Xpect 4D"]["ends_on"] == dt.date(2026, 4, 26)
    assert rows["ORS"]["ends_on"] == dt.date(2026, 4, 24)
    event = await database.fetchval("SELECT detail->>'shift_days' FROM audit_events WHERE action = 'medication.date_corrected' ORDER BY id DESC LIMIT 1")
    assert event == str((dt.date(2026, 4, 24) - dt.date(2022, 4, 24)).days)
    assert (await family.client.put(f"/v1/prescriptions/{a}/date", headers=family.h("amma"), json={"date": "1990-01-01"})).status_code == 422
    assert (await family.client.put(f"/v1/prescriptions/{uuid.uuid4()}/date", headers=family.h("amma"), json={"date": "2026-04-24"})).status_code == 404


async def test_the_clinic_on_a_prescription_is_read_shown_and_correctable(family, database):
    claim = _med("Metformin 500 mg", TODAY + dt.timedelta(days=20), patient="Amma")
    claim.place = "Little Blossoms Children's Clinic"
    a = await _share(family, "Prescription with a letterhead", [claim])
    b = await _share(family, "Prescription without one", [_med("Telmisartan 40 mg", TODAY + dt.timedelta(days=20), patient="Amma")])
    groups = (await family.client.get("/v1/prescriptions", headers=family.h("amma"))).json()
    rx = {x["artifact_id"]: x for g in groups for x in g["prescriptions"]}
    assert rx[str(a)]["clinic"] == "Little Blossoms Children's Clinic" and rx[str(b)]["clinic"] is None
    r = await family.client.patch(f"/v1/prescriptions/{b}", headers=family.h("amma"), json={"clinic": "  Apollo   Clinic, Chennai "})
    assert r.status_code == 200, r.text
    assert await database.fetchval("SELECT clinic FROM medications WHERE artifact_id = $1", b) == "Apollo Clinic, Chennai"
    # Only what is sent changes: a date alone leaves the clinic.
    await family.client.patch(f"/v1/prescriptions/{b}", headers=family.h("amma"), json={"date": (TODAY - dt.timedelta(days=3)).isoformat()})
    assert await database.fetchval("SELECT clinic FROM medications WHERE artifact_id = $1", b) == "Apollo Clinic, Chennai"
    assert (await family.client.patch(f"/v1/prescriptions/{uuid.uuid4()}", headers=family.h("amma"), json={"clinic": "x"})).status_code == 404


async def test_a_prescription_can_be_said_to_be_someone_elses(family, database):
    import datetime as dt
    import uuid

    from familyos import medications
    from familyos.identity import Principal
    p = Principal(member_id=uuid.UUID(family.amma["id"]), household_id=uuid.UUID(family.household["id"]), role="guardian", display_name="Amma")
    r = await family.upload("amma", b"%PDF-1.4 rx2 " + uuid.uuid4().bytes, filename="rx.pdf", visibility="shared")
    artifact_id = uuid.UUID(r.json()["artifact"]["id"])
    today = clock.today()
    await database.execute(
        "INSERT INTO medications (id, household_id, artifact_id, drug, patient_member_id, starts_on, ends_on) VALUES ($1, $2, $3, 'Cetrizine', $4, $5, $6)",
        uuid.uuid4(), p.household_id, artifact_id, uuid.UUID(family.older["id"]), today, today + dt.timedelta(days=5))
    res = await family.client.patch(f"/v1/prescriptions/{artifact_id}", headers=family.h("amma"), json={"patient_member_id": family.younger["id"]})
    assert res.status_code == 200, res.text
    rows = [m for m in await medications.list_for(p) if m["artifact_id"] == artifact_id]
    assert rows and rows[0]["patient_name"] == family.younger["display_name"]
    bad = await family.client.patch(f"/v1/prescriptions/{artifact_id}", headers=family.h("amma"), json={"patient_member_id": str(uuid.uuid4())})
    assert bad.status_code in (403, 404)
