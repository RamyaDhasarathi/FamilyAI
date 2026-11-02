"""Child and teen mode: a separate narrow key, the child's own day, a private journal, and the one button."""
import datetime as dt
import uuid

from familyos import clock
from tests.conftest import pdf
from tests.test_brief import _obligation

TODAY = clock.today()


async def _key(family, child=None):
    child = child or family.younger
    r = await family.client.post(f"/v1/members/{child['id']}/kid-key", headers=family.h("amma"), json={"days": 30})
    assert r.status_code == 201, r.text
    return r.json()


def _k(key):
    return {"authorization": "Bearer " + key["token"]}


async def test_a_guardian_gives_a_child_a_key_and_it_reaches_only_their_day(family):
    key = await _key(family)
    assert key["path"].startswith("/kid/#kid_")
    day = (await family.client.get("/v1/kid/day", headers=_k(key))).json()
    assert day["name"] == family.younger["display_name"].split()[0] and day["date"] == TODAY.isoformat()
    # the key is good for nothing else: not the household, not a member's calls
    for path in ("/v1/me", "/v1/household", "/v1/inbox", "/v1/decisions", "/v1/finance/budgets"):
        assert (await family.client.get(path, headers=_k(key))).status_code == 401
    # and a member's token is not a child's key
    assert (await family.client.get("/v1/kid/day", headers=family.h("amma"))).status_code == 401


async def test_only_a_guardian_issues_or_revokes_and_a_revoked_key_stops(family):
    assert (await family.client.post(f"/v1/members/{family.younger['id']}/kid-key", headers=family.h("paati"), json={})).status_code == 403
    assert (await family.client.post(f"/v1/members/{family.amma['id']}/kid-key", headers=family.h("amma"), json={})).status_code == 404       # an adult is not a child
    key = await _key(family)
    assert (await family.client.delete(f"/v1/kid-keys/{key['id']}", headers=family.h("amma"))).status_code == 204
    assert (await family.client.get("/v1/kid/day", headers=_k(key))).status_code == 401
    keys = (await family.client.get(f"/v1/members/{family.younger['id']}/kid-keys", headers=family.h("amma"))).json()
    assert keys[0]["active"] is False and "token" not in keys[0]


async def test_the_routine_and_the_ticks_are_the_childs(family):
    await family.client.put(f"/v1/members/{family.younger['id']}/kid-routine", headers=family.h("amma"),
                            json={"items": [{"slot": "morning", "label": "Brush teeth", "icon": "🪥"}, {"slot": "evening", "label": "Pack the bag", "icon": "🎒"}]})
    key = await _key(family)
    day = (await family.client.get("/v1/kid/day", headers=_k(key))).json()
    assert [x["label"] for x in day["morning"]] == ["Brush teeth"] and [x["label"] for x in day["evening"]] == ["Pack the bag"]
    first = day["morning"][0]
    await family.client.post("/v1/kid/check", headers=_k(key), json={"key": first["key"], "done": True})
    assert (await family.client.get("/v1/kid/day", headers=_k(key))).json()["morning"][0]["done"] is True
    await family.client.post("/v1/kid/check", headers=_k(key), json={"key": first["key"], "done": False})
    assert (await family.client.get("/v1/kid/day", headers=_k(key))).json()["morning"][0]["done"] is False


async def test_today_and_what_to_bring_come_from_shared_notices_about_the_child(family, database):
    a = (await family.upload("amma", pdf(str(uuid.uuid4())), visibility="shared")).json()["artifact"]["id"]
    oid = await _obligation(database, family, artifact_id=a, due=TODAY + dt.timedelta(days=1), status="accepted", title="Sports day", action="attend")
    await database.execute("UPDATE obligations SET subject_member_id = $2 WHERE id = $1", oid, uuid.UUID(family.younger["id"]))
    eid = await database.fetchval("SELECT id FROM extractions WHERE artifact_id = $1", uuid.UUID(a))
    await database.execute("INSERT INTO claims (id, extraction_id, household_id, artifact_id, ordinal, kind, title, quote, confidence) VALUES ($1,$2,$3,$4,9,'instruction','Wear the house T-shirt','x',0.9)",
                           uuid.uuid4(), eid, uuid.UUID(family.household["id"]), uuid.UUID(a))
    private = (await family.upload("amma", pdf(str(uuid.uuid4())), visibility="private")).json()["artifact"]["id"]
    oid2 = await _obligation(database, family, artifact_id=private, due=TODAY, status="accepted", title="Private appointment", action="attend")
    await database.execute("UPDATE obligations SET subject_member_id = $2 WHERE id = $1", oid2, uuid.UUID(family.younger["id"]))
    day = (await family.client.get("/v1/kid/day", headers=_k(await _key(family)))).json()
    assert [(i["title"], i["when"]) for i in day["today"]] == [("Sports day", "tomorrow")]
    assert [b["text"] for b in day["bring"]] == ["Wear the house T-shirt"]


