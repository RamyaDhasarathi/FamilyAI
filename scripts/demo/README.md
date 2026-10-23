# The demo video

How `famos-demo-2026-10-10.mp4` was made, so it can be re-cut after a change.
Everything runs against the dev server on 127.0.0.1:8088 and the real
household; outputs land in `scripts/demo/out/` (ignored), or `$DEMO_OUT`.

1. `demo-link.py` issues a one-time sign-in link for Arunmozhi's member row
   (`OUT=<file>`; load `.env` in a subshell first).
2. `demo-web.py <notice id> <errand id>` records the console with Playwright
   (needs `playwright install chromium`): every page, Ask with a question,
   captions timed in `web-marks.json`. Reads `link-web.txt` from the out dir.
3. `demo-mobile.sh` builds `ios/Driver/DemoTests.swift`, records the FamilyOS
   simulator (`xcrun simctl io ... recordVideo`) while the test walks the app,
   Photos' share sheet and Shortcuts. Set `welcomed` on the simulator once
   (`xcrun simctl spawn <udid> defaults write com.arunmozhi.familyos welcomed -bool true`)
   and add a notice photo to its Photos (`simctl addmedia`). The test prints
   `DEMOMARK <clock> <caption>` lines; the script keeps the recorder's start
   time. A killed recorder leaves the simulator "already recording": shut it
   down and boot it again.
4. `demo-stitch.py [extra.mp4:caption ...]` assembles cards, the console, the
   phone and any extra clips (a phone screen recording) into `famos-demo.mp4`.

The architecture clip is `docs/architecture.html?autoplay=1` recorded the
same way (Playwright, `ARCHMARK` console lines for timings).
