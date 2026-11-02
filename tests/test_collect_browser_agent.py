"""The browser agent (familyos/collect/browser_agent.py, decided 30 Oct 2026): the founder's generalist over Chromium on this
Mac, signing in to a Connected services site and reading the member's own orders into the local cache. The model never has
the password: it puts a placeholder, only into a password field, and neither the page it reads nor the gate's reading
carries a password's value; a click that would show the password, buy, or save is refused. Driven here by a real Chromium
on a stand-in site and a scripted model."""
import uuid

import pytest
from anthropic.types.beta import BetaToolUseBlock

from familyos.collect import browser_agent, store, vault
from familyos.settings import settings

SECRET = "hunter2-correct-horse"
SITE = "https://shop.test/"
PAGE = """<html><body>
<h1>Sign in</h1>
<input id=u name=u placeholder="Email or phone">
<input id=p type=password placeholder="Password">
<button id=show aria-label="Show password">o</button>
<button id=go type=button onclick="document.body.innerHTML = '<h1>Your Orders</h1><p>Order 402-1 placed 12 Oct 2026 Rs 1,299 Delivered</p><button>Buy it again</button>'">Sign in</button>
<input id=q placeholder="Search orders">
<button id=buy>Buy it again</button>
</body></html>"""


class ShopBrowser(browser_agent.LocalBrowser):
    """A real Chromium, on a stand-in site instead of the internet, without a kept profile."""

    async def _open(self):
        if self._page is None:
            from playwright.async_api import async_playwright
            self._pw = await async_playwright().start()
            try:
                self._browser = await self._pw.chromium.launch()
            except Exception:  # noqa: BLE001
                await self._pw.stop()
                pytest.skip("chromium is not installed")
            self._ctx = await self._browser.new_context()
            await self._ctx.route("https://shop.test/**", lambda r: r.fulfill(body=PAGE, content_type="text/html"))
            self._page = await self._ctx.new_page()
        return self._page

    async def close(self):
        if self._pw is not None:
            await self._browser.close()
        await super().close()


def _use(name, input):
    return BetaToolUseBlock(id=f"t{uuid.uuid4().hex[:6]}", name=name, input=input, type="tool_use", toolset_name="browser")


def _said(result) -> str:
    content = result.get("content")
    return content if isinstance(content, str) else " ".join(b.get("text", "") for b in content if isinstance(b, dict))


async def _ref(ts, words):
    tree = await ts.read_page(None, type("I", (), {"filter": "interactive", "ref": None, "depth": 0})())
    line = next(x for x in tree.splitlines() if words in x)
    return line.split("[")[1].split("]")[0], tree


@pytest.fixture
async def toolset(tmp_path):
    ts = browser_agent.CollectToolset(ShopBrowser(tmp_path / "p", headless=True), hosts=frozenset({"shop.test"}), password=SECRET)
    await ts.base.goto(SITE)
    yield ts
    await ts.close()


async def test_the_password_goes_only_into_a_password_field_and_the_model_never_reads_it(toolset):
    ts = toolset
    user, _ = await _ref(ts, '"Email or phone"')
    pw, _ = await _ref(ts, '"Password"')
    search, _ = await _ref(ts, "Search orders")
    # Into the search box: refused, and the box stays empty.
    r = await ts.tool_result(_use("form_input", {"target": {"type": "ref", "ref": search}, "value": "{{password}}"}))
    assert r.get("is_error") and "password field" in _said(r)
    assert await ts.base._page.input_value("#q") == ""
    # Typed with the focus outside a password field: refused.
    await ts.base._page.focus("#q")
    r = await ts.tool_result(_use("type", {"text": "{{password}}"}))
    assert r.get("is_error") and await ts.base._page.input_value("#q") == ""
    # The proper way.
    await ts.tool_result(_use("form_input", {"target": {"type": "ref", "ref": user}, "value": "amma@example.com"}))
    r = await ts.tool_result(_use("form_input", {"target": {"type": "ref", "ref": pw}, "value": "{{password}}"}))
    assert not r.get("is_error"), _said(r)
    assert await ts.base._page.input_value("#p") == SECRET
    # What the model can read: the username, never the password.
    tree = (await _ref(ts, '"Email or phone"'))[1]
    assert 'value="amma@example.com"' in tree and SECRET not in tree
    found = await ts.find(None, type("I", (), {"query": "password hunter2"})())
    assert SECRET not in found
    # What the gate reads of the field (and could keep in its refused list): not the password either.
    assert SECRET not in await ts.words_of("left_click", type("I", (), {"target": type("T", (), {"type": "ref", "ref": pw})()})())
    assert all(SECRET not in step for step in ts.log)


