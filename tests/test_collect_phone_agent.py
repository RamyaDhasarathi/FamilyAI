"""The phone agent (familyos/collect/phone_agent.py, decided 30 Oct 2026): the phone sends what it shows, the backend answers
one action, chosen by Claude (Sonnet 5.5) or, when Claude cannot be had, by the local MAI-UI. Every action is checked before
the phone gets it: only inside the app being read, never a tap that pays, orders, sends, calls or changes something, never
typing into a password field, never the same action three times. What it reads goes to the local cache, for that member only."""
import types

import pytest

from familyos.collect import phone_agent, store, two_agent
from familyos.settings import settings

PKG = "in.swiggy.android"


def node(text, left, t, r, b, **kw):
    return {"text": text, "contentDescription": "", "className": kw.pop("cls", "TextView"), "clickable": kw.pop("clickable", True),
            "scrollable": False, "bounds": {"left": left, "top": t, "right": r, "bottom": b}, **kw}


ORDERS = {"currentApp": PKG, "width": 1000, "height": 2000, "screenshot": "aGVsbG8=", "tree": [
    node("Account", 0, 1800, 250, 2000),
    node("Orders", 0, 200, 1000, 300),
    node("Reorder", 700, 400, 1000, 500),
    node("Biryani · Rs 349 · Delivered 12 Oct", 0, 400, 680, 500, clickable=False),
]}
CART = {**ORDERS, "tree": [node("Item total Rs 349", 0, 300, 1000, 400, clickable=False), node("Continue", 0, 1800, 1000, 2000)]}
LOGIN = {**ORDERS, "tree": [node("", 0, 300, 1000, 400, cls="EditText", editable=True, password=True, focused=True)]}


def run_for(**kw):
    return phone_agent.Run(id="r", email="amma@example.com", package=PKG, label="Swiggy", category="Food and Grocery",
                           task="read", model="claude-sonnet-5-5", started_at="2026-10-30T00:00:00+00:00", **kw)


@pytest.fixture(autouse=True)
def cache(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "collect_dir", str(tmp_path / "collect"))
    monkeypatch.setattr(settings, "anthropic_api_key", "sk-test")
    monkeypatch.setattr(phone_agent, "_runs", {})
    store.set_apps("amma@example.com", [{"package": PKG, "label": "Swiggy", "collect": True},
                                         {"package": "com.whatsapp", "label": "WhatsApp", "collect": False}])


def refused(action, obs, run=None):
    try:
        phone_agent.check(phone_agent.valid_action(action), obs, run or run_for())
    except phone_agent.Refused as exc:
        return str(exc)
    return None


def tap(x, y):
    return {"action": "tap", "target": {"description": "", "point": {"x": x, "y": y}}}


def test_reading_taps_pass_and_writing_ones_are_refused_by_the_words_under_the_finger():
    assert refused(tap(0.5, 0.125), ORDERS) is None                                     # "Orders"
    assert "would buy" in refused(tap(0.85, 0.225), ORDERS)                              # "Reorder"
    assert "would buy" in refused({"action": "tap", "target": {"description": "Pay now"}}, ORDERS)
    assert "checkout step" in refused(tap(0.5, 0.95), CART)                              # Continue under a bill
    assert "would place a call" in refused({"action": "tap", "target": {"description": "+91 98450 12345"}}, ORDERS)
    assert "password field" in refused({"action": "type", "text": "hunter2"}, LOGIN)
    assert "FamilyOS itself" in refused(tap(0.5, 0.5), {**ORDERS, "currentApp": phone_agent.OWN_APP})
    assert "not Swiggy" in refused(tap(0.5, 0.5), {**ORDERS, "currentApp": "com.whatsapp"})
    assert "only Swiggy" in refused({"action": "launch_app", "package": "com.whatsapp"}, ORDERS)
    r = run_for(actions=[phone_agent.valid_action(tap(0.5, 0.125))] * 2)
    assert "third time" in refused(tap(0.5, 0.125), ORDERS, r)
    for bad in ({"action": "rm -rf"}, {"action": "tap", "target": {"point": {"x": 3, "y": 0}}}, {"action": "swipe", "direction": "in"}):
        with pytest.raises(phone_agent.Refused):
            phone_agent.valid_action(bad)


def test_the_model_never_sees_a_password_fields_text():
    els = phone_agent.elements({**LOGIN, "tree": [{**LOGIN["tree"][0], "text": "••••••"}]})
    assert els[0]["label"] == "" and els[0]["password"]


class Use:
    def __init__(self, name, input, id="tu"):
        self.type, self.name, self.input, self.id = "tool_use", name, input, id

    def model_dump(self, **kw):
        return {"type": "tool_use", "id": self.id, "name": self.name, "input": self.input}


