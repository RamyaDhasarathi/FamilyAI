"""Ranking what is suggested to a person by what that person accepts: counts per kind, no model, quiet after three
dismissals with no acceptance, never quiet for a date a day away, and the member can see and clear it."""
import datetime as dt
import uuid

from familyos import clock, feedback
from familyos.identity import Principal

TODAY = clock.today()


def _p(family, who="amma"):
    m = getattr(family, who)
    return Principal(member_id=uuid.UUID(m["id"]), household_id=uuid.UUID(family.household["id"]), role=m["role"], display_name=m["display_name"])


def _item(kind, days=10):
    return {"key": f"{uuid.uuid4()}:{kind}", "title": kind, "due_date": TODAY + dt.timedelta(days=days)}


def _kind(i):
    return i["key"].rsplit(":", 1)[-1]


def test_score_has_a_prior_so_one_tap_does_not_swing_it():
    assert feedback.score(None) == 0.5
    assert feedback.score({"accepted": 1, "dismissed": 0}) < 0.7
    assert feedback.score({"accepted": 5, "dismissed": 0}) > feedback.score({"accepted": 1, "dismissed": 0})
    assert feedback.score({"accepted": 0, "dismissed": 4}) < 0.2


def test_quiet_means_three_dismissals_and_no_acceptance():
    assert feedback.muted({"accepted": 0, "dismissed": 3}) and not feedback.muted({"accepted": 0, "dismissed": 2})
    assert not feedback.muted({"accepted": 1, "dismissed": 9})


async def test_what_a_person_accepts_comes_first_and_what_they_wave_away_goes_quiet(family):
    p = _p(family)
    for _ in range(3):
        await feedback.record(p, "gift", "accepted")
    for _ in range(3):
        await feedback.record(p, "ptm", "dismissed")
    items = [_item("ptm"), _item("clinic"), _item("gift")]
    ranked = await feedback.rank(p, items, kind=_kind, today=TODAY)
    assert [_kind(i) for i in ranked] == ["gift", "clinic"]                # ptm is quiet; gift beats an unknown kind


async def test_a_quiet_kind_still_shows_when_its_date_is_a_day_away(family):
    p = _p(family)
    for _ in range(3):
        await feedback.record(p, "exam", "dismissed")
    ranked = await feedback.rank(p, [_item("exam", days=1), _item("exam", days=9)], kind=_kind, today=TODAY)
    assert len(ranked) == 1 and ranked[0]["due_date"] == TODAY + dt.timedelta(days=1)


async def test_each_person_has_their_own_standing(family):
    for _ in range(3):
        await feedback.record(_p(family, "amma"), "gift", "dismissed")
    assert await feedback.rank(_p(family, "appa"), [_item("gift")], kind=_kind, today=TODAY)
    assert not await feedback.rank(_p(family, "amma"), [_item("gift")], kind=_kind, today=TODAY)


async def test_accepting_and_dismissing_through_the_routes_are_counted_and_can_be_cleared(family, database):
    h = family.h("amma")
    r = await family.client.get("/v1/me/learned", headers=h)
    assert r.json() == []
    await feedback.record(_p(family), "gift", "accepted")
    await feedback.record(_p(family), "gift", "dismissed")
    got = (await family.client.get("/v1/me/learned", headers=h)).json()
    assert got == [{"kind": "gift", "accepted": 1, "dismissed": 1, "quiet": False}]
    assert (await family.client.get("/v1/me/learned", headers=family.h("appa"))).json() == []
    assert (await family.client.delete("/v1/me/learned", headers=h)).json() == {"cleared": 2}
    assert (await family.client.get("/v1/me/learned", headers=h)).json() == []


async def test_an_offer_accepted_counts_once_as_accepted_not_also_as_dismissed(family, database):
    from familyos import offers
    p = _p(family)
    await database.execute("UPDATE households SET receipts_close_bills = FALSE WHERE id = $1", p.household_id)
    key = "closes:" + str(uuid.uuid4())
    await database.execute("INSERT INTO suggestion_dismissals (household_id, source_key, dismissed_by) VALUES ($1, 'x', $2)", p.household_id, p.member_id)
    await offers.dismiss(p, key)
    c = await feedback.counts(p)
    assert c["closes"] == {"accepted": 0, "dismissed": 1}
