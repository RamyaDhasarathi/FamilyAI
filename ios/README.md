# FamilyOS for iPhone

The native app: Today, Inbox, a notice with its dates, Ask, Settings, and a
share extension that sends a photo, a PDF, a page or a text to the household
from any app's share sheet. Plan and scope: `docs/native-app.md`.

## Build

    brew install xcodegen               # once
    xcodebuild -downloadPlatform iOS    # once, the simulator runtime
    ./build.sh                          # generates FamilyOS.xcodeproj, builds for the simulator

To put the build on a booted simulator and sign in from a script:

    xcrun simctl install booted build/Build/Products/Debug-iphonesimulator/FamilyOS.app
    xcrun simctl launch booted com.arunmozhi.familyos -signinLink <link> -server http://127.0.0.1:8000

Debug builds also take `-tab inbox|ask|settings` and `-notice <id>`.

Open `FamilyOS.xcodeproj` in Xcode to run it. On a phone, set your team under
Signing & Capabilities for both targets (or `DEVELOPMENT_TEAM` in
`project.yml`); the app group `group.com.arunmozhi.familyos` must be enabled for
both. Xcode needs the iOS platform installed (Settings → Components).

## Layout

- `Kit/` — models, the API client, the Keychain and app-group state. Compiled
  into both targets.
- `FamilyOS/` — the app: `FamilyOSApp.swift` (session), `Views/`.
- `ShareExtension/` — the share sheet entry.
- `project.yml` — the XcodeGen spec; the `.xcodeproj` is generated and ignored.

## First run

1. Sign in: the server's address (the Tailscale URL while the console runs on
   the Mac), your email, then paste the mailed link.
2. The app issues itself a device token ("iPhone app") for the share sheet; it
   shows on the console's Devices card.
3. Share a photo of a notice from Photos → FamilyOS → tag a child → Send.
