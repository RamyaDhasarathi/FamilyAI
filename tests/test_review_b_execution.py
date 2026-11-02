"""Review of 20 Oct 2026, execution and parsing: each test is a hole found by reading the code, written to fail before the fix."""
import asyncio
import datetime as dt
import uuid

import pytest

from familyos import clock, errands, familykey
from familyos.db import pool
from familyos.execution import disposable, generalist, phone, screens
from familyos.extraction import sandbox, service
from familyos.settings import settings
from tests.test_apps import ScriptedApp
from tests.test_errands import _p
from tests.test_generalist import HOSTS, FakeBase, _use
from tests.test_paylinks import _bill

# ---------------------------------------------------------------- the phone taps the app's own notices pages, nothing else

async def test_what_to_read_is_never_a_word_to_tap_unless_the_app_names_it_as_a_notices_page(family, database, monkeypatch):
    """A look is approved the moment it is asked, and its `what` can come from a model that read a stranger's notice. The phone taps only the
    app's own notices pages; "Pay fees" in the errand is not a button to press, even when the screen has one."""
    monkeypatch.setattr(screens, "SETTLE_STEP", 0)
    r = await family.client.post("/v1/errands", headers=family.h("amma"),
                                 json={"service": "myclassboard", "kind": "look", "title": "Read the school's notices", "spec": {"what": "Pay fees"}})
    errand_id = uuid.UUID(r.json()["id"])
    ref = []

    class FeesScreen(ScriptedApp):
        def __init__(self, driver_ref):
            super().__init__(driver_ref)
            self.screen = "Home · Attendance · Announcements · Pay fees · Fees due"

    scripted = FeesScreen(ref)
    driver = phone.attach(errand_id, scripted.send)
    ref.append(driver)
    await errands.run_on_phone(_p(family), errand_id, driver)
    tapped = [m["text"] for m in scripted.seen if m["op"] == "click_text"]
    assert tapped == ["Announcement"], tapped


# ---------------------------------------------------------------- a look presses nothing it was not shown to press

async def test_in_a_look_only_keys_that_move_around_are_pressed():
    """Space on a focused button presses it, and so does the numpad's Enter: neither is the word `enter` or `return`."""
    base = FakeBase()
    ts = generalist.SteelToolset(base, hosts=HOSTS)
    ts.guard.look = True
    await ts.tool_result(_use("navigate", {"url": "https://www.urbancompany.com/"}))
    for k in ("space", "NumpadEnter", "ctrl+Enter", "Return", "ctrl+v", "Backspace", "Delete", "ctrl+a"):
        await ts.tool_result(_use("key", {"text": k}))
    assert base.page.pressed == [] and ts.guard.stopped is None
    for k in ("PageDown", "Tab", "shift+Tab", "ArrowDown", "Escape", "End", "Home", "PageUp"):
        await ts.tool_result(_use("key", {"text": k}))
    assert len(base.page.pressed) == 8


async def test_space_on_a_focused_paying_button_is_refused_in_a_booking_too():
    base = FakeBase()
    ts = generalist.SteelToolset(base, hosts=HOSTS)
    await ts.tool_result(_use("navigate", {"url": "https://www.urbancompany.com/checkout"}))
    real = base.page.evaluate

    async def focused_on_pay(js, arg=None):
        return "Pay now ₹1,297" if "activeElement" in js else await real(js, arg)
    base.page.evaluate = focused_on_pay
    await ts.tool_result(_use("key", {"text": "space"}))
    assert base.page.pressed == [] and ts.guard.stopped == "needs_you"


@pytest.mark.parametrize("label", ["Purchase", "Enrol now", "Update profile", "Redeem offer", "Reschedule", "Withdraw", "Sign out", "Unsubscribe", "Top up"])
async def test_a_look_refuses_the_words_a_page_uses_for_a_change(label):
    base = FakeBase()
    ts = generalist.SteelToolset(base, hosts=HOSTS)
    ts.guard.look = True
    await ts.tool_result(_use("navigate", {"url": "https://www.urbancompany.com/"}))
    real = base.page.evaluate

    async def under_the_pointer(js, arg=None):
        return label if "elementFromPoint" in js else await real(js, arg)
    base.page.evaluate = under_the_pointer
    await ts.tool_result(_use("left_click", {"target": {"type": "coordinate", "x": 5, "y": 5}}))
    assert base.page.clicks == [], label