async def test_the_gate_refuses_showing_the_password_buying_and_enter_but_lets_it_sign_in(toolset):
    ts = toolset
    show, _ = await _ref(ts, "Show password")
    buy, _ = await _ref(ts, "Buy it again")
    go, _ = await _ref(ts, '"Sign in"')
    for name, inp in (("left_click", {"target": {"type": "ref", "ref": show}}),
                      ("left_click", {"target": {"type": "ref", "ref": buy}}),
                      ("key", {"text": "Enter"})):
        await ts.tool_result(_use(name, inp))
    assert len(ts.guard.refused) == 3, ts.guard.refused
    await ts.tool_result(_use("left_click", {"target": {"type": "ref", "ref": go}}))
    assert "Your Orders" in await ts.base._page.inner_text("body")


def test_only_plain_checked_items_are_kept_from_the_answer():
    rows, note = browser_agent.items_from('Here: {"items": [{"id": "402-1", "date": "12 Oct 2026", "title": "<b>Kettle</b>", '
                                          '"amount": "Rs 1,299", "status": "Delivered"}, {"title": ""}, "nonsense", '
                                          '{"date": "1 Oct", "title": "Rice 5kg", "amount": "Rs 450"}], "note": "2 orders"}')
    assert [(r["id"], r["title"]) for r in rows][0] == ("402-1", "bKettle/b")
    assert rows[1]["id"].startswith("fos-") and rows[1]["happened"] == "1 Oct" and len(rows) == 2 and note == "2 orders"
    assert browser_agent.items_from("no json at all") == ([], "")


# ── A run, through the routes ───────────────────────────────────────────────────────────────────────────────

class _Text:
    def __init__(self, text):
        self.type, self.text = "text", text


class _Message:
    def __init__(self, text):
        self.content = [_Text(text)]
        self.usage = type("U", (), {"input_tokens": 10_000, "output_tokens": 500})()


class FakeRunner:
    def __init__(self, toolset, script):
        self.toolset, self.script = toolset, script

    def __aiter__(self):
        return self._go()

    async def _go(self):
        for actions, said in self.script:
            for name, input in actions:
                if callable(input):
                    input = await input(self.toolset)
                await self.toolset.tool_result(_use(name, input))
            yield _Message(said)


@pytest.fixture
def agent(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "collect_dir", str(tmp_path / "collect"))
    monkeypatch.setattr(settings, "anthropic_api_key", "sk-test")
    held = {}
    monkeypatch.setattr(vault, "_keychain_set", lambda s, a, p: held.__setitem__((s, a), p))
    monkeypatch.setattr(vault, "_keychain_get", lambda s, a: held.get((s, a)))
    monkeypatch.setattr(vault, "_keychain_delete", lambda s, a: held.pop((s, a), None))
    monkeypatch.setattr(browser_agent, "_browser_factory", ShopBrowser)
    monkeypatch.setattr(browser_agent, "_running", {})

    def script(*turns):
        monkeypatch.setattr(browser_agent, "_runner_factory", lambda model, ts, system, task: FakeRunner(ts, turns))
    return script


