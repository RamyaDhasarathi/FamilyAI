"""The generalist: Anthropic's browser toolset over the run's own browser.
The URL policy keeps it on the site, the gate refuses the tap that would
commit the household, and an errand runs through it to done or to the
person's hands. Driven here by a fake page and a fake model loop."""
import base64
import io
import uuid

import pytest
from anthropic.types.beta import BetaToolUseBlock

from familyos import errands
from familyos.execution import generalist, sessions, steel
from familyos.execution.sessions import SessionState
from familyos.identity import Principal
from familyos.settings import settings
from tests.test_sign_in_sitting import FakeBrowser

HOSTS = frozenset({"www.urbancompany.com", "urbancompany.com"})

TREE = ('link "AC Service & Repair" [ref_1]\n'
        'button "Add" [ref_2]\n'
        'textbox "Search for services" [ref_3]\n'
        'button "Pay now ₹1,297" [ref_4]\n'
        'heading "Select a service" [ref_5]')
WORDS = {"ref_1": "AC Service & Repair", "ref_2": "Add", "ref_3": "Search for services", "ref_4": "Pay now ₹1,297", "ref_5": "Select a service"}


def _png() -> bytes:
    from PIL import Image
    out = io.BytesIO()
    Image.new("RGB", (40, 30), (200, 180, 160)).save(out, format="PNG")
    return out.getvalue()


class FakeLocator:
    def __init__(self, page, ref): self.page, self.ref = page, ref
    @property
    def first(self): return self
    async def count(self): return 1 if self.ref in WORDS else 0
    async def scroll_into_view_if_needed(self): pass
    async def click(self, **kw): self.page.clicks.append((self.ref, kw.get("click_count", 1)))
    async def hover(self, **kw): self.page.hovered.append(self.ref)
    async def fill(self, value): self.page.filled.append((self.ref, value))
    async def set_checked(self, on): self.page.filled.append((self.ref, bool(on)))
    async def select_option(self, v): self.page.filled.append((self.ref, v))
    async def bounding_box(self): return {"x": 10, "y": 20, "width": 100, "height": 30}
    async def evaluate(self, js, arg=None):
        if "tagName" in js:
            return "text"
        return WORDS.get(self.ref, "")


class FakeMouse:
    def __init__(self, page): self.page = page
    async def click(self, x, y, **kw): self.page.clicks.append(((x, y), kw.get("click_count", 1)))
    async def move(self, x, y): pass
    async def wheel(self, dx, dy): self.page.wheels.append((dx, dy))


class FakeKeyboard:
    def __init__(self, page): self.page = page
    async def type(self, text): self.page.typed.append(text)
    async def press(self, chord): self.page.pressed.append(chord)


class FakePage:
    """A site as a script: a tree with references, words under them."""

    def __init__(self):
        self.url = "about:blank"
        self.clicks = []
        self.hovered = []
        self.filled = []
        self.typed = []
        self.pressed = []
        self.wheels = []
        self.mouse, self.keyboard = FakeMouse(self), FakeKeyboard(self)
        self.went = []
    async def title(self): return "UC"
    async def wait_for_timeout(self, ms): pass
    async def go_back(self, **kw): self.went.append("back")
    async def go_forward(self, **kw): self.went.append("forward")
    async def reload(self, **kw): self.went.append("reload")
    async def screenshot(self, **kw): return _png()
    def locator(self, sel): return FakeLocator(self, sel.split('"')[1])
    async def evaluate(self, js, arg=None):
        if "fosRef" in js:
            return TREE
        if "elementFromPoint" in js:
            return "Pay now ₹1,297" if arg == [300, 400] else "Add"
        if "activeElement" in js:
            return "Search for services"
        return "AC Service & Repair Earliest Thu Select a service Add Pay now ₹1,297"


class FakeBase:
    """What the toolset needs of the runbooks' driver."""

    def __init__(self):
        self.page = FakePage()
        self.closed = False
        self.visited = []

    async def _open(self):
        return self.page

    async def goto(self, url):
        self.visited.append(url)
        self.page.url = url

    async def screenshot(self):
        return b"\xff\xd8jpeg"

    async def close(self):
        self.closed = True


