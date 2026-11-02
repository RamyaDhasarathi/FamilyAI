"""Record the console walkthrough with Playwright. Writes web.webm and web-marks.json (segment captions with start times)."""
import json
import os
import sys
import time

from playwright.sync_api import sync_playwright

S = os.environ.get("DEMO_OUT") or os.path.join(os.path.dirname(os.path.abspath(__file__)), "out")
link = open(os.path.join(S, "link-web.txt")).read().strip()
NOTICE = sys.argv[1]; ERRAND = sys.argv[2]
BASE = "http://127.0.0.1:8088/app/"
STOPS = [
    ("#/home", "Today: the brief, what needs a person now, what is late, the day itself", 9),
    ("#/today", "Waiting on you: the proposed dates and asks, accepted or dismissed in a tap", 8),
    ("#/notices", "Inbox: every notice the family shared, read by FamilyOS", 8),
    (f"#/notices/{NOTICE}", "A notice: its dates and asks, proposed, accepted by a parent", 10),
    ("#/money", "Money: bills, rhythms, pay links, what comes out this week", 8),
    ("#/family", "Family: the people, the week ahead, what is in whose hands", 8),
    ("#/life", "Life: school, money, home, travel, each a space of its own", 8),
    ("#/plans", "Plans: a trip or a project, its to-dos and bookings in one place", 7),
    ("#/errands", "Errands: runbooks on real sites, approved by a guardian, every step audited", 7),
    (f"#/errands/{ERRAND}", "An errand: the phone read the school app, every step pictured", 9),
    ("#/chat", "Ask: a question over the family's own record", 26),
    ("#/memories", "Memories: what the family kept", 6),
    ("#/household", "Household: members, rules, consent, Telegram, devices", 9),
    ("#/audit", "Audit: every read, write and run, by whom and when", 7),
]
marks = []
with sync_playwright() as p:
    b = p.chromium.launch(headless=True)
    ctx = b.new_context(viewport={"width": 1440, "height": 900}, record_video_dir=os.path.join(S, "web-video"),
                        record_video_size={"width": 1440, "height": 900}, device_scale_factor=1)
    page = ctx.new_page()
    t0 = time.time()
    page.goto(BASE + "?link=" + link, wait_until="networkidle")
    page.wait_for_timeout(4000)
    for route, caption, secs in STOPS:
        start = time.time() - t0
        page.evaluate(f"location.hash = {json.dumps(route)}")
        page.wait_for_timeout(2500)
        if route == "#/chat":
            box = page.locator("textarea, input[type=text]").last
            try:
                box.click(timeout=3000)
                box.type("What is due this week, and who is handling it?", delay=35)
                box.press("Enter")
            except Exception as e:
                print("ask box:", e)
            page.wait_for_timeout(max(1000, secs * 1000 - 4500))
        else:
            steps = max(1, (secs - 3) * 2)
            for _ in range(steps):
                page.mouse.wheel(0, 90); page.wait_for_timeout(500)
            page.mouse.wheel(0, -90 * steps); page.wait_for_timeout(500)
        marks.append({"start": round(start, 2), "caption": caption})
        print(f"{start:6.1f}s  {route}")
    end = time.time() - t0
    ctx.close(); b.close()
marks.append({"start": round(end, 2), "caption": ""})
json.dump(marks, open(os.path.join(S, "web-marks.json"), "w"), indent=1)
print("done", round(end, 1), "s")
