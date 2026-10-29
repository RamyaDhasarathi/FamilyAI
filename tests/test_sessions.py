"""Class 2 custody: the session is sealed, lent for one task, and gone after."""
import uuid

import pytest
from cryptography.exceptions import InvalidTag

from familyos import crypto
from familyos.execution import capability, disposable, sessions
from familyos.execution.sessions import SessionState
from familyos.identity import Invalid, Principal

STATE = SessionState(
    cookies=[{"name": "sid", "value": "secret-cookie-value", "domain": "portal.example.com"}],
    fingerprint={"ua": "Mozilla/5.0", "viewport": [1280, 800]},
    egress_id="proxy-in-1")


def _principal(family, who="amma"):
    m = getattr(family, who)
    return Principal(member_id=uuid.UUID(m["id"]), household_id=uuid.UUID(family.household["id"]),
                     role=m["role"], display_name=m["display_name"])


async def _store(family, who="amma", service="portal"):
    return await sessions.store(_principal(family, who), service=service, state=STATE,
                                allow_hosts=["portal.example.com"])


# ----------------------------------------------------------------------------
# what sealing buys
# ----------------------------------------------------------------------------

async def test_the_stored_row_holds_no_readable_cookie(family, database):
    await _store(family)
    raw = await database.fetchval("SELECT sealed_state FROM sealed_sessions")
    assert b"secret-cookie-value" not in raw
    assert b"proxy-in-1" not in raw


async def test_a_session_will_not_open_for_another_member_or_service(family, database):
    row = await _store(family, "amma", "portal")
    key = crypto.unwrap(uuid.UUID(family.household["id"]),
                        await database.fetchval("SELECT wrapped_key FROM households WHERE id = $1",
                                                uuid.UUID(family.household["id"])))
    sealed = row["sealed_state"]
    household_id = uuid.UUID(family.household["id"])

    # The right key, the wrong binding: the cipher refuses, not a line of code.
    for aad in (sessions._aad(household_id, uuid.UUID(family.appa["id"]), "portal"),
                sessions._aad(household_id, uuid.UUID(family.amma["id"]), "other-portal"),
                sessions._aad(uuid.uuid4(), uuid.UUID(family.amma["id"]), "portal")):
        with pytest.raises(InvalidTag):
            crypto.open_sealed(key, sealed, aad)


async def test_erasing_the_household_takes_the_session_with_it(family, database):
    """The property a persistent on-disk browser profile cannot have."""
    await _store(family)
    p = _principal(family)
    async with sessions.lease(p, "portal", reason="check") as held:
        assert held.state.cookies[0]["value"] == "secret-cookie-value"

    # Destroy the key, as erasure does before deleting anything.
    await database.execute("UPDATE households SET wrapped_key = $2 WHERE id = $1",
                           p.household_id, crypto.new_wrapped_key(p.household_id))
    with pytest.raises(sessions.SessionLapsed):
        async with sessions.lease(p, "portal", reason="check"):
            pass


# ----------------------------------------------------------------------------
# the lease
# ----------------------------------------------------------------------------

async def test_a_lease_is_open_for_one_task_and_forgotten_after(family, database):
    await _store(family)
    p = _principal(family)
    async with sessions.lease(p, "portal", reason="read circulars") as held:
        assert held.live and held.state.egress_id == "proxy-in-1"
        kept = held
    assert not kept.live
    assert kept.state.cookies == [] and kept.state.egress_id == ""


async def test_the_lease_is_recorded_at_both_ends_without_the_secret(family, database):
    await _store(family)
    p = _principal(family)
    async with sessions.lease(p, "portal", reason="read circulars"):
        pass
    rows = await database.fetch(
        "SELECT action, detail FROM audit_events WHERE action LIKE 'session.%' ORDER BY at")
    assert [r["action"] for r in rows] == ["session.stored", "session.opened", "session.closed"]
    blob = " ".join(str(r["detail"]) for r in rows)
    assert "secret-cookie-value" not in blob and "proxy-in-1" not in blob


async def test_use_is_counted_even_when_the_task_fails(family, database):
    await _store(family)
    p = _principal(family)
    with pytest.raises(RuntimeError):
        async with sessions.lease(p, "portal", reason="read"):
            raise RuntimeError("the portal was down")
    row = await database.fetchrow("SELECT uses, last_used_at FROM sealed_sessions")
    assert row["uses"] == 1 and row["last_used_at"] is not None


