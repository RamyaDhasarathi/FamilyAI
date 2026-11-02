"""Walk Orbit (/orbit/) the way the console demo walks /app/: sign in by link,
the home and its orbs, a notification orb and its modal, the dashboard, the
deep layers, the three escape routes, Ask with the same question, the spoken
day, and the senior, teen and child personas. Records a phone-width video
with marks, checks the console for errors, and writes a pass/fail list.
Usage: DEMO_OUT=<dir> python scripts/demo/demo-orbit.py  (reads link-orbit.txt from the out dir)."""
import json
import os
import sys
import time

from playwright.sync_api import sync_playwright

S = os.environ.get("DEMO_OUT") or os.path.join(os.path.dirname(os.path.abspath(__file__)), "out")
BASE = os.environ.get("ORBIT_BASE", "http://127.0.0.1:8088/orbit/")
link = open(os.path.join(S, "link-orbit.txt")).read().strip()
QUESTION = "What is due this week, and who is handling it?"
marks, checks, errors = [], [], []

def mark(page, t0, caption, hold=4.0):
    marks.append({"start": round(time.time() - t0, 2), "caption": caption}); page.wait_for_timeout(int(hold * 1000))

def check(name, ok, detail=""):
    checks.append({"check": name, "ok": bool(ok), "detail": detail}); print(("PASS " if ok else "FAIL ") + name + (": " + detail if detail else ""))