def reply(*blocks):
    return types.SimpleNamespace(content=list(blocks), usage=types.SimpleNamespace(input_tokens=5000, output_tokens=200))


def claude_says(monkeypatch, *replies):
    queue, sent = list(replies), []

    async def fake(run):
        sent.append([m for m in run.messages])
        return queue.pop(0)
    monkeypatch.setattr(phone_agent, "_ask_claude", fake)
    return sent


async def test_a_run_opens_the_app_reads_with_claude_and_keeps_what_it_read(family, monkeypatch):
    sent = claude_says(monkeypatch,
                       reply(Use("tap", {"element": 3}, "a")),                    # Reorder: refused, asked again
                       reply(Use("tap", {"element": 2}, "b")),                    # Orders
                       reply(Use("done", {"items": [{"id": "SW-1", "date": "12 Oct", "title": "Biryani", "amount": "Rs 349",
                                                     "status": "Delivered"}], "note": "1 order"}, "c")))
    r = await family.client.post("/v1/collect/phone/runs", headers=family.h("amma"), json={"package": PKG})
    assert r.status_code == 201, r.text
    run = r.json()
    assert run["model"] == "claude-sonnet-5-5" and "orders" in run["task"]
    step = f"/v1/collect/phone/runs/{run['run_id']}/step"
    first = (await family.client.post(step, headers=family.h("amma"), json={**ORDERS, "currentApp": "com.android.launcher"})).json()
    assert first["action"] == {"action": "launch_app", "package": PKG}
    second = (await family.client.post(step, headers=family.h("amma"), json=ORDERS)).json()
    assert second["action"]["action"] == "tap" and second["action"]["target"]["description"] == "Orders"
    assert any("Refused" in str(m) for m in sent[1])                                # the refusal went back to Claude
    third = (await family.client.post(step, headers=family.h("amma"), json=ORDERS)).json()
    assert third["status"] == "done" and third["kept"] == 1 and third["action"]["action"] == "done"
    assert third["cost_usd"] == pytest.approx(15_000 / 1e6 * 2 + 600 / 1e6 * 10)
    got = (await family.client.get(f"/v1/collect/apps/{PKG}/items", headers=family.h("amma"))).json()
    assert [(i["id"], i["title"]) for i in got["items"]] == [("SW-1", "Biryani")] and got["last_run"]["counts"]["kept"] == 1
    assert (await family.client.get(f"/v1/collect/apps/{PKG}/items", headers=family.h("appa"))).status_code == 404
    assert (await family.client.post(step, headers=family.h("appa"), json=ORDERS)).status_code == 404


class FakeModels:
    """The Mac's model server as two_agent.py calls it: /plan, /decide (scripted), /verify, /extract; MAI-UI apart."""

    def __init__(self, decisions, *, complete=True, items=None):
        self.decisions, self.complete, self.items = list(decisions), complete, items or []
        self.asked: list[dict] = []
        self.mai_ui: list[str] = []

    async def post(self, path, body):
        self.asked.append({"path": path, **body})
        if path == "/plan":
            return {"goals": ["read the orders"], "parts": [{"goal": "read the orders", "app": "Swiggy", "done_when": "orders listed"}]}
        if path == "/decide":
            return {"done": False, "last_ok": None, "remember": [], **self.decisions.pop(0)}
        if path == "/verify":
            return {"complete": self.complete, "missing": "" if self.complete else "more orders below"}
        if path == "/extract":
            return {"data": {"items": self.items}}
        raise AssertionError(path)

    async def analyze(self, instruction, history, obs, apps):
        self.mai_ui.append(instruction)
        return {"action": "press_back"}


def local_models(monkeypatch, *decisions, **kw):
    fake = FakeModels(decisions, **kw)
    monkeypatch.setattr(two_agent, "_post", fake.post)
    monkeypatch.setattr(two_agent, "_mai_ui", fake.analyze)
    return fake


