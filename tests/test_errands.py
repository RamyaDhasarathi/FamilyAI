"""An errand: a booking or purchase on a signed-in site, written down in
full, fingerprinted, approved by a guardian against exactly that. Nothing
runs until then; nothing here holds a card."""
import uuid

from familyos import chat, errands
from familyos.execution import sessions
from familyos.execution.sessions import SessionState
from familyos.identity import Principal
from familyos.settings import settings


def _p(family, who="amma"):
    m = getattr(family, who)
    return Principal(member_id=uuid.UUID(m["id"]), household_id=uuid.UUID(family.household["id"]),
                     role=m["role"], display_name=m["display_name"])


async def _signed_in(family, who="amma"):
    await sessions.store(_p(family, who), service="urbancompany",
                         state=SessionState(cookies=[{"name": "_uc_user_token", "value": "x", "domain": ".urbancompany.com"}]),
                         allow_hosts=["www.urbancompany.com", "urbancompany.com"])


SPEC = {"what": "Kitchen deep clean", "details": "Saturday morning", "when": {"date": "2031-10-11", "part": "morning"},
        "max_amount": 3000, "currency": "INR", "payment": "pay_after_service"}


async def test_an_errand_needs_a_signed_in_site_and_is_written_down_in_full(family, database):
    r = await family.client.post("/v1/errands", headers=family.h("amma"),
                                 json={"service": "urbancompany", "title": "Kitchen deep clean", "spec": SPEC})
    assert r.status_code == 422 and "sign in on the Household page" in r.text
    await _signed_in(family)
    r = await family.client.post("/v1/errands", headers=family.h("amma"),
                                 json={"service": "urbancompany", "title": "Kitchen deep clean", "spec": SPEC})
    assert r.status_code == 201, r.text
    e = r.json()
    assert e["status"] == "proposed" and e["kind"] == "booking" and len(e["params_sha256"]) == 64
    sp = e["spec"]
    assert sp["where"] == {"service": "urbancompany", "hosts": ["www.urbancompany.com", "urbancompany.com"], "address": "the saved home address"}
    assert sp["limits"] == {"max_amount": 3000.0, "currency": "INR", "quantity": 1}
    assert sp["payment"]["card_held_by_familyos"] is False and sp["payment"]["mode"] == "pay_after_service"
    assert sp["stop_rules"]["unexpected_payment_prompt"] == "stop" and sp["stop_rules"]["alternative_service"] == "needs_you"
    assert sp["when"] == {"date": "2031-10-11", "time": None, "part": "morning", "by": None}
    # A site off the list, or no amount, is refused.
    r = await family.client.post("/v1/errands", headers=family.h("amma"), json={"service": "amazon", "title": "x", "spec": SPEC})
    assert r.status_code == 422
    r = await family.client.post("/v1/errands", headers=family.h("amma"), json={"service": "urbancompany", "title": "x", "spec": {**SPEC, "max_amount": 0}})
    assert r.status_code == 422


async def test_only_a_guardian_approves_and_only_exactly_what_was_shown(family, database):
    await _signed_in(family)
    e = (await family.client.post("/v1/errands", headers=family.h("paati"),
                                  json={"service": "urbancompany", "title": "Sofa cleaning", "spec": SPEC})).json()
    r = await family.client.post(f"/v1/errands/{e['id']}/approve", headers=family.h("paati"), json={"params_sha256": e["params_sha256"]})
    assert r.status_code == 403
    r = await family.client.post(f"/v1/errands/{e['id']}/approve", headers=family.h("appa"), json={"params_sha256": "0" * 64})
    assert r.status_code == 422 and "not what you were shown" in r.text
    # Changed underneath: no approval applies.
    await database.execute("UPDATE errands SET spec = spec || '{\"what\": \"Sofa cleaning and a bathroom\"}' WHERE id = $1", uuid.UUID(e["id"]))
    r = await family.client.post(f"/v1/errands/{e['id']}/approve", headers=family.h("appa"), json={"params_sha256": e["params_sha256"]})
    assert r.status_code == 422 and "changed since it was proposed" in r.text
    await database.execute("UPDATE errands SET spec = $2 WHERE id = $1", uuid.UUID(e["id"]), e["spec"])
    r = await family.client.post(f"/v1/errands/{e['id']}/approve", headers=family.h("appa"), json={"params_sha256": e["params_sha256"]})
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "approved" and r.json()["approved_by"] == family.appa["id"]
    # Approved, and the run is queued for the site's runbook.
    assert await database.fetchval("SELECT count(*) FROM jobs WHERE kind = $1", errands.KIND) == 1
    acts = [r["action"] for r in await database.fetch("SELECT action FROM audit_events WHERE action LIKE 'errand.%' ORDER BY at")]
    assert acts == ["errand.proposed", "errand.approved"]
    r = await family.client.post(f"/v1/errands/{e['id']}/cancel", headers=family.h("amma"))
    assert r.status_code == 200 and r.json()["status"] == "cancelled"
    assert [x["status"] for x in (await family.client.get("/v1/errands", headers=family.h("amma"))).json()] == ["cancelled"]