async def test_asking_a_parent_becomes_a_card_and_the_answer_comes_back(family, monkeypatch):
    from familyos import notify
    told = []

    async def member(member_id, subject, body, buttons=None):
        told.append(subject)
        return "test"
    monkeypatch.setattr(notify, "member", member)
    key = await _key(family)
    r = await family.client.post("/v1/kid/ask", headers=_k(key), json={"text": "Can I go to Riya's on Saturday?"})
    assert r.status_code == 201 and any("asks" in t for t in told)
    cards = (await family.client.get("/v1/decisions", headers=family.h("amma"))).json()
    card = next(c for c in cards if c["kind"] == "kid_request")
    assert "Riya" in card["title"] and [a["key"] for a in card["actions"]] == ["yes", "no", "later"]
    yes = card["actions"][0]
    assert (await family.client.request(yes["method"], yes["path"], headers=family.h("amma"), json=yes["body"])).status_code == 200
    asked = (await family.client.get("/v1/kid/day", headers=_k(key))).json()["asked"]
    assert asked[0]["answer"] == "yes"
    assert [c for c in (await family.client.get("/v1/decisions", headers=family.h("amma"))).json() if c["kind"] == "kid_request"] == []


async def test_too_many_questions_in_an_hour_slow_down(family, monkeypatch):
    from familyos import notify

    async def member(*a, **k):
        return "test"
    monkeypatch.setattr(notify, "member", member)
    key = await _key(family)
    codes = [(await family.client.post("/v1/kid/ask", headers=_k(key), json={"text": f"q{i}"})).status_code for i in range(7)]
    assert codes[:5] == [201] * 5 and codes[5] == 429


async def test_the_journal_is_the_childs_and_a_guardian_reads_only_what_is_shared(family):
    key = await _key(family)
    a = (await family.client.post("/v1/kid/journal", headers=_k(key), json={"text": "I felt left out at lunch."})).json()["id"]
    await family.client.post("/v1/kid/journal", headers=_k(key), json={"text": "I scored a goal!"})
    assert (await family.client.get(f"/v1/members/{family.younger['id']}/kid-journal", headers=family.h("amma"))).json() == []
    assert (await family.client.post(f"/v1/kid/journal/{a}/share", headers=_k(key))).json() == {"shared": True}
    shared = (await family.client.get(f"/v1/members/{family.younger['id']}/kid-journal", headers=family.h("amma"))).json()
    assert [e["text"] for e in shared] == ["I felt left out at lunch."]
    assert (await family.client.get(f"/v1/members/{family.younger['id']}/kid-journal", headers=family.h("paati"))).status_code == 403
    assert len((await family.client.get("/v1/kid/journal", headers=_k(key))).json()) == 2


async def test_pressing_i_need_a_grown_up_tells_the_adults_now(family, monkeypatch):
    from familyos import notify
    told = []

    async def member(member_id, subject, body, buttons=None):
        told.append((str(member_id), subject))
        return "test"
    monkeypatch.setattr(notify, "member", member)
    assert (await family.client.post("/v1/kid/help", headers=_k(await _key(family)))).json() == {"told": True}
    assert {t[0] for t in told} >= {family.amma["id"], family.appa["id"]} and "needs a grown-up" in told[0][1]


async def test_a_childs_own_goal_and_allowance_show_in_their_day_and_not_the_households(family):
    g = (await family.client.post("/v1/finance/goals", headers=family.h("amma"), json={"title": "Bicycle", "target_amount": 4000, "owner_member_id": family.younger["id"]})).json()
    await family.client.post(f"/v1/finance/goals/{g['id']}/contribute", headers=family.h("amma"), json={"amount": 500, "note": "allowance"})
    day = (await family.client.get("/v1/kid/day", headers=_k(await _key(family)))).json()
    assert day["goals"] == [{"title": "Bicycle", "target": 4000.0, "saved": 500.0, "currency": "INR", "percent": 12.5}]
    assert (await family.client.get("/v1/finance/goals", headers=family.h("amma"))).json() == []
    assert (await family.client.post("/v1/finance/goals", headers=family.h("paati"), json={"title": "x", "target_amount": 5, "owner_member_id": family.younger["id"]})).status_code == 403