async def _field(ts, name):
    return {"target": {"type": "ref", "ref": (await _ref(ts, f'"{name}"'))[0]}}


async def test_a_run_signs_in_reads_the_orders_and_keeps_them_for_that_member_only(family, agent):
    await family.client.post("/v1/collect/services", headers=family.h("amma"),
                             json={"service": "other", "host": "shop.test", "username": "amma@example.com", "password": SECRET})

    async def user(ts):
        return {**await _field(ts, "Email or phone"), "value": "amma@example.com"}

    async def password(ts):
        return {**await _field(ts, "Password"), "value": "{{password}}"}

    async def sign_in(ts):
        return {"target": {"type": "ref", "ref": (await _ref(ts, '"Sign in"'))[0]}}
    agent(([("form_input", user), ("form_input", password), ("left_click", sign_in)], "Signed in."),
          ([("get_page_text", {})], '{"items": [{"id": "402-1", "date": "12 Oct 2026", "title": "Kettle", "amount": "Rs 1,299", '
                                    '"status": "Delivered"}], "note": "1 order"}'))
    result = await browser_agent.run("amma@example.com", "other")
    assert result["outcome"] == "done" and result["kept"] == 1 and result["turns"] == 2
    assert result["cost_usd"] == pytest.approx(20_000 / 1e6 * 2 + 1_000 / 1e6 * 10)
    assert SECRET not in str(result)
    got = (await family.client.get("/v1/collect/services/other/items", headers=family.h("amma"))).json()
    assert [(i["id"], i["title"], i["amount"]) for i in got] == [("402-1", "Kettle", "Rs 1,299")]
    assert (await family.client.get("/v1/collect/services/other/items", headers=family.h("appa"))).status_code == 404
    listed = (await family.client.get("/v1/collect/services", headers=family.h("amma"))).json()["connected"]
    assert listed[0]["items"] == 1 and listed[0]["last_run"]["counts"]["kept"] == 1
    assert SECRET.encode() not in (store.path()).read_bytes()


async def test_a_one_time_code_stops_the_run_for_the_member_to_sign_in(family, agent):
    await family.client.post("/v1/collect/services", headers=family.h("amma"),
                             json={"service": "other", "host": "shop.test", "username": "amma", "password": SECRET})
    agent(([], "NEEDS_SIGN_IN: it sent a one-time code to the phone"))
    result = await browser_agent.run("amma@example.com", "other")
    assert result["outcome"] == "needs_sign_in" and "one-time code" in result["note"]


async def test_the_routes_say_what_is_missing(family, agent, monkeypatch):
    r = await family.client.post("/v1/collect/services/amazon/run", headers=family.h("amma"))
    assert r.status_code == 404
    monkeypatch.setattr(settings, "anthropic_api_key", "")
    await family.client.post("/v1/collect/services", headers=family.h("amma"), json={"service": "amazon", "username": "a", "password": SECRET})
    assert (await family.client.post("/v1/collect/services/amazon/run", headers=family.h("amma"))).status_code == 503
    assert (await family.client.post("/v1/collect/services/amazon/run")).status_code == 401


def test_an_api_refusal_is_said_in_its_own_words():
    class Refused(Exception):
        body = {"type": "error", "error": {"type": "invalid_request_error", "message": "You have reached your specified API usage limits."}}
    assert browser_agent.said(Refused("Error code: 400 - {...}")) == "You have reached your specified API usage limits."
    assert browser_agent.said(RuntimeError("the page did not load")) == "the page did not load"


# ── A one-time code, filled from what was collected (decided 2 Nov 2026) ──────────────────────────────────────

OTP_PAGE = """<html><body>
<input id=m placeholder="Mobile number">
<button id=get type=button onclick="document.getElementById('c').style.display='block'">Get OTP</button>
<input id=c placeholder="Enter OTP" style="display:none">
<button id=v type=button onclick="if (document.getElementById('c').value === '482913') document.body.innerHTML = '<h1>Your Orders</h1><button>Pay now</button>'">Verify</button>
</body></html>"""