async def test_with_a_runbook_approval_queues_the_run(family, database):
    await _signed_in(family)
    ran = []

    async def book(row):
        ran.append(row["id"])
        return {"ran": str(row["id"])}
    before = errands.runbooks().get("urbancompany")
    errands.use_runbook("urbancompany", book)
    try:
        e = (await family.client.post("/v1/errands", headers=family.h("amma"),
                                      json={"service": "urbancompany", "title": "Kitchen deep clean", "spec": SPEC})).json()
        r = await family.client.post(f"/v1/errands/{e['id']}/approve", headers=family.h("amma"), json={"params_sha256": e["params_sha256"]})
        assert r.status_code == 200
        job = await database.fetchrow("SELECT * FROM jobs WHERE kind = $1", errands.KIND)
        assert job["spec"]["errand_id"] == e["id"]
        assert (await errands._handle(dict(job), None))["ran"] == e["id"] and ran == [uuid.UUID(e["id"])]
    finally:
        # Put the real runbook back: the registry is shared by the whole suite.
        if before is not None:
            errands.use_runbook("urbancompany", before)
        else:
            errands.runbooks().pop("urbancompany", None)


async def test_the_chat_proposes_an_errand_only_for_a_signed_in_site(family, database, monkeypatch):
    monkeypatch.setattr(settings, "ask_enabled", True)

    class M:
        name = "scripted"
        system = None

        async def reply(self, system, messages, schema=None):
            M.system = system
            return {"say": "Here it is to approve.", "proposals": [
                {"kind": "errand", "service": "urbancompany", "title": "Kitchen deep clean", "what": "kitchen deep clean",
                 "details": "Saturday morning", "due_date": "2031-10-11", "part": "morning", "max_amount": 3000, "currency": "INR"}]}
    chat.use_model(M())
    try:
        out = await chat.turn(_p(family), "book a kitchen deep clean on urban company saturday morning under 3000")
        [p] = out["proposals"]
        assert not p["ok"] and "sign in on the Household page" in p["why"]
        assert "SIGNED-IN SITES: none" in M.system
        await _signed_in(family)
        out = await chat.turn(_p(family), "book it")
        [p] = out["proposals"]
        assert p["ok"] and p["label"] == "Urban Company" and p["max_amount"] == 3000.0 and p["part"] == "morning"
        assert "SIGNED-IN SITES: Urban Company (urbancompany)" in M.system
    finally:
        chat.use_model(chat.RefusingModel())


async def test_the_errand_proposal_crosses_the_api_with_its_time(family, database, monkeypatch):
    """Through POST /chat, not only chat.turn: the response model has to carry it."""
    monkeypatch.setattr(settings, "ask_enabled", True)
    await _signed_in(family)

    class M:
        name = "scripted"

        async def reply(self, system, messages, schema=None):
            return {"say": "Here it is.", "proposals": [
                {"kind": "errand", "service": "urbancompany", "title": "AC deep cleaning", "what": "AC service deep cleaning",
                 "details": "tomorrow 3.30PM", "due_date": "2031-10-08", "due_time": None, "part": "any", "max_amount": 1000, "currency": "INR"}]}
    chat.use_model(M())
    try:
        r = await family.client.post("/v1/chat", headers=family.h("amma"), json={"message": "book me an ac service deep cleaning tomorrow 3.30PM, budget 1000"})
    finally:
        chat.use_model(chat.RefusingModel())
    assert r.status_code == 200, r.text
    [p] = r.json()["proposals"]
    assert p["kind"] == "errand" and p["ok"] and p["label"] == "Urban Company" and p["max_amount"] == 1000.0
    assert p["due_time"] == "15:30:00"           # read from the person's own words
    r = await family.client.post("/v1/errands", headers=family.h("amma"), json={
        "service": "urbancompany", "title": p["title"], "spec": {"what": p["what"], "details": p["details"],
        "when": {"date": p["due_date"], "time": p["due_time"][:5], "part": "any"}, "max_amount": p["max_amount"], "currency": "INR"}})
    assert r.status_code == 201, r.text
    assert r.json()["spec"]["when"] == {"date": "2031-10-08", "time": "15:30", "part": "afternoon", "by": None}
