"""DELETE /v1/members/{id}: a guardian removes a member for good, as the phone
app does once its Undo window closes. What is theirs goes with them,
including the household records they created (decided 29 Oct 2026)."""
import uuid

from familyos import db, erasure


async def remove(family, who, member):
    return await family.client.delete(f"/v1/members/{member['id']}", headers=family.h(who))


async def test_a_guardian_removes_a_member_and_their_sessions_go_with_them(family):
    r = await remove(family, "amma", family.paati)
    assert r.status_code == 204, r.text
    assert await db.pool().fetchval("SELECT count(*) FROM members WHERE id = $1", family.paati["id"]) == 0
    assert await db.pool().fetchval("SELECT count(*) FROM member_tokens WHERE member_id = $1", family.paati["id"]) == 0
    assert (await family.client.get("/v1/me", headers=family.h("paati"))).status_code == 401
    audit = await db.pool().fetchrow("SELECT detail FROM audit_events WHERE action = 'member.removed' AND target_id = $1",
                                     family.paati["id"])
    assert audit["detail"] == {"role": "adult"}


async def test_a_child_can_be_removed(family):
    assert (await remove(family, "amma", family.younger)).status_code == 204


async def test_the_regular_payments_they_created_go_with_them(family):
    await db.pool().execute(
        "INSERT INTO standing_obligations (id, household_id, created_by, title, payee, amount, day_of_month) "
        "VALUES ($1, $2, $3, 'Rent', 'Landlord', 25000, 5)", uuid.uuid4(), family.household["id"], family.paati["id"])
    assert (await remove(family, "amma", family.paati)).status_code == 204
    assert await db.pool().fetchval("SELECT count(*) FROM standing_obligations WHERE household_id = $1",
                                    family.household["id"]) == 0


async def test_only_a_guardian_removes_and_never_themselves(family):
    assert (await remove(family, "paati", family.younger)).status_code == 403
    r = await remove(family, "amma", family.amma)
    assert r.status_code == 422 and "yourself" in r.json()["detail"]
    assert await db.pool().fetchval("SELECT count(*) FROM members WHERE household_id = $1", family.household["id"]) == 5


async def test_an_unknown_member_or_one_from_another_household_is_not_found(family, client):
    from conftest import Family
    other = await Family(client).setup("Another family", "other@example.com")
    assert (await remove(family, "amma", {"id": "00000000-0000-0000-0000-000000000000"})).status_code == 404
    assert (await remove(family, "amma", other.paati)).status_code == 404
    assert await db.pool().fetchval("SELECT count(*) FROM members WHERE id = $1", other.paati["id"]) == 1


async def test_their_linked_whatsapp_browser_is_forgotten_first(family, monkeypatch):
    forgotten = []

    async def forget(household_id, member_ids=None):
        forgotten.append((str(household_id), [str(m) for m in member_ids]))
        return len(member_ids)
    monkeypatch.setattr(erasure, "_forget_browsers", forget)
    assert (await remove(family, "amma", family.paati)).status_code == 204
    assert forgotten == [(family.household["id"], [family.paati["id"]])]


async def _family_key(family, holders):
    pool = db.pool()
    await pool.execute("UPDATE households SET key_mode = 'family' WHERE id = $1", family.household["id"])
    await pool.execute("INSERT INTO family_keys (household_id, threshold, shares, wrapped_key, pending) VALUES ($1, 2, 3, $2, FALSE)",
                       family.household["id"], b"wrapped")
    for m in holders:
        await pool.execute("INSERT INTO family_key_share_seals (id, household_id, member_id, credential_id, prf_salt, wrapped_share) "
                           "VALUES ($1, $2, $3, $4, $5, $6)", uuid.uuid4(), family.household["id"], m["id"], b"c", b"s", b"w")


async def test_removal_is_refused_while_it_would_leave_the_family_key_unopenable(family):
    await _family_key(family, [family.appa, family.paati])          # two of two needed shares held on passkeys
    r = await remove(family, "amma", family.paati)
    assert r.status_code == 422 and "family key" in r.json()["detail"]
    assert await db.pool().fetchval("SELECT count(*) FROM members WHERE id = $1", family.paati["id"]) == 1


async def test_removal_goes_ahead_when_enough_shares_remain(family):
    await _family_key(family, [family.amma, family.appa, family.paati])
    assert (await remove(family, "amma", family.paati)).status_code == 204
    assert (await remove(family, "amma", family.younger)).status_code == 204     # holds no share at all