def _use(name, input, id="t1"):
    return BetaToolUseBlock(id=id, name=name, input=input, type="tool_use", toolset_name="browser")


def _said(result) -> str:
    content = result.get("content")
    if isinstance(content, str):
        return content
    return " ".join(b.get("text", "") for b in content if isinstance(b, dict) and b.get("type") == "text")


def test_the_url_policy_keeps_the_run_on_the_site_and_off_anything_private():
    policy = generalist.url_policy_for(HOSTS)
    policy(None, "https://www.urbancompany.com/bengaluru-ac-service-repair")
    policy(None, "https://m.urbancompany.com/x")            # a subdomain of the site is the site
    policy(None, "back")
    for bad in ("https://evil.example.com/x", "javascript:alert(1)", "file:///etc/passwd", "http://127.0.0.1:8088/v1/me",
                "http://169.254.169.254/latest/meta-data", "https://localhost/x", "https://urbancompany.com.evil.example/x"):
        with pytest.raises(Exception) as caught:
            policy(None, bad)
        assert "URLRefused" in type(caught.value).__name__, bad
    assert generalist.host_allowed("www.urbancompany.com", HOSTS) and not generalist.host_allowed("10.0.0.4", HOSTS)


async def test_the_toolset_reads_with_references_and_acts_on_them():
    base = FakeBase()
    ts = generalist.SteelToolset(base, hosts=HOSTS)
    r = await ts.tool_result(_use("navigate", {"url": "https://www.urbancompany.com/"}))
    assert not r.get("is_error") and base.visited == ["https://www.urbancompany.com/"]
    r = await ts.tool_result(_use("navigate", {"url": "https://evil.example.com/"}))
    assert r.get("is_error") and "evil.example.com" in _said(r) and base.visited == ["https://www.urbancompany.com/"]
    r = await ts.tool_result(_use("read_page", {"filter": "interactive"}))
    assert "[ref_2]" in _said(r) and 'button "Add"' in _said(r)
    r = await ts.tool_result(_use("find", {"query": "the Add button for the service"}))
    assert _said(r).splitlines()[0].startswith('button "Add"')
    r = await ts.tool_result(_use("left_click", {"target": {"type": "ref", "ref": "ref_2"}}))
    assert not r.get("is_error") and base.page.clicks == [("ref_2", 1)]
    r = await ts.tool_result(_use("left_click", {"target": {"type": "ref", "ref": "ref_99"}}))
    assert r.get("is_error") and "read the page again" in _said(r)
    r = await ts.tool_result(_use("form_input", {"target": {"type": "ref", "ref": "ref_3"}, "value": "AC service"}))
    assert base.page.filled == [("ref_3", "AC service")]
    await ts.tool_result(_use("key", {"text": "ctrl+a Enter"}))
    assert base.page.pressed == ["Control+a", "Enter"]
    await ts.tool_result(_use("scroll", {"target": {"type": "coordinate", "x": 640, "y": 400}, "scroll_direction": "down", "scroll_amount": 5}))
    assert base.page.wheels == [(0, 500)]
    r = await ts.tool_result(_use("screenshot", {}))
    img = next(b for b in r["content"] if isinstance(b, dict) and b.get("type") == "image")
    assert base64.b64decode(img["source"]["data"])[:4] == b"\x89PNG"
    r = await ts.tool_result(_use("zoom", {"region": [0, 0, 20, 15]}))
    assert any(isinstance(b, dict) and b.get("type") == "image" for b in r["content"])
    r = await ts.tool_result(_use("get_page_text", {}))
    assert "Select a service" in _said(r)
    # The browser state rides along: one tab, on the site.
    state = next((b for b in r["content"] if isinstance(b, dict) and b.get("type") == "browser_state"), None)
    assert state and state["tabs"][0]["url"] == "https://www.urbancompany.com/"


