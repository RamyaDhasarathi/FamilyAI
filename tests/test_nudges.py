"""Heads-ups are pushed once, inside each person's quiet hours and cap, and never after a dismissal."""
from familyos import interruptions, notify, nudges
from tests.test_graph import _open_things


def _capture(monkeypatch):
    sent = []

    async def open_hours(member_id, local_now):      # the clock decides quiet hours; these tests are about what is sent, so never the clock
        return True, None
    monkeypatch.setattr(interruptions, "allow", open_hours)

    async def member(member_id, subject, body, buttons=None):
        sent.append({"to": str(member_id), "subject": subject, "body": body})
        return "test"
    monkeypatch.setattr(notify, "member", member)
    return sent


async def _pile(family, database):
    await family.consent(family.younger)
    await _open_things(family, database, family.younger["id"], ["Field trip form", "Cetirizine refill", "Book fair"])


async def test_a_new_heads_up_is_told_once_to_the_adults_who_can_see_it(family, database, monkeypatch):
    sent = _capture(monkeypatch)
    await _pile(family, database)
    out = await nudges.sweep()
    assert out["told"] >= 1 and out["failed"] == 0
    mine = [m for m in sent if m["to"] == family.amma["id"]]
    assert len(mine) == 1 and "Younger has 3 things" in mine[0]["subject"] + mine[0]["body"] and "Needs you" in mine[0]["body"]
    assert not any(m["to"] == family.younger["id"] for m in sent)                   # a child is not messaged
    again = len(sent)
    assert (await nudges.sweep())["told"] == 0 and len(sent) == again               # once


async def test_a_dismissed_heads_up_is_never_sent(family, database, monkeypatch):
    sent = _capture(monkeypatch)
    await _pile(family, database)
    (card,) = [c for c in (await family.client.get("/v1/decisions", headers=family.h("amma"))).json() if c["kind"] == "heads_up"]
    seen = next(a for a in card["actions"] if a["key"] == "seen")
    assert (await family.client.post(seen["path"], headers=family.h("amma"))).status_code == 204
    await nudges.sweep()
    assert not any(m["to"] == family.amma["id"] for m in sent)


async def test_quiet_hours_hold_it_back_and_it_goes_later_not_dropped(family, database, monkeypatch):
    sent = _capture(monkeypatch)
    await _pile(family, database)
    real = interruptions.allow                                    # the open-hours stand-in from _capture

    async def quiet(member_id, local_now):
        return False, "quiet hours"
    monkeypatch.setattr(interruptions, "allow", quiet)
    held = await nudges.sweep()
    assert held["told"] == 0 and held["waited"] >= 1 and sent == []
    monkeypatch.setattr(interruptions, "allow", real)
    assert (await nudges.sweep())["told"] >= 1 and any(m["to"] == family.amma["id"] for m in sent)


async def test_a_household_with_its_own_key_gets_a_heads_up_without_names_in_the_message(family, database, monkeypatch):
    sent = _capture(monkeypatch)
    await _pile(family, database)
    await database.execute("UPDATE households SET key_mode = 'family' WHERE id = $1", __import__("uuid").UUID(family.household["id"]))
    await nudges.sweep()
    mine = [m for m in sent if m["to"] == family.amma["id"]]
    assert mine and "Younger" not in mine[0]["subject"] + mine[0]["body"] and "Cetirizine" not in mine[0]["body"] and "Needs you" in mine[0]["body"]