async def test_the_gate_reads_what_a_control_shows_as_well_as_what_it_is_called():
    """A page can name a button "Details" for a screen reader and print "Book now" on it: the gate sees both, in a real browser."""
    from playwright.async_api import async_playwright
    try:
        pw = await async_playwright().start()
        browser = await pw.chromium.launch()
    except Exception:  # noqa: BLE001
        pytest.skip("no Chromium on this machine")
    try:
        page = await browser.new_page()
        await page.set_content('<button id="b" style="position:fixed;left:10px;top:10px;width:200px;height:40px" aria-label="Details">Book now</button>')
        await page.focus("#b")
        assert "Book now" in await page.evaluate(generalist.ACTIVE_TEXT)
        assert "Book now" in await page.evaluate(generalist.AT_POINT, [50, 25])
        assert "Book now" in await page.locator("#b").evaluate(generalist.REF_WORDS)
        assert generalist.WRITES.search(await page.evaluate(generalist.AT_POINT, [50, 25]))
        await page.set_content('<a href="/x" aria-label="Open the menu">Menu</a>')
        assert await page.locator("a").evaluate(generalist.REF_WORDS) == "Open the menu | Menu"
    finally:
        await browser.close()
        await pw.stop()


# ---------------------------------------------------------------- a payee comes only from a sender the household would believe

async def _gmail_bill(family, database, sender, *, auth=True):
    today = clock.today()
    aid = uuid.UUID((await family.upload("amma", b"%PDF-1.4 mail", filename="m.txt", content_type="text/plain", visibility="shared")).json()["artifact"]["id"])
    await pool().execute("UPDATE input_artifacts SET channel = 'gmail', source = $2 WHERE id = $1", aid,
                         {"from": sender, "subject": "Bill", "sender_authenticated": auth, "date": today.strftime("%a, %d %b %Y 09:00:00 +0530")})
    upi = "upi://pay?pa=payee@bank&pn=Biller&am=1940.98&cu=INR"
    await service.save(uuid.UUID(family.household["id"]), aid, _bill(today), text=f"Your bill is due. Pay: {upi}")
    return await database.fetchval("SELECT pay_url FROM obligations WHERE artifact_id = $1 AND action = 'pay'", aid), upi


async def test_a_upi_payee_in_gmail_is_kept_only_from_a_sender_the_household_would_believe(family, database):
    kept, upi = await _gmail_bill(family, database, "Airtel <ebill@airtel.com>")
    assert kept == upi                                           # a biller the code lists
    got, _ = await _gmail_bill(family, database, "Electricity <pay@kseb-bill.example>")
    assert got is None                                           # any domain can pass DMARC for itself; that is not a biller
    await database.execute("INSERT INTO trusted_sender_domains (household_id, domain) VALUES ($1, 'kseb-bill.example')", uuid.UUID(family.household["id"]))
    got, upi = await _gmail_bill(family, database, "Electricity <pay@kseb-bill.example>")
    assert got == upi                                            # one the household has vouched for


# ---------------------------------------------------------------- an outside server is never a private address in disguise

@pytest.mark.parametrize("address", ["64:ff9b::7f00:1", "64:ff9b::a00:1", "64:ff9b::c0a8:1", "::ffff:10.0.0.1"])
async def test_an_outside_server_that_resolves_to_a_private_address_through_nat64_is_refused(monkeypatch, address):
    from familyos import mcp_client
    from familyos.identity import Invalid

    async def resolve(host):
        return [address]
    monkeypatch.setattr(disposable, "_resolve", resolve)
    with pytest.raises(Invalid):
        await mcp_client.check_url("https://tools.example.org/mcp")


# ---------------------------------------------------------------- the sandbox does not become a fork bomb

async def test_only_a_few_sandbox_children_run_at_once(monkeypatch):
    """A page of thumbnails is a page of requests, each a process of up to a gigabyte."""
    live = {"now": 0, "most": 0}

    class Child:
        returncode = 0

        async def communicate(self, data=None):
            live["now"] += 1
            live["most"] = max(live["most"], live["now"])
            await asyncio.sleep(0.02)
            live["now"] -= 1
            return b'{"codes": []}', b""

    async def spawn(*args, **kwargs):
        return Child()
    monkeypatch.setattr(sandbox.asyncio, "create_subprocess_exec", spawn)
    monkeypatch.setattr(settings, "parse_concurrency", 3)
    await asyncio.gather(*[sandbox.run_op("pdfqr", b"%PDF") for _ in range(15)])
    assert 1 <= live["most"] <= 3


# ---------------------------------------------------------------- an unlocked key does not outlive the switch that stored it

async def test_locking_a_household_clears_a_stored_key_even_with_the_switch_off(family, database, monkeypatch):
    from familyos import crypto
    household_id = uuid.UUID(family.household["id"])
    monkeypatch.setattr(settings, "multi_worker", True)
    await database.execute("INSERT INTO family_key_unlocks (household_id, wrapped_key, expires_at) VALUES ($1, $2, NOW() + INTERVAL '8 hours')",
                           household_id, crypto.wrap_key(household_id, b"k" * 32))
    monkeypatch.setattr(settings, "multi_worker", False)            # the operator turned it off, then the family locked the household
    await familykey._forget(household_id)
    assert await database.fetchval("SELECT count(*) FROM family_key_unlocks WHERE household_id = $1", household_id) == 0


