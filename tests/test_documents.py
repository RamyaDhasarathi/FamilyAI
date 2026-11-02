"""Documents: a passport, a policy, the car's papers, read from the family's
own notices and kept with their dates. A renewal is proposed with the lead
the kind needs; a trip is checked against the passports that would travel;
of a number only the last four characters are kept."""
import datetime as dt
import uuid

from familyos import clock, documents
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


def _passport(holder, expires, *, number="Z1234567", title=None, issued=None):
    return Claim(kind="document", title=title or f"Passport of {holder}", document_kind="passport", subject_name=holder,
                 issuer="Passport Seva, Chennai", identifier_tail=number, date=issued or expires - dt.timedelta(days=3650),
                 end_date=expires, quote="Date of expiry", location=GROUNDED, confidence=0.95)


async def _share(family, subject, claims, who="amma"):
    r = await family.upload(who, pdf(subject), filename=subject[:20] + ".pdf", visibility="shared")
    artifact_id = uuid.UUID(r.json()["artifact"]["id"])
    counts = await service.save(uuid.UUID(family.household["id"]), artifact_id, _read(claims))
    return artifact_id, counts


async def test_a_passport_is_kept_with_its_dates_its_holder_and_only_the_tail_of_its_number(family, database):
    expires = TODAY + dt.timedelta(days=400)
    artifact_id, counts = await _share(family, "Amma passport photo page", [_passport("Amma", expires, number="M 9876543")])
    assert counts["documents"] == 1
    row = await database.fetchrow("SELECT * FROM documents WHERE artifact_id = $1", artifact_id)
    assert row["kind"] == "passport" and row["holder_member_id"] == uuid.UUID(family.amma["id"]) and row["expires_on"] == expires
    assert row["identifier_tail"] == "6543"
    assert await database.fetchval("SELECT identifier_tail FROM claims WHERE artifact_id = $1 AND kind = 'document'", artifact_id) == "6543"
    assert "9876543" not in str(await database.fetchval("SELECT row_to_json(d) FROM documents d WHERE artifact_id = $1", artifact_id))
    # A renewal is proposed nine months before a passport runs out.
    renew = await database.fetchrow("SELECT title, action, due_date, kind FROM obligations WHERE artifact_id = $1", artifact_id)
    assert renew["title"] == "Renew Passport of Amma" and renew["action"] == "submit" and renew["due_date"] == expires - dt.timedelta(days=270)
    # And it is on the household's list, valid, with its holder's name.
    r = await family.client.get("/v1/documents", headers=family.h("appa"))
    assert r.status_code == 200, r.text
    [doc] = r.json()["documents"]
    assert doc["holder_name"] == "Amma" and doc["status"] == "ok" and doc["days_left"] == 400 and doc["identifier_tail"] == "6543" and doc["label"] == "passport"
    assert r.json()["checks"] == []


async def test_a_child_is_a_holder_only_with_consent_and_a_stranger_is_nobody(family, database):
    child = family.older
    a1, _ = await _share(family, "Child passport, no consent", [_passport(child["display_name"], TODAY + dt.timedelta(days=900))])
    assert await database.fetchval("SELECT holder_member_id FROM documents WHERE artifact_id = $1", a1) is None
    await family.consent(child)
    a2, _ = await _share(family, "Child passport, consented", [_passport(child["display_name"], TODAY + dt.timedelta(days=900), number="K2222")])
    assert await database.fetchval("SELECT holder_member_id FROM documents WHERE artifact_id = $1", a2) == uuid.UUID(child["id"])
    a3, _ = await _share(family, "Somebody else's passport", [_passport("Rajesh Kumar", TODAY + dt.timedelta(days=900), number="R3333")])
    row = await database.fetchrow("SELECT holder_member_id, holder_text FROM documents WHERE artifact_id = $1", a3)
    assert row["holder_member_id"] is None and row["holder_text"] is None