class OtpShop(ShopBrowser):
    async def _open(self):
        page = await super()._open()
        await self._ctx.unroute("https://shop.test/**")
        await self._ctx.route("https://shop.test/**", lambda r: r.fulfill(body=OTP_PAGE, content_type="text/html"))
        return page


async def test_a_code_that_arrived_by_sms_is_filled_without_the_model_seeing_it(monkeypatch, tmp_path):
    import datetime as dt

    from familyos.collect import categorize, device
    monkeypatch.setattr(settings, "collect_dir", str(tmp_path / "collect"))
    monkeypatch.setattr(categorize, "start", lambda email: False)
    started = dt.datetime.now(dt.UTC)
    ts = browser_agent.CollectToolset(OtpShop(tmp_path / "p", headless=True), hosts=frozenset({"shop.test"}), password=SECRET,
                                      email="amma@example.com", since=started)
    try:
        await ts.base.goto(SITE)
        verify, _ = await _ref(ts, '"Verify"')
        # Verify before any code was filled: the look gate refuses it ("verify" is a write).
        await ts.tool_result(_use("left_click", {"target": {"type": "ref", "ref": verify}}))
        assert ts.guard.refused and "Verify" in ts.guard.refused[-1]
        # The site's own "Get OTP" is let through (it sends a code to the member).
        await ts.tool_result(_use("left_click", {"target": {"type": "ref", "ref": (await _ref(ts, '"Get OTP"'))[0]}}))
        # The SMS arrives on the phone and live SMS sends it.
        device.keep("sms", "amma@example.com", [{"id": "99", "sender": "AX-SHOPTS", "body": "482913 is your OTP for Shop",
                                                 "date": int(dt.datetime.now(dt.UTC).timestamp() * 1000)}])
        code_box, _ = await _ref(ts, '"Enter OTP"')
        r = await ts.tool_result(_use("form_input", {"target": {"type": "ref", "ref": code_box}, "value": "{{otp}}"}))
        assert not r.get("is_error"), _said(r)
        assert await ts.base._page.input_value("#c") == "482913"
        tree = (await _ref(ts, '"Enter OTP"'))[1]
        assert "482913" not in tree and "482913" not in await ts.words_of(
            "left_click", type("I", (), {"target": type("T", (), {"type": "ref", "ref": code_box})()})())
        await ts.tool_result(_use("left_click", {"target": {"type": "ref", "ref": verify}}))
        assert "Your Orders" in await ts.base._page.inner_text("body")
        # Signed in: paying is still refused.
        await ts.tool_result(_use("left_click", {"target": {"type": "ref", "ref": (await _ref(ts, '"Pay now"'))[0]}}))
        assert "Pay now" in " ".join(ts.guard.refused) or ts.guard.stopped
        assert "482913" not in " ".join(ts.log)
    finally:
        await ts.close()


async def test_an_old_code_is_never_used_and_none_arriving_says_so(monkeypatch, tmp_path):
    import datetime as dt

    from familyos.collect import categorize, device
    monkeypatch.setattr(settings, "collect_dir", str(tmp_path / "collect"))
    monkeypatch.setattr(categorize, "start", lambda email: False)
    monkeypatch.setattr(browser_agent, "OTP_WAIT_S", 4)
    monkeypatch.setattr(browser_agent.asyncio, "sleep", _instant)
    device.keep("sms", "amma@example.com", [{"id": "1", "sender": "X", "body": "111222 is your OTP", "date": 1700000000000}])
    ts = browser_agent.CollectToolset(None, hosts=frozenset({"shop.test"}), password=SECRET, email="amma@example.com",
                                      since=dt.datetime.now(dt.UTC))
    with pytest.raises(Exception, match="no code arrived"):
        await ts._code()


async def _instant(_):
    return None