with sync_playwright() as p:
    b = p.chromium.launch(headless=True)
    ctx = b.new_context(viewport={"width": 390, "height": 844}, device_scale_factor=2, is_mobile=True, has_touch=True,
                        record_video_dir=os.path.join(S, "orbit-video"), record_video_size={"width": 390, "height": 844})
    page = ctx.new_page()
    page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
    page.on("pageerror", lambda e: errors.append(str(e)))
    t0 = time.time()
    page.goto(BASE + "?link=" + link, wait_until="networkidle"); page.wait_for_timeout(6000)
    check("signed in by link, home rendered", page.locator("#orbs .orb").count() == 5, f"{page.locator('#orbs .orb').count()} orbs")
    check("link taken out of the address bar", "link=" not in page.url)
    core = page.locator("#statusWord").inner_text() if page.locator("#statusWord").count() else ""
    mark(page, t0, "Home: the household at the centre, five spaces in orbit. " + core, 6)
    for ag in ["finance", "education", "household", "calendar", "grocery"]:
        label = page.locator(f'#orbs .orb[data-agent="{ag}"]').get_attribute("aria-label") or ""
        check(f"orb {ag} has a readable label", bool(label), label[:90])
    notes = page.locator("#orbs .note-orb").count()
    check("notification orbs in orbit", notes > 0, f"{notes}")
    if notes:
        page.locator("#orbs .note-orb").first.click(); page.wait_for_timeout(1200)
        has_modal = page.locator("#modalRoot .modal").count() > 0
        check("a notification opens its frosted modal with real actions", has_modal and page.locator("#modalRoot .btn").count() > 0,
              page.locator("#modalRoot .mm-title").first.inner_text()[:80] if has_modal else "no modal")
        mark(page, t0, "An orbital notification: tap it, read why, act or leave it", 5)
        page.keyboard.press("Escape"); page.wait_for_timeout(600)
        check("Escape closes the modal", page.locator("#modalRoot .modal").count() == 0)
    page.locator("#openDash").click(); page.wait_for_timeout(1500)
    check("the dashboard sheet opens", "sheet-open" in (page.locator("body").get_attribute("class") or ""))
    mark(page, t0, "Swipe up: the 90% frosted dashboard, the home still showing above", 6)
    sheet = page.locator("#sheet")
    sheet.evaluate("el => { const s = el.querySelector('.sheet-scroll') || el; s.scrollBy({top: 420, behavior: 'smooth'}) }"); page.wait_for_timeout(2500)
    sheet.evaluate("el => { const s = el.querySelector('.sheet-scroll') || el; s.scrollTo({top: 0, behavior: 'smooth'}) }"); page.wait_for_timeout(1500)
    page.locator('[data-open="finance"]').first.click(); page.wait_for_timeout(1500)
    check("tapping the Finance card pushes its deep layer", page.url.endswith("#/dashboard/finance"), page.url[-30:])
    hero = page.locator("#layers .hero, #layers h1, #layers .deep-hero").first
    mark(page, t0, "Deep layer: the hero figure, then the stream of what FamilyOS did and proposed", 7)
    page.locator("#bentoBtn").click(); page.wait_for_timeout(1200)
    check("escape 1: the grid icon snaps back to the dashboard root", page.url.endswith("#/dashboard"), page.url[-30:])
    mark(page, t0, "Escape one: the grid icon returns to the dashboard root", 3)
    page.locator('[data-open="education"]').first.click(); page.wait_for_timeout(1500)
    page.go_back(); page.wait_for_timeout(1200)
    check("escape 2: browser back goes up one layer", page.url.endswith("#/dashboard"), page.url[-30:])
    mark(page, t0, "Escape two: back goes up exactly one layer", 3)
    page.locator('[data-open="household"]').first.click(); page.wait_for_timeout(1500)
    page.locator("#sliver").click(); page.wait_for_timeout(1500)
    check("escape 3: tapping the sliver drops the whole sheet", "sheet-open" not in (page.locator("body").get_attribute("class") or ""))
    mark(page, t0, "Escape three: tap the home sliver and everything collapses", 4)
    page.locator("#fab").click(); page.wait_for_timeout(1200)
    check("the FAB opens the chat", page.locator("#chat").is_visible())
    page.locator("#chatInput").fill(QUESTION); page.keyboard.press("Enter")
    mark(page, t0, "Tap the FAB: Ask, over the family's own record", 2)
    answered = False
    for _ in range(40):
        page.wait_for_timeout(1000)
        if page.locator("#thread .bubble.them:not(.pending)").count(): answered = True; break
    check("Ask answers with citations", answered and page.locator("#thread .cite").count() > 0, f"answered={answered}, cites={page.locator('#thread .cite').count()}")
    mark(page, t0, "The answer, each fact pointing back to its notice", 8)
    page.locator("#chatListen").click(); page.wait_for_timeout(2500)
    check("hold to listen: the spoken day has a transcript", page.locator("#speech").is_visible() and len(page.locator("#speech").inner_text()) > 40)
    mark(page, t0, "Hold the FAB: the day read aloud, with a transcript", 7)
    page.keyboard.press("Escape"); page.wait_for_timeout(600)
    for persona, caption in [("senior", "Older adult: no orbit, one large card, one action, 24px type"),
                             ("teen", "Teen: schedule and events first, acid accents, fewer blocks"),
                             ("child", "Child: the adventure pod, big tactile blocks")]:
        page.goto(BASE + "?persona=" + persona, wait_until="networkidle"); page.wait_for_timeout(4500)
        check(f"persona {persona} renders", page.locator("#orbs .orb").count() == 5 or page.locator("#noteCard").is_visible())
        mark(page, t0, caption, 5)
        if persona != "senior":
            page.locator("#openDash").click(); page.wait_for_timeout(1800); mark(page, t0, caption.split(":")[0] + ": the dashboard at this density", 4)
    end = round(time.time() - t0, 2)
    ctx.close(); b.close()
check("no console errors during the walk", not errors, "; ".join(errors)[:300])
marks.append({"start": end, "caption": ""})
json.dump({"marks": marks, "checks": checks, "errors": errors}, open(os.path.join(S, "orbit-marks.json"), "w"), indent=1)
print(f"done {end}s; {sum(c['ok'] for c in checks)}/{len(checks)} checks passed")
sys.exit(0 if all(c["ok"] for c in checks) else 1)