async def test_a_lapsed_or_revoked_session_is_refused_and_nothing_retries(family, database):
    row = await _store(family)
    p = _principal(family)
    await database.execute("UPDATE sealed_sessions SET expires_at = NOW() - interval '1 day' WHERE id = $1",
                           row["id"])
    with pytest.raises(sessions.SessionLapsed):
        async with sessions.lease(p, "portal", reason="read"):
            pass

    await database.execute("UPDATE sealed_sessions SET expires_at = NOW() + interval '1 day' WHERE id = $1",
                           row["id"])
    await sessions.revoke(p, row["id"])
    with pytest.raises(sessions.SessionLapsed):
        async with sessions.lease(p, "portal", reason="read"):
            pass


async def test_signing_in_again_retires_the_previous_session(family, database):
    first = await _store(family)
    second = await _store(family)
    assert first["id"] != second["id"]
    live = await database.fetch("SELECT id FROM sealed_sessions WHERE revoked_at IS NULL")
    assert [r["id"] for r in live] == [second["id"]]


# ----------------------------------------------------------------------------
# the gateway
# ----------------------------------------------------------------------------

async def test_a_capability_carries_no_secret(family, database):
    await _store(family)
    cap = await capability.capability_for(_principal(family), "portal")
    assert cap.allow_hosts == frozenset({"portal.example.com"})
    # Nothing on it, and nothing in how it prints, is a credential.
    blob = repr(cap) + str(cap.__dict__)
    assert "secret-cookie-value" not in blob and "proxy-in-1" not in blob


async def test_without_a_browser_the_task_is_refused_rather_than_skipped(family, database):
    await _store(family)
    p = _principal(family)
    cap = await capability.capability_for(p, "portal")
    with pytest.raises(capability.NoDriver):
        await capability.perform(p, cap, task="read circulars", reason="weekly")


async def test_only_the_driver_is_handed_the_lease(family, database, monkeypatch):
    seen = {}

    class Fake:
        async def run(self, lease, *, task):
            seen["cookies"] = lease.state.cookies
            seen["hosts"] = lease.allow_hosts
            return capability.Outcome(pages=[disposable.Page(
                url="https://portal.example.com/circulars", title="Circulars",
                text="Two new notices.", sha256="0" * 64, bytes=42, truncated=False)])

    await _store(family)
    p = _principal(family)
    monkeypatch.setattr(capability, "_driver", Fake())
    cap = await capability.capability_for(p, "portal")
    out = await capability.perform(p, cap, task="read circulars", reason="weekly")

    assert seen["cookies"][0]["value"] == "secret-cookie-value"
    assert seen["hosts"] == frozenset({"portal.example.com"})
    assert out.pages[0].title == "Circulars"


async def test_a_page_from_outside_the_grant_is_refused_after_the_fact(family, database, monkeypatch):
    class Wanderer:
        async def run(self, lease, *, task):
            return capability.Outcome(pages=[disposable.Page(
                url="https://elsewhere.example.com/x", title="Elsewhere",
                text="", sha256="0" * 64, bytes=1, truncated=False)])

    await _store(family)
    p = _principal(family)
    monkeypatch.setattr(capability, "_driver", Wanderer())
    cap = await capability.capability_for(p, "portal")
    with pytest.raises(disposable.Refused):
        await capability.perform(p, cap, task="read", reason="weekly")


async def test_a_capability_that_drifted_from_the_stored_grant_is_not_honoured(family, database):
    await _store(family)
    p = _principal(family)
    widened = capability.Capability(service="portal",
                                    allow_hosts=frozenset({"portal.example.com", "anything.example.com"}),
                                    describes="widened by hand")
    with pytest.raises(Invalid):
        await capability.perform(p, widened, task="read", reason="weekly")


async def test_sessions_are_listed_without_what_they_hold(family, database):
    await _store(family)
    [row] = await sessions.list_for(_principal(family))
    assert row["service"] == "portal"
    assert "sealed_state" not in row and "cookies" not in row


async def test_household_erasure_reaches_a_signed_in_service(family, database):
    """Step 0 of erasure nulls the wrapped key, before a single row is
    deleted. From that instant a stored session is ciphertext nobody can open
    -- which is what a persistent on-disk browser profile cannot offer."""
    await _store(family)
    p = _principal(family)

    await database.execute("UPDATE households SET status = 'erasing', wrapped_key = NULL WHERE id = $1",
                           p.household_id)
    with pytest.raises(sessions.SessionLapsed):
        async with sessions.lease(p, "portal", reason="check"):
            pass

    # And the rows go with the household, by cascade.
    await database.execute("DELETE FROM households WHERE id = $1", p.household_id)
    assert await database.fetchval("SELECT count(*) FROM sealed_sessions") == 0