async def test_the_gate_refuses_the_tap_that_would_commit_the_household_and_the_members_never_enabled():
    base = FakeBase()
    ts = generalist.SteelToolset(base, hosts=HOSTS)
    await ts.tool_result(_use("navigate", {"url": "https://www.urbancompany.com/checkout"}))
    r = await ts.tool_result(_use("left_click", {"target": {"type": "ref", "ref": "ref_4"}}))          # "Pay now ₹1,297"
    assert r.get("is_error") or "refus" in _said(r).lower() or ts.guard.stopped
    assert base.page.clicks == [] and ts.guard.stopped == "needs_you" and "Pay now" in ts.guard.why
    # By coordinate too: the words under the pointer are read before the click.
    ts2 = generalist.SteelToolset(FakeBase(), hosts=HOSTS)
    await ts2.tool_result(_use("left_click", {"target": {"type": "coordinate", "x": 300, "y": 400}}))
    assert ts2.guard.stopped == "needs_you"
    # A click on Add is fine; so is Enter in a search box.
    ts3 = generalist.SteelToolset(FakeBase(), hosts=HOSTS)
    await ts3.tool_result(_use("left_click", {"target": {"type": "ref", "ref": "ref_2"}}))
    await ts3.tool_result(_use("key", {"text": "Enter"}))
    assert ts3.guard.stopped is None
    # Scripts, uploads and extra tabs: refused before anything runs.
    r = await ts3.tool_result(_use("javascript_exec", {"expression": "1+1"}))
    assert r.get("is_error") or "refus" in _said(r).lower() or "disabled" in _said(r).lower()
    assert ts3.guard.stopped is None


def test_the_generalist_is_named_in_configuration_not_inferred(monkeypatch):
    monkeypatch.setattr(settings, "anthropic_api_key", "k")
    monkeypatch.setattr(settings, "errand_generalist", "off")
    monkeypatch.setattr(settings, "errand_model", "claude-x")
    assert not generalist.available()
    monkeypatch.setattr(settings, "errand_generalist", "fallback")
    assert generalist.available() and generalist.wants("look", has_runbook=False) and not generalist.wants("look", has_runbook=True)
    monkeypatch.setattr(settings, "errand_generalist", "looks")
    assert generalist.wants("look", has_runbook=True) and not generalist.wants("booking", has_runbook=True)
    monkeypatch.setattr(settings, "errand_model", "")
    monkeypatch.setattr(settings, "chat_model", "openai/gpt-x")
    assert not generalist.available()                      # the chat model is not Anthropic's: nothing is inferred
    monkeypatch.setattr(settings, "chat_model", "anthropic/claude-y")
    assert generalist.model_name() == "claude-y"
    monkeypatch.setattr(settings, "anthropic_api_key", "")
    assert not generalist.available()


# ----------------------------------------------------------------------------
# an errand, end to end, with a fake model loop
# ----------------------------------------------------------------------------

def _p(family, who="amma"):
    m = getattr(family, who)
    return Principal(member_id=uuid.UUID(m["id"]), household_id=uuid.UUID(family.household["id"]), role=m["role"], display_name=m["display_name"])


class _Text:
    def __init__(self, text): self.type, self.text = "text", text


class _Message:
    def __init__(self, *texts): self.content = [_Text(t) for t in texts]


class FakeRunner:
    """A model's turns as a script: each turn acts on the toolset the way the
    SDK would, then says something."""

    def __init__(self, toolset, script):
        self.toolset, self.script = toolset, script

    def __aiter__(self):
        return self._go()

    async def _go(self):
        for actions, said in self.script:
            for name, input in actions:
                await self.toolset.tool_result(_use(name, input, id=f"t{uuid.uuid4().hex[:6]}"))
            yield _Message(said)


@pytest.fixture
def browser():
    fake = FakeBrowser()
    steel.use_browser(fake)
    yield fake
    steel.use_browser(steel.NoBrowser())


@pytest.fixture
def generalist_on(monkeypatch):
    monkeypatch.setattr(settings, "anthropic_api_key", "k")
    monkeypatch.setattr(settings, "errand_generalist", "looks")
    monkeypatch.setattr(settings, "errand_model", "claude-test")
    bases = {"base": FakeBase(), "runs": []}
    generalist.use_page_factory(lambda ws, storage=None: bases["base"])
    yield bases
    generalist.use_page_factory(None)
    generalist.use_runner_factory(None)


