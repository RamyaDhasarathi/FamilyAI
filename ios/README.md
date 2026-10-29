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
    xcrun simctl launch booted <your bundle id> -signinLink <link> -server http://127.0.0.1:8000

Debug builds also take `-tab inbox|ask|settings` and `-notice <id>`.

**Your identity, once.** Copy `Local.xcconfig.example` to `Local.xcconfig` (gitignored) and set
`FAMILYOS_BUNDLE_PREFIX` (for example `com.yourname`) and `FAMILYOS_TEAM_ID` (your Apple team).
Every identifier derives from them: the bundle ids (`<prefix>.familyos`, `.share`, `.live`, `.driver`),
the app group `group.<prefix>.familyos`, the Keychain service and the background-task id. Without a
`Local.xcconfig` the build falls back to `com.example` and no team: fine for the simulator, not for a
phone. Pick the prefix once: changing it changes the app's identity, and a phone that already has the
app would be signed out. Regenerating the project (`xcodegen`) never wipes it.

Open `FamilyOS.xcodeproj` in Xcode to run it. On a phone, the app group `group.<prefix>.familyos`
must be enabled for both the app and the share extension. Xcode needs the iOS platform installed
(Settings → Components).

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