async def test_a_newer_passport_supersedes_the_old_and_a_trip_is_checked_against_it(family, database):
    old_expiry = TODAY + dt.timedelta(days=120)
    a1, _ = await _share(family, "Appa old passport", [_passport("Appa", old_expiry, number="A1111")])
    # A trip returning in 60 days: the passport runs out 120 days from now, far short of six months after.
    plan_id = uuid.uuid4()
    await pool().execute(
        "INSERT INTO plans (id, household_id, created_by, title, brief, status, starts_on, ends_on, shape) VALUES ($1, $2, $3, $4, 'a week away', 'draft', $5, $6, 'trip')",
        plan_id, uuid.UUID(family.household["id"]), uuid.UUID(family.amma["id"]), "Diwali in Dubai", TODAY + dt.timedelta(days=50), TODAY + dt.timedelta(days=60))
    r = await family.client.get("/v1/documents", headers=family.h("amma"))
    [check] = r.json()["checks"]
    assert check["kind"] == "passport_short" and check["plan_title"] == "Diwali in Dubai" and check["holder_name"] == "Appa"
    assert check["title"] == "Appa’s passport runs out before Diwali in Dubai needs it."
    assert "six months" in check["why"] and check["needed_until"] == (TODAY + dt.timedelta(days=60 + 180)).isoformat()
    # A new passport arrives: the old record is superseded, the trip is fine, the list shows one.
    a2, _ = await _share(family, "Appa new passport", [_passport("Appa", TODAY + dt.timedelta(days=3600), number="B2222")])
    assert await database.fetchval("SELECT superseded_at FROM documents WHERE artifact_id = $1", a1) is not None
    r = await family.client.get("/v1/documents", headers=family.h("amma"))
    assert [d["artifact_id"] for d in r.json()["documents"]] == [str(a2)] and r.json()["checks"] == []


async def test_an_expired_policy_is_said_and_a_puc_renewal_is_a_fortnight_ahead(family, database):
    policy = Claim(kind="document", title="Car insurance policy, Honda City", document_kind="insurance", issuer="ICICI Lombard",
                   identifier_tail="POL/2025/778899", date=TODAY - dt.timedelta(days=400), end_date=TODAY - dt.timedelta(days=35),
                   quote="Policy period", location=GROUNDED, confidence=0.9)
    puc = Claim(kind="document", title="PUC certificate, TN 09 AB 1234", document_kind="puc", issuer="RTO",
                date=TODAY - dt.timedelta(days=100), end_date=TODAY + dt.timedelta(days=80), quote="Valid till", location=GROUNDED, confidence=0.9)
    artifact_id, _ = await _share(family, "Car papers", [policy, puc])
    r = await family.client.get("/v1/documents", headers=family.h("amma"))
    by = {d["kind"]: d for d in r.json()["documents"]}
    assert by["insurance"]["status"] == "expired" and by["insurance"]["identifier_tail"] == "8899"
    assert by["puc"]["status"] == "ok"
    [check] = r.json()["checks"]
    assert check["kind"] == "expired" and check["title"] == "insurance policy has expired."
    rows = await database.fetch("SELECT title, due_date FROM obligations WHERE artifact_id = $1 ORDER BY due_date", artifact_id)
    assert [(r["title"], (r["due_date"] - TODAY).days) for r in rows if r["title"].startswith("Renew PUC")] == [("Renew PUC certificate, TN 09 AB 1234", 66)]
    assert documents.status_of(TODAY + dt.timedelta(days=10), "puc") == ("expiring", 10)


def test_a_documents_number_is_never_kept_whole():
    assert documents.mask_numbers("Aadhaar 1234 5678 9012 issued") == "Aadhaar xxxx xxxx 9012 issued"
    assert documents.mask_numbers("Passport No. Z1234567, DOB 1984") == "Passport No. Zxxx4567, DOB 1984"
    assert documents.mask_numbers("Policy 2025/778899, Rs 4,000") == "Policy 2025/xx8899, Rs 4,000"   # a six-digit number is masked; an amount is not
    assert documents.mask_numbers("Call 1800 258 6161") == "Call xxxx xxx 6161"
    assert documents.mask_numbers(None) is None


async def test_a_document_claims_quote_is_stored_masked(family, database):
    holder = "Amma"
    claim = Claim(kind="document", title="Aadhaar card", document_kind="id_card", subject_name=holder, issuer="UIDAI",
                  identifier_tail="9012", quote="Aadhaar 1234 5678 9012", location=GROUNDED, confidence=0.95)
    artifact_id, _ = await _share(family, "Amma Aadhaar", [claim])
    assert await database.fetchval("SELECT quote FROM claims WHERE artifact_id = $1", artifact_id) == "Aadhaar xxxx xxxx 9012"
    assert await database.fetchval("SELECT identifier_tail FROM documents WHERE artifact_id = $1", artifact_id) == "9012"