async def _ready(family, *, kind="look", what="AC deep cleaning"):
    await sessions.store(_p(family), service="urbancompany", allow_hosts=sorted(HOSTS),
                         state=SessionState(cookies=[{"name": "_uc_user_token", "value": "x", "domain": ".urbancompany.com"}],
                                            fingerprint={"user_agent": "Mozilla/5.0 Chrome/154"}))
    r = await family.client.post("/v1/errands", headers=family.h("amma"), json={
        "service": "urbancompany", "kind": kind, "title": what,
        "spec": {"what": what, "when": {"date": "2031-10-09", "time": "15:30"}, "max_amount": 3000, "currency": "INR"}})
    assert r.status_code == 201, r.text
    return r.json()


async def test_a_look_runs_through_the_generalist_to_done_with_what_it_found(family, database, browser, generalist_on):
    script = [([("navigate", {"url": "https://www.urbancompany.com/"}), ("read_page", {"filter": "interactive"}),
                ("left_click", {"target": {"type": "ref", "ref": "ref_1"}})], "Opening the AC page."),
              ([("get_page_text", {})], "Slots on the page: 10:00 AM, 12:30 PM, 03:30 PM. Anti-rust deep clean is ₹1,198.")]
    generalist.use_runner_factory(lambda model, ts, system, task: FakeRunner(ts, script))
    e = await _ready(family)
    assert e["status"] == "approved"
    job = await database.fetchrow("SELECT * FROM jobs WHERE kind = $1", errands.KIND)
    out = await errands._handle(dict(job), None)
    assert out["status"] == "done", out
    got = (await family.client.get(f"/v1/errands/{e['id']}", headers=family.h("amma"))).json()
    assert got["status"] == "done" and got["outcome"]["answer"].startswith("Slots on the page") and got["outcome"]["turns"] == 2
    said = [s["said"] for s in got["outcome"]["steps"]]
    assert said[0].startswith("Started on") and any(s.startswith("navigate") for s in said) and any(s.startswith("left click ref_1") for s in said)
    base = generalist_on["base"]
    assert base.visited == ["https://www.urbancompany.com/"] and base.page.clicks == [("ref_1", 1)] and base.closed
    assert browser.released == ["steel-2"]                           # a look gives the browser back
    shots = await database.fetch("SELECT visibility FROM input_artifacts WHERE channel = 'errand'")
    assert len(shots) == 2 and all(s["visibility"] == "private" for s in shots)   # the navigate and the click, pictured


async def test_a_booking_through_the_generalist_stops_at_the_paying_tap_and_hands_over(family, database, browser, generalist_on, monkeypatch):
    monkeypatch.setattr(settings, "errand_generalist", "fallback")
    monkeypatch.setattr(errands, "_runbooks", {})                   # no runbook for the site: the generalist takes it
    script = [([("navigate", {"url": "https://www.urbancompany.com/checkout"}),
                ("left_click", {"target": {"type": "ref", "ref": "ref_4"}})], "Trying to pay."),
              ([], "It would not let me pay; over to you.")]
    generalist.use_runner_factory(lambda model, ts, system, task: FakeRunner(ts, script))
    e = await _ready(family, kind="booking")
    r = await family.client.post(f"/v1/errands/{e['id']}/approve", headers=family.h("amma"), json={"params_sha256": e["params_sha256"]})
    assert r.status_code == 200
    job = await database.fetchrow("SELECT * FROM jobs WHERE kind = $1", errands.KIND)
    out = await errands._handle(dict(job), None)
    assert out["status"] == "needs_you", out
    got = (await family.client.get(f"/v1/errands/{e['id']}", headers=family.h("amma"))).json()
    assert got["status"] == "needs_you" and "Pay now" in got["outcome"]["why"] and got["outcome"]["turns"] == 1
    assert got["outcome"]["browser"]["ws_url"] == "ws://localhost:3000/"
    base = generalist_on["base"]
    assert base.page.clicks == [] and not base.closed and browser.released == []   # the browser stays, for the person


async def test_without_a_model_a_look_waits_rather_than_runs(family, database, browser, monkeypatch):
    monkeypatch.setattr(settings, "anthropic_api_key", "")
    monkeypatch.setattr(errands, "_runbooks", {})
    e = await _ready(family)
    assert e["status"] == "approved"
    assert await database.fetchval("SELECT count(*) FROM jobs WHERE kind = $1", errands.KIND) == 0