async def test_when_claude_cannot_be_had_qwen_and_mai_ui_carry_on_the_collector_apps_way(family, monkeypatch):
    class Limit(Exception):
        body = {"error": {"message": "You have reached your specified API usage limits."}}

    async def refuses(run):
        raise Limit("400")
    monkeypatch.setattr(phone_agent, "_ask_claude", refuses)
    fake = local_models(monkeypatch,
                        {"instruction": 'tap "Orders"'},
                        {"instruction": "scroll down", "last_ok": True, "remember": ["Biryani · Rs 349 · Delivered 12 Oct"]},
                        {"done": True, "result": "1 order: Biryani Rs 349", "part_done": True},
                        items=[{"id": "SW-1", "date": "12 Oct", "title": "Biryani", "amount": "Rs 349", "status": "Delivered"}])
    run = (await family.client.post("/v1/collect/phone/runs", headers=family.h("amma"), json={"package": PKG})).json()
    step = f"/v1/collect/phone/runs/{run['run_id']}/step"
    a = (await family.client.post(step, headers=family.h("amma"), json=ORDERS)).json()
    assert a["model"] == phone_agent.LOCAL and a["fallback"] == "You have reached your specified API usage limits."
    assert a["action"]["action"] == "tap" and a["action"]["target"]["description"] == "Orders"      # by its label: no MAI-UI
    assert fake.mai_ui == [] and [x["path"] for x in fake.asked][:2] == ["/plan", "/decide"]
    b = (await family.client.post(step, headers=family.h("amma"), json=ORDERS)).json()
    assert b["action"] == {"action": "swipe", "direction": "up"}                                       # "scroll down" = finger up
    c = (await family.client.post(step, headers=family.h("amma"), json=ORDERS)).json()
    assert c["status"] == "done" and c["kept"] == 1
    assert any(x["path"] == "/verify" for x in fake.asked) and any(x["path"] == "/extract" for x in fake.asked)
    extract = next(x for x in fake.asked if x["path"] == "/extract")
    # The final answer is kept as a fact too when Qwen saved none with it (orchestrator.js keepAnswer).
    assert extract["observations"] == ["Biryani · Rs 349 · Delivered 12 Oct", "1 order: Biryani Rs 349"]
    got = (await family.client.get(f"/v1/collect/apps/{PKG}/items", headers=family.h("amma"))).json()["items"]
    assert [(i["id"], i["title"]) for i in got] == [("SW-1", "Biryani")]


async def test_on_the_macs_models_a_refused_tap_is_a_failed_step_and_a_repeat_stops_the_run(family, monkeypatch):
    fake = local_models(monkeypatch, {"instruction": 'tap "Reorder"'}, {"instruction": 'tap "Reorder"', "last_ok": False},
                        {"instruction": 'tap "Reorder"'})
    run = (await family.client.post("/v1/collect/phone/runs", headers=family.h("amma"), json={"package": PKG, "engine": "local"})).json()
    assert run["model"] == phone_agent.LOCAL and run["fallback"] is None
    step = f"/v1/collect/phone/runs/{run['run_id']}/step"
    first = (await family.client.post(step, headers=family.h("amma"), json=ORDERS)).json()
    assert first["action"] == {"action": "wait"}                                                       # refused, never tapped
    second = (await family.client.post(step, headers=family.h("amma"), json=ORDERS)).json()
    assert second["action"] == {"action": "wait"}
    assert any("✗" in h for h in next(x for x in reversed(fake.asked) if x["path"] == "/decide")["history"])
    third = (await family.client.post(step, headers=family.h("amma"), json=ORDERS)).json()
    assert third["status"] == "stopped" and "didn't work 2 times" in third["note"]


async def test_mai_uis_give_up_back_is_not_done_when_it_was_asked_to_tap(family, monkeypatch):
    fake = local_models(monkeypatch, {"instruction": "tap the filter icon at the top"})
    run = (await family.client.post("/v1/collect/phone/runs", headers=family.h("amma"), json={"package": PKG, "engine": "local"})).json()
    a = (await family.client.post(f"/v1/collect/phone/runs/{run['run_id']}/step", headers=family.h("amma"), json=ORDERS)).json()
    assert fake.mai_ui == ["tap the filter icon at the top"] and a["action"] == {"action": "wait"}


def test_the_collector_apps_shortcuts_and_grounding():
    assert two_agent.resolve_direct_action("Scroll down.") == {"action": "swipe", "direction": "up"}
    assert two_agent.resolve_direct_action('type "biryani"') == {"action": "type", "text": "biryani"}
    assert two_agent.resolve_direct_action("go back") == {"action": "press_back"}
    assert two_agent.resolve_direct_action("tap Orders") is None
    assert two_agent.resolve_open_app("open Swiggy app", [{"label": "Swiggy", "package": PKG}]) == PKG
    assert two_agent.label_from_instruction('tap the "Your Orders" button') == ("Your Orders", True)
    assert two_agent.label_from_instruction("tap Account") == ("Account", False)
    action, targets = two_agent.tap_by_label('tap "Account"', ORDERS["tree"], 1000, 2000)
    assert action["target"]["point"] == {"x": 0.125, "y": 0.95} and len(targets) == 1
    two = [node("Orders", 0, 200, 1000, 300), node("Orders", 0, 1000, 1000, 1100)]
    assert two_agent.tap_by_label('tap "Orders"', two, 1000, 2000)[0] is None                         # two: MAI-UI decides
    near, snapped = two_agent.snap_to_nearest({"action": "tap", "target": {"point": {"x": 0.5, "y": 0.57}}}, two, 1000, 2000)
    assert snapped and near["target"]["point"] == {"x": 0.5, "y": 0.525}
    steps = [{"action": {"action": "swipe", "direction": "up"}, "tree": ORDERS["tree"]}]
    assert two_agent.list_end_reached(steps, 0, ORDERS["tree"])                                        # the scroll changed nothing
    assert "end of the list was reached" in " ".join(two_agent.screen_facts(steps, 0, ORDERS["tree"]))
    memory = ["Order: Biryani Rs 349"]
    assert two_agent.add_to_memory(memory, ["biryani rs 349!", "Dosa Rs 120"]) == ["Dosa Rs 120"]


