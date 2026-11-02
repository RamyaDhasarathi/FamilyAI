"""Hand-offs that close the loop: answered, moved on, escalated to a backup, and counted plainly."""
import uuid

from familyos import clock, handoffs
from tests.conftest import pdf


async def _handed(family, who_to="appa", **extra):
    a = (await family.upload("amma", pdf(str(uuid.uuid4())), visibility="shared")).json()["artifact"]["id"]
    body = {"member_id": family[who_to]["id"] if isinstance(family, dict) else getattr(family, who_to)["id"], "note": "Please see to this", **extra}
    r = await family.client.post(f"/v1/artifacts/{a}/assign", headers=family.h("amma"), json=body)
    assert r.status_code == 200, r.text
    return a, r.json()


async def test_a_hand_off_waits_for_an_answer_and_shows_on_both_sides(family):
    a, made = await _handed(family)
    assert made["assigned_ack"] == "pending"
    sender = (await family.client.get("/v1/handoffs", headers=family.h("amma"))).json()["items"]
    assert [(x["direction"], x["state"]) for x in sender] == [("waiting_on", "pending")]
    mine = (await family.client.get("/v1/handoffs", headers=family.h("appa"))).json()["items"]
    assert [(x["direction"], x["state"]) for x in mine] == [("for_me", "pending")]
    card = (await family.client.get("/v1/decisions", headers=family.h("appa"))).json()[0]
    assert [x["key"] for x in card["actions"]][:2] == ["accept", "decline"] and "answer" in card["recommendation"]["text"]


async def test_accepting_tells_the_sender_and_clears_the_question(family):
    a, _ = await _handed(family)
    r = await family.client.post(f"/v1/artifacts/{a}/acknowledge", headers=family.h("appa"), json={"response": "accept"})
    assert r.json() == {"state": "accepted"}
    assert (await family.client.get("/v1/handoffs", headers=family.h("amma"))).json()["items"][0]["state"] == "accepted"
    assert (await family.client.post(f"/v1/artifacts/{a}/acknowledge", headers=family.h("appa"), json={"response": "accept"})).status_code == 403   # once


async def test_only_the_assignee_can_answer(family):
    a, _ = await _handed(family)
    assert (await family.client.post(f"/v1/artifacts/{a}/acknowledge", headers=family.h("amma"), json={"response": "accept"})).status_code == 403


async def test_declining_with_a_suggestion_moves_it_and_it_must_be_answered_again(family):
    a, _ = await _handed(family)
    r = await family.client.post(f"/v1/artifacts/{a}/acknowledge", headers=family.h("appa"),
                                 json={"response": "decline", "propose_member_id": family.paati["id"]})
    assert r.status_code == 200 and r.json()["state"] == "moved", r.text
    paati = (await family.client.get("/v1/handoffs", headers=family.h("paati"))).json()["items"]
    assert paati and paati[0]["state"] == "pending"


async def test_declining_with_no_suggestion_returns_it_to_the_sender(family):
    a, _ = await _handed(family)
    r = await family.client.post(f"/v1/artifacts/{a}/acknowledge", headers=family.h("appa"), json={"response": "decline"})
    assert r.json() == {"state": "returned"}
    assert (await family.client.get("/v1/handoffs", headers=family.h("appa"))).json()["items"] == []


async def test_nobody_answering_moves_it_to_the_backup_once(family, database, monkeypatch):
    from familyos import notify
    sent = []

    async def member(member_id, subject, body, buttons=None):
        sent.append((str(member_id), subject))
        return "test"
    monkeypatch.setattr(notify, "member", member)
    a, _ = await _handed(family, backup_member_id=family.paati["id"])
    await database.execute("UPDATE input_artifacts SET assigned_at = NOW() - interval '30 hours' WHERE id = $1", uuid.UUID(a))
    out = await handoffs.sweep()
    assert out["to_backup"] == 1
    paati = (await family.client.get("/v1/handoffs", headers=family.h("paati"))).json()["items"]
    assert paati and paati[0]["state"] == "pending"
    assert any(s[0] == family.paati["id"] for s in sent) and any(s[0] == family.amma["id"] for s in sent)
    assert (await handoffs.sweep()) == {"to_backup": 0, "told_sender": 0}                  # once


async def test_no_backup_means_the_sender_is_told_and_nothing_moves(family, database, monkeypatch):
    from familyos import notify
    sent = []

    async def member(member_id, subject, body, buttons=None):
        sent.append((str(member_id), subject))
        return "test"
    monkeypatch.setattr(notify, "member", member)
    a, _ = await _handed(family)
    await database.execute("UPDATE input_artifacts SET assigned_at = NOW() - interval '30 hours' WHERE id = $1", uuid.UUID(a))
    assert (await handoffs.sweep())["told_sender"] == 1
    assert any(s[0] == family.amma["id"] and "No answer" in s[1] for s in sent)
    mine = (await family.client.get("/v1/handoffs", headers=family.h("appa"))).json()["items"]
    assert mine and mine[0]["state"] == "pending"


async def test_a_young_hand_off_is_left_alone(family):
    await _handed(family)
    assert await handoffs.sweep() == {"to_backup": 0, "told_sender": 0}


async def test_workload_is_plain_counts_for_adults_only(family):
    await _handed(family)
    rows = (await family.client.get("/v1/workload", headers=family.h("amma"))).json()
    by = {r["name"]: r for r in rows}
    assert by[family.appa["display_name"]]["open"] == 1 and by[family.amma["display_name"]]["open"] == 0
    assert clock.today() and all(set(r) == {"member_id", "name", "open", "handled_30d"} for r in rows)
