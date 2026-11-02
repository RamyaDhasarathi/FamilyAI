"""A booking errand waiting on the person is closed by the service's own confirmation or invoice, and only by that: the sender is
authenticated and on the service's own domain, and the subject confirms or invoices. Marketing, a lookalike domain and a forged
sender close nothing."""
import uuid

import pytest

from familyos import notify
from familyos.extraction import service
from familyos.extraction.claims import Claim
from tests.test_loops import GROUNDED, TODAY, _mail, _read


@pytest.fixture
def told(monkeypatch):
    out = []

    async def member(member_id, subject, body):
        out.append((member_id, subject, body))
        return "test"

    monkeypatch.setattr(notify, "member", member)
    return out


CONFIRMED = "Your booking is confirmed: Kitchen deep clean"


async def _errand(family, database, *, title="Kitchen deep clean", status="needs_you", what=None):
    errand_id = uuid.uuid4()
    await database.execute(
        "INSERT INTO errands (id, household_id, created_by, service, kind, title, spec, params_sha256, status) "
        "VALUES ($1, $2, $3, 'urbancompany', 'booking', $4, $5, $6, $7)",
        errand_id, uuid.UUID(family.household["id"]), uuid.UUID(family.amma["id"]), title, {"what": what or title}, "0" * 64, status)
    return errand_id


async def _arrives(family, database, *, sender="Urban Company <noreply@urbancompany.com>", subject=CONFIRMED, authenticated=True):
    artifact_id = await _mail(family, sender, subject)
    await database.execute("UPDATE input_artifacts SET source = source || $2::jsonb WHERE id = $1", artifact_id,
                           {"sender_authenticated": authenticated})
    return await service.save(uuid.UUID(family.household["id"]), artifact_id, _read([
        Claim(kind="info", title="Kitchen deep clean booked", date=TODAY, quote="Your booking is confirmed", location=GROUNDED, confidence=0.9)],
        reference=TODAY))


async def test_the_services_own_confirmation_closes_the_errand_and_tells_who_asked(family, database, told):
    errand = await _errand(family, database)
    told.clear()
    counts = await _arrives(family, database)
    assert counts["errands_closed"] == [str(errand)]
    row = await database.fetchrow("SELECT status, ended_at, outcome FROM errands WHERE id = $1", errand)
    assert row["status"] == "done" and row["ended_at"] is not None and row["outcome"]["confirmed_by"]["subject"] == CONFIRMED
    assert [(t[0], t[1]) for t in told] == [(uuid.UUID(family.amma["id"]), "Confirmed: Kitchen deep clean")]
    assert await database.fetchval("SELECT count(*) FROM audit_events WHERE action = 'errand.confirmed_by_mail' AND target_id = $1", errand) == 1


@pytest.mark.parametrize("sender,subject,authenticated", [
    ("Urban Company <offers@urbancompany.com>", "20% off AC service this weekend", True),                 # marketing from the same domain
    ("Urban Company <noreply@urbancompany.com>", CONFIRMED, False),                                       # a forged sender
    ("Urban Company <noreply@urbancompany.com.example.net>", CONFIRMED, True),                            # a lookalike domain
    ("Urban Company <noreply@noturbancompany.com>", CONFIRMED, True),                                     # a longer name ending the same way
])
async def test_what_is_not_the_services_own_confirmation_closes_nothing(family, database, told, sender, subject, authenticated):
    errand = await _errand(family, database)
    counts = await _arrives(family, database, sender=sender, subject=subject, authenticated=authenticated)
    assert counts["errands_closed"] == []
    assert await database.fetchval("SELECT status FROM errands WHERE id = $1", errand) == "needs_you"


async def test_an_errand_already_done_gains_the_evidence_and_is_not_announced_again(family, database, told):
    errand = await _errand(family, database, status="done")
    told.clear()
    await _arrives(family, database)
    row = await database.fetchrow("SELECT status, outcome FROM errands WHERE id = $1", errand)
    assert row["status"] == "done" and "confirmed_by" in row["outcome"] and told == []


async def test_with_two_open_the_one_the_mail_names_is_the_one_that_closes(family, database, told):
    kitchen = await _errand(family, database, title="Kitchen deep clean")
    bathroom = await _errand(family, database, title="Bathroom cleaning")
    counts = await _arrives(family, database)
    assert counts["errands_closed"] == [str(kitchen)]
    assert await database.fetchval("SELECT status FROM errands WHERE id = $1", bathroom) == "needs_you"


async def test_with_two_open_and_neither_named_nothing_is_guessed(family, database, told):
    await _errand(family, database, title="Sofa shampoo")
    await _errand(family, database, title="Bathroom cleaning")
    counts = await _arrives(family, database, subject="Your invoice from Urban Company")
    assert counts["errands_closed"] == []