async def test_only_an_app_switched_on_can_be_read_and_a_run_can_be_stopped(family, monkeypatch):
    assert (await family.client.post("/v1/collect/phone/runs", headers=family.h("amma"), json={"package": "com.whatsapp"})).status_code == 409
    run = (await family.client.post("/v1/collect/phone/runs", headers=family.h("amma"), json={"package": PKG})).json()
    stopped = (await family.client.post(f"/v1/collect/phone/runs/{run['run_id']}/stop", headers=family.h("amma"))).json()
    assert stopped["status"] == "stopped"
    after = (await family.client.post(f"/v1/collect/phone/runs/{run['run_id']}/step", headers=family.h("amma"), json=ORDERS)).json()
    assert after["action"]["action"] == "done"
    assert (await family.client.post("/v1/collect/phone/runs", json={"package": PKG})).status_code == 401


async def test_a_step_sent_twice_after_a_dropped_link_waits_for_the_first(monkeypatch):
    import asyncio
    fake = local_models(monkeypatch, {"instruction": "scroll down"}, {"instruction": "scroll down"})
    inside, overlap = 0, []
    plain = fake.post

    async def slow(path, body):
        nonlocal inside
        inside += 1
        overlap.append(inside)
        await asyncio.sleep(0.05)
        inside -= 1
        return await plain(path, body)
    monkeypatch.setattr(two_agent, "_post", slow)
    run = phone_agent.start("amma@example.com", PKG, "local")
    a, b = await asyncio.gather(phone_agent.step("amma@example.com", run.id, ORDERS), phone_agent.step("amma@example.com", run.id, ORDERS))
    assert max(overlap) == 1                                          # never two model calls of one run at once
    assert [x["path"] for x in fake.asked].count("/plan") == 1        # planned once
    assert a["action"]["action"] == b["action"]["action"] == "swipe"


async def test_out_of_steps_what_claude_read_is_kept_not_lost(family, monkeypatch):
    monkeypatch.setattr(phone_agent, "MAX_STEPS", 2)
    sent = claude_says(monkeypatch,
                       reply(Use("tap", {"element": 2}, "a")),
                       reply(Use("done", {"items": [{"id": "408-1", "date": "8 Oct", "title": "Cabin trolley", "amount": "Rs 1,291",
                                                     "status": "Delivered"}], "note": "1 order before the steps ran out"}, "z")))
    run = (await family.client.post("/v1/collect/phone/runs", headers=family.h("amma"), json={"package": PKG})).json()
    step = f"/v1/collect/phone/runs/{run['run_id']}/step"
    await family.client.post(step, headers=family.h("amma"), json={**ORDERS, "currentApp": "com.android.launcher"})   # opens the app
    await family.client.post(step, headers=family.h("amma"), json=ORDERS)                                               # tap
    last = (await family.client.post(step, headers=family.h("amma"), json=ORDERS)).json()                               # out of steps
    assert last["status"] == "done" and last["kept"] == 1 and "before the steps ran out" in last["note"]
    assert "used all 2 steps" in str(sent[-1][-1])


async def test_out_of_steps_on_the_macs_models_the_memory_becomes_items(family, monkeypatch):
    monkeypatch.setattr(phone_agent, "MAX_STEPS", 1)
    local_models(monkeypatch, {"instruction": "scroll down", "remember": ["Cabin trolley · Rs 1,291 · Delivered 11 Oct"]},
                 items=[{"title": "Cabin trolley", "amount": "Rs 1,291", "status": "Delivered", "date": "11 Oct"}])
    run = (await family.client.post("/v1/collect/phone/runs", headers=family.h("amma"), json={"package": PKG, "engine": "local"})).json()
    step = f"/v1/collect/phone/runs/{run['run_id']}/step"
    await family.client.post(step, headers=family.h("amma"), json=ORDERS)
    last = (await family.client.post(step, headers=family.h("amma"), json=ORDERS)).json()
    assert last["status"] == "done" and last["kept"] == 1