# ---------------------------------------------------------------- the heartbeat belongs to a task that is running

async def test_a_task_that_fails_before_it_starts_does_not_leave_a_heartbeat_running(family, database, monkeypatch):
    from familyos import assistant_tasks
    from tests.test_assistant_tasks_workers import _task
    tid = await _task(database, family, "queued")
    real = assistant_tasks.pool

    class Flaky:
        def __init__(self, inner):
            self.inner = inner

        async def fetchrow(self, query, *args):
            if "FROM assistant_connections" in query:
                raise ConnectionError("the database went away")
            return await self.inner.fetchrow(query, *args)

        def __getattr__(self, name):
            return getattr(self.inner, name)
    monkeypatch.setattr(assistant_tasks, "pool", lambda: Flaky(real()))
    with pytest.raises(ConnectionError):
        await assistant_tasks.run(tid)
    beating = [t for t in asyncio.all_tasks() if "_beat" in repr(t.get_coro()) and not t.done()]
    for t in beating:
        t.cancel()
    assert beating == []


# ---------------------------------------------------------------- one ask is one task, but two children's slips are two

async def _phone_read(family, database, text_id, *, child=None):
    household_id = uuid.UUID(family.household["id"])
    aid = uuid.UUID((await family.upload("amma", f"slip {text_id}".encode(), filename=f"{text_id}.txt", content_type="text/plain", visibility="private")).json()["artifact"]["id"])
    await pool().execute("UPDATE input_artifacts SET channel = 'share', note = 'read from MyClassBoard school app by the phone' WHERE id = $1", aid)
    if child:
        await pool().execute("INSERT INTO artifact_subjects (artifact_id, member_id, inferred) VALUES ($1, $2, FALSE)", aid, uuid.UUID(family.__dict__[child]["id"]))
    return household_id, aid


async def _slip(title, today):
    from familyos.extraction.claims import Claim, Extraction, ExtractorInfo
    from tests.test_duplicates import GROUNDED
    return Extraction(
        extractor=ExtractorInfo(name="openai", model="openai/gpt-5.6-sol", prompt_version="p", parser_version="p1"),
        reference_date=today, actionable=True, page_count=1,
        claims=[Claim(kind="deadline", title=title, date=today + dt.timedelta(days=4), quote="return the signed slip", location=GROUNDED, confidence=0.9,
                      requires=["form_return"])])


async def test_the_same_ask_for_two_different_children_is_two_tasks_and_for_one_child_is_one(family, database):
    today = clock.today()
    h, first = await _phone_read(family, database, "a", child="older")
    await service.save(h, first, await _slip("Return the signed slip for the museum trip", today), text="slip a")
    h, second = await _phone_read(family, database, "b", child="younger")
    await service.save(h, second, await _slip("Return the signed slip for the museum trip", today), text="slip b")
    assert await database.fetchval("SELECT count(*) FROM obligations WHERE artifact_id = ANY($1::uuid[])", [first, second]) == 2
    h, again = await _phone_read(family, database, "c", child="older")
    await service.save(h, again, await _slip("Return the signed slip for the museum trip today", today), text="slip c")
    assert await database.fetchval("SELECT count(*) FROM obligations WHERE artifact_id = $1", again) == 0


# ---------------------------------------------------------------- the grade filter reads a class the way the family writes it

def test_a_section_written_without_a_dash_is_read_and_a_section_that_is_not_the_childs_is_another_class():
    from familyos.extraction import attribute
    assert not attribute.for_another_class("Class 4A", ["4-A"])         # "4A" is one token to a splitter on spaces and dashes
    assert not attribute.for_another_class("Grade 4A and 4B", ["4-B"])
    assert attribute.for_another_class("Class 4B", ["4-A"])             # the grade is the child's, the section is not
    assert attribute.for_another_class("Grade 4B students", ["4-A"])
    assert not attribute.for_another_class("Class 4", ["4-A"])          # no section named: every section is in it
    assert not attribute.for_another_class("Class IX-B", ["IX-B"])


def test_a_class_written_in_roman_and_a_circular_in_digits_are_the_same_class():
    from familyos.extraction import attribute
    assert not attribute.for_another_class("Grade 9", ["IX-B"])
    assert not attribute.for_another_class("Class IX", ["9-A"])
    assert attribute.for_another_class("Grade 3", ["IX-B"])
    assert attribute.for_another_class("Grade 10", ["IX-B"])
    assert not attribute.for_another_class("Grades IX and X", ["10-A"])