def test_a_one_time_code_a_statement_and_a_letterhead_are_not_documents_but_a_policy_and_a_licence_are():
    d = dt.date(2026, 10, 11)
    # "Valid for 30 minutes": the TomTom mail that showed "document has expired".
    assert documents.worth_keeping("TomTom account verification code", "other", d, d, None) is False
    assert documents.worth_keeping("Daily Margin Statement", "other", d, None, None) is False
    assert documents.worth_keeping("Preset Police Doctor's Device", "other", dt.date(2025, 11, 1), None, None) is False
    assert documents.worth_keeping("Some paper with no date or number", "other", None, None, None) is False
    assert documents.worth_keeping("Car insurance policy", "insurance", dt.date(2026, 1, 1), dt.date(2027, 1, 1), "8899") is True
    assert documents.worth_keeping("Driving licence", "driving_licence", None, dt.date(2030, 5, 1), None) is True
    assert documents.worth_keeping("Aadhaar Card", "id_card", dt.date(2026, 10, 8), None, "9012") is True      # a number, so worth keeping


async def test_what_was_wrongly_kept_before_is_taken_off_the_list_not_deleted(family, database):
    artifact_id, _ = await _share(family, "Verification mail", [])
    await database.execute(
        "INSERT INTO documents (id, household_id, artifact_id, kind, title, valid_from, expires_on) VALUES ($1, $2, $3, 'other', 'Login verification code', $4, $4)",
        uuid.uuid4(), uuid.UUID(family.household["id"]), artifact_id, TODAY)
    async with pool().acquire() as conn:
        assert await documents.prune_unworthy(conn) == 1
    assert await database.fetchval("SELECT count(*) FROM documents WHERE artifact_id = $1 AND superseded_at IS NULL", artifact_id) == 0
    assert await database.fetchval("SELECT count(*) FROM documents WHERE artifact_id = $1", artifact_id) == 1


async def _document_cards(family, who="amma"):
    return [c for c in (await family.client.get("/v1/decisions", headers=family.h(who))).json() if c["kind"] == "document"]


def _licence(holder, expires, *, issued=None):
    return Claim(kind="document", title="Driving License", document_kind="driving_licence", subject_name=holder, issuer="RTO, Madurai", identifier_tail="TN0120066647",
                 date=issued or expires - dt.timedelta(days=7300), end_date=expires, quote="Valid till", location=GROUNDED, confidence=0.95)


async def test_an_expired_licence_is_a_card_with_a_renewal_to_do_and_a_renewed_one_clears_it(family, database):
    await _share(family, "Licence scan", [_licence(family.amma["display_name"], TODAY - dt.timedelta(days=94))])
    h = family.h("amma")
    (card,) = await _document_cards(family)
    assert card["late"] and "has expired" in card["title"] and "94 days ago" in card["happened"] and card["actions"][0]["key"] == "todo"
    todo = card["actions"][0]
    made = await family.client.post(todo["path"], headers=h, json=todo["body"])
    assert made.status_code == 201 and made.json()["title"].startswith("Renew")
    # the renewed card supersedes the old record, and the card goes
    await _share(family, "Licence renewed", [_licence(family.amma["display_name"], TODAY + dt.timedelta(days=7000), issued=TODAY)])
    assert await _document_cards(family) == []


async def test_not_this_is_remembered_an_expiring_one_is_a_card_too_and_other_peoples_are_not_shown(family, database):
    await _share(family, "Policy", [Claim(kind="document", title="Health insurance", document_kind="insurance", issuer="Star Health", identifier_tail="POL998877",
                                          date=TODAY - dt.timedelta(days=335), end_date=TODAY + dt.timedelta(days=20), quote="Policy period", location=GROUNDED, confidence=0.9)])
    (card,) = await _document_cards(family)
    assert "runs out" in card["title"] and not card["late"]
    renewed = next(a for a in card["actions"] if a["key"] == "renewed")
    assert (await family.client.post(renewed["path"], headers=family.h("amma"))).status_code == 204
    assert await _document_cards(family) == []
    await _share(family, "Old", [_licence(family.appa["display_name"], TODAY - dt.timedelta(days=10))])
    assert len(await _document_cards(family)) == 1               # a guardian sees another adult's
    assert await _document_cards(family, "paati") == []          # an adult who is not the holder does not
