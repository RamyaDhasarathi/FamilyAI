"""The chat's opening message: cards with the answer one tap away, made from the household's own record."""
import datetime as dt
import uuid

from familyos import cards, clock, suggest
from familyos.db import pool
from familyos.identity import Principal
from tests.test_phone_reminders import _obligation
from tests.test_suggest import _accepted

TODAY = clock.today()


def _p(family, who="amma"):
    m = getattr(family, who)
    return Principal(member_id=uuid.UUID(m["id"]), household_id=uuid.UUID(family.household["id"]), role=m["role"], display_name=m["display_name"])


async def test_a_date_waiting_for_a_yes_becomes_an_action_card_with_accept_and_not_this(family, database):
    _, oid = await _obligation(family, database, "Pay the bus fee", TODAY + dt.timedelta(days=2), status="proposed")
    opening = await cards.opening(_p(family))
    assert "1 thing waiting for your yes" in opening["say"]
    card = next(c for c in opening["cards"] if c["type"] == "action" and c["title"] == "Pay the bus fee")
    assert [b["label"] for b in card["buttons"]] == ["Accept", "Not this"]
    yes = await family.client.post(f"/v1/chat/pending/{card['buttons'][0]['id']}/confirm", headers=family.h("amma"))
    assert yes.status_code == 200, yes.text
    assert await pool().fetchval("SELECT status FROM obligations WHERE id = $1", oid) == "accepted"


async def test_not_this_dismisses_and_the_other_button_then_does_nothing(family, database):
    _, oid = await _obligation(family, database, "Buy the sports kit", TODAY + dt.timedelta(days=2), status="proposed")
    card = next(c for c in (await cards.opening(_p(family)))["cards"] if c["type"] == "action")
    no = await family.client.post(f"/v1/chat/pending/{card['buttons'][1]['id']}/confirm", headers=family.h("amma"))
    assert no.status_code == 200 and await pool().fetchval("SELECT status FROM obligations WHERE id = $1", oid) == "dismissed"


async def test_a_suggestion_is_added_with_one_tap_and_not_now_is_remembered(family, database):
    await _accepted(family, "Aarav's birthday party", TODAY + dt.timedelta(days=6))
    p = _p(family)
    first = next(c for c in (await cards.opening(p))["cards"] if c["type"] == "action" and "Gift" in c["title"])
    assert [b["label"] for b in first["buttons"]][:2] == ["Add", "Not now"]
    cancel = await family.client.post(f"/v1/chat/pending/{first['buttons'][1]['id']}/cancel", headers=family.h("amma"))
    assert cancel.status_code == 204
    assert not [s for s in await suggest.for_member(p) if "Gift" in s["title"]]            # it is not offered again
    again = [c for c in (await cards.opening(p))["cards"] if c["type"] == "action" and "Gift" in c["title"]]
    assert again == []


async def test_nothing_waiting_still_gives_chips_and_no_action_cards(family):
    opening = await cards.opening(_p(family))
    assert opening["say"].startswith("Nothing is waiting")
    assert opening["cards"][-1]["type"] == "chips" and not [c for c in opening["cards"] if c["type"] == "action"]


async def test_another_member_cannot_press_a_card_made_for_someone_else(family, database):
    await _obligation(family, database, "Pay the bus fee", TODAY + dt.timedelta(days=2), status="proposed")
    card = next(c for c in (await cards.opening(_p(family)))["cards"] if c["type"] == "action")
    other = await family.client.post(f"/v1/chat/pending/{card['buttons'][0]['id']}/confirm", headers=family.h("appa"))
    assert other.status_code == 404


async def test_the_opening_route_returns_the_same_cards(family, database):
    await _obligation(family, database, "Pay the bus fee", TODAY + dt.timedelta(days=2), status="proposed")
    r = await family.client.get("/v1/chat/opening", headers=family.h("amma"))
    assert r.status_code == 200 and r.json()["cards"][0]["type"] == "action"
