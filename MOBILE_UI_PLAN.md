# FamilyOS Mobile UI — Plan

Working from `AGENT (1).md`, the reference video `design-reference/desing.mp4` and the design pack in
`design-reference/UI_Design1/`. Branch: `feat/mobile-familyos-ui`.

## 1. Repo shape (Phase 0 findings)

**Shape C — no React Native app existed.** `ai-family-os-main` contains:

| Part | What it is | Touched? |
|---|---|---|
| `familyos/` | Python FastAPI backend. Serves four static web UIs with no build step: `web/`, `web_classic/`, `web_guide/`, `web_orbit/` | **No** |
| `ios/` | Native **SwiftUI** iPhone app (Today, Inbox, Notice, Ask, Settings, Life, Memories, share extension) generated with XcodeGen | **No** |
| `tests/`, `docs/`, `scripts/`, `tools/`, `poc/`, `evalset/` | Backend tests and docs | **No** |

AGENT.md asks for a React Native UI that runs on **both Android and iOS**. The SwiftUI app is iOS-only and cannot run on
the Android test phone (Xiaomi 11 Lite NE, Android 14). So the new UI is a **new Expo React Native app in `mobile/`**,
beside everything else. Nothing existing is edited or deleted, so the SwiftUI app's API client (`ios/Kit/API.swift`),
models and session logic stay in place for the developer to port or keep (rule 4).

The folder was not a git repository. I ran `git init`, committed the code exactly as provided to `main` (`76a84f8`),
and work on `feat/mobile-familyos-ui`.

## 2. Isolation strategy

- Everything new lives in `mobile/` (the app) and `design-reference/` (video, design pack, frames, baseline).
- No shared config is edited. The repo root `.gitignore`, `pyproject.toml` and CI are untouched.
- `design-reference/.gitignore` keeps extracted frames out of git (scoped, instead of editing the root `.gitignore`).
- `design-reference/ruff.toml` excludes the copied reference renderer `familyos_3d.py`. Without it, copying the pack
  into the repo would have added 15 ruff findings to the backend's `ruff check .`, which CI runs.
- Web baseline: `design-reference/web-baseline.txt`, produced by `design-reference/web-check.sh` on a clean checkout
  of `main`: ruff (1 pre-existing finding), `node --check` on all 7 web JS files, and a SHA-256 manifest of all
  374 files outside `mobile/` and `design-reference/`. It is re-run at the end and must match exactly.
- The web UIs are not React Native Web, so there is no platform-split risk (shape B rules do not apply).

## 3. Toolchain set up on this machine

| Tool | Version | Note |
|---|---|---|
| Node | 26.10 | supported by Expo SDK 58 (`^26.0.0`) |
| ffmpeg | Homebrew | for frame extraction |
| JDK | OpenJDK 17 (Homebrew) | Android Studio's bundled JBR is 25; RN's Gradle wants 17 |
| Android SDK | platforms 35–37, build-tools 36/37, NDK 27/28 | already installed |
| adb | 37.0.1 → **35.0.2** | 37.0.1 crashes on macOS 27 (libunwind) and drops the phone; r35.0.2 with `ADB_LIBUSB=0` is stable |
| Xcode | 27.1 | iOS simulator: iPhone 18 Pro |

## 4. Dependencies (mobile/ only, SDK-matched via `npx expo install`)

| Purpose | Package | Version |
|---|---|---|
| Framework | expo / react-native / react | 58.0.17 / 0.88.0 / 19.3.0 |
| Animation | react-native-reanimated + react-native-worklets | 4.7.1 + 0.13.0 (worklets Babel plugin added automatically by babel-preset-expo) |
| Gestures | react-native-gesture-handler | 3.3.x (legacy `Gesture.*` builders still accepted by `GestureDetector`) |
| GPU graphics | @shopify/react-native-skia | 2.14.0 |
| Bottom sheet | ~~@gorhom/bottom-sheet~~ | removed — see §5 |
| Blur / gradients | ~~expo-blur~~ / expo-linear-gradient | blur removed — see §5; gradients 58.x |
| Vector / icons | react-native-svg / lucide-react-native | 15.16.0 / 1.61 |
| Haptics / speech | expo-haptics / expo-speech | 58.x |
| Fonts | @expo-google-fonts/inter + expo-font | Inter 400/500/600/700 |
| Images / GIFs | expo-image | 58.x |
| State | zustand | 5.0.x |
| Navigation | @react-navigation/native + native-stack | 7.x |
| Platform | expo-dev-client, expo-navigation-bar, expo-system-ui, expo-screen-orientation, expo-splash-screen, react-native-safe-area-context, react-native-screens | 58.x |

## 5. Rendering approach (decisions)

- **Crystal core:** a real low-poly polyhedron (Fibonacci-sphere points with radius jitter, convex hull, about
  130 faces). It is rotated, culled and shaded per frame in a worklet, with shading that follows
  `familyos_3d.py`: cosine-palette `irid()`, key and fill Lambert lights, Fresnel rim and Blinn sparkle.
  *Revised after profiling on the Xiaomi:* the front faces are **one `drawVertices` call** whose facet edges come
  from barycentric texture coordinates plus a tiny SkSL shader (no stroked paths, which cost ~10 ms a frame).
  The far wall of the glass is a single gradient-filled path.
- **Satellites and the particle morph** are cached `SkPicture`s, re-recorded a few per frame (round-robin).
- **Dust halo, star field, background glow:** one **SkSL runtime shader** with procedural, cell-hashed particles.
  Thousands of particles cost no per-frame JS. (`MakeVertices` converts every point and colour through JSI, which
  is fine for the gem's ~1.5k vertices but not for 900 dust quads.)
- **Particle morph:** about 1,200 CPU particles, drawn with `drawPoints` in a few alpha buckets. Icon targets are
  sampled once at start-up from SVG paths (`path.contains` plus `ContourMeasure`).
- **Sheets:** all custom Reanimated + Gesture Handler components, so `@gorhom/bottom-sheet` was removed. The modal
  cards (Today, Needs-you, Chat, Profile) are floating cards with a `Close` pill rather than edge-attached sheets,
  and the Dashboard is driven by the same shared value (`scene.dashT`) that shrinks the gem into the mini gem, so
  the finger, the sheet and the gem move as one.
- **Frosted glass:** the live Home scene is blurred by Skia under any open sheet, with translucent tinted fills
  and 1 px borders on top. This looks the same on iOS and Android, so `expo-blur` was removed.

## 6. Screen mapping

| Existing (SwiftUI, `ios/`) | Target in `mobile/` |
|---|---|
| `RootView` (tabs) | Replaced by the Home "Orbit" screen (no tab bar, §8.1) + `FamilyOSNavigator` stack |
| `TodayView` | Today sheet (§8.2) |
| `InboxView` | Needs-you sheet (§8.4) |
| `AskView` | Chat sheet "Ask FamilyOS" / "Ask {Agent}" (§8.6) |
| `SettingsView` | Settings screen, restyled (§8.8), with the dev-only "Demo scenario" row |
| `LifeView` (family) | Family members screen, restyled, with avatar stages by age (§8.5, §11.3) |
| `WelcomeView`, `SignInView` | Loading screen + Log in screen, restyled per `design.md` §13.2–13.3 (§8.8) |
| `NoticeView`, `AddNoticeView`, `ErrandView`, `MemoriesView`, `SearchView` | Not in the design. Left untouched in the SwiftUI app, not ported |
| — (new) | Dashboard sheet (§8.3), Profile menu (§8.5), Agent Deep Layer screens ×5 (§8.7), placeholder screens for profile-menu rows |

## 7. Video vs. AGENT.md notes

The video is the source of truth (AGENT.md rule 3):
- The summary-button chip in the profile menu reads **Listen / Read** in the video (AGENT.md says Read / Play). The
  video starts in **Listen** mode, with toasts "The summary button now opens the written summary" and "The summary
  button now plays the summary aloud". The labels and the default live in `mocks/data.ts`.
- The Today sheet in the video has a "TOMORROW MORNING" commute card ("Leave by 8:10") above the weather and first-event tiles.
- Tapping a satellite in the video (0:26.8) rings it and starts that agent's filtered walkthrough
  (`EDUCATION · 1 OF 4`). The gem breaks into shards and dust, and the dust reforms as the agent's icon. AGENT.md §7.3
  says a tap opens the Deep Layer screen, which the video never shows (agent screens are opened from the Dashboard).
  Following rule 3: **tap = agent walkthrough** (as in the video), **long-press = Deep Layer screen** (scale-up from the
  satellite, as AGENT.md §9 describes). Dashboard cards also open the Deep Layer screens.
- The Needs-you sheet sizes to its content. A swiped card shows a small "Done" / "Snoozed until tonight" pill.
- With one item left, Home shows that item as a floating card above the bottom bar.
- In urgent mode the Dashboard shows a "NEEDS YOU · N OPEN" section with swipeable cards under the agent grid.

## 8. Phase checklist

- [x] Phase 0 — recon, toolchain, frames, baseline, this plan
- [x] Phase 1 — dependencies + smoke test on the Xiaomi (Android) and iOS simulator
- [x] Phase 2 — design system (tokens, scenario themes, typography, motion, glass components)
- [x] Phase 3 — signature graphics (crystal, dust shader, satellites, particle morph, charts)
- [x] Phase 4 — screens and flows (Home → Ask/Summary → Today → Needs-you → Profile → Chat → Dashboard → Agents → restyled screens)
- [x] Phase 5 — verification (web untouched, builds, screenshots vs. video, flows, perf) + `MOBILE_UI_REPORT.md`

---

# Task 2 — Interactive core + family members (`AGENT_CORE_AND_FAMILY.md`)

Branch `feat/core-gestures-and-family`, created from `feat/stone-design-v2` (the current, refreshed stones).

## Findings (Phase 0)

- **Names differ from the file:** `GlassCard`/`GlassPill` → `Glass` + `PillButton`/`ClosePill`; the "bottom-sheet setup" →
  `ModalCard` (keyboard-aware glass sheet; `@gorhom/bottom-sheet` was never used); `ParticleField` → the dust in
  `ambientShader.ts`; `Crystal` → `drawStone()` (`stoneStyle.ts` → `crystalRenderV2.ts`); `SwipeCard`, `Toast`,
  `SectionLabel` exist as named.
- **Crystal rotation today:** angles `rotY`/`tiltX` computed per frame in `OrbitScene`; faces projected and shaded in
  the renderer worklet. Tap on the core currently starts the summary walkthrough (Pressable over the gem); the Home
  swipe-up is a `Gesture.Pan` on the whole overlay.
- **Family today:** a read-only `FamilyScreen` (5 members: Michael 42, Sarah 40, Ethan 16, Mia 11, Linda 68) using
  `avatarForAge()` and the stage GIF/PNG pairs in `assets/familyos/avatars/{anim,still}`. The Profile menu's "Family
  members" row opens it.
- **Libraries:** none of async-storage, secure-store, datetimepicker, image-picker or document-picker were installed;
  all five are now installed at SDK 58 versions (all run in Expo Go).
- **"Scrollbar" on Home (§2 polish):** Home has no scroll container. The bar at the top-right edge on the Xiaomi is
  MIUI's Security Center sidebar handle, a system overlay (`com.miui.securitycenter/.FloatingWindow`,
  frame x 992–1080, y 156–464). It also shows over the launcher. Nothing to change in the app.

## Decisions

- **Rotation:** orientation becomes a quaternion shared value; idle spin is a per-frame quaternion step about the tilted
  axis, flicks add an angular-velocity vector, and the renderer receives a 3×3 matrix. The jelly ripple, squash/stretch
  and rotation are drawn by the v2 renderer. With `STONE_STYLE = 'v1'` the core still squashes and rotates by the old
  angles but shows no ripple (v1's file stays unchanged).
- **Gestures:** a circular `GestureDetector` over the crystal with `Race(pan, Exclusive(longPress, tap))`; the crystal
  gesture `blocksExternalGesture(swipeUp)` so pans that start on the crystal never open the Dashboard.
- **Seed:** the existing seed already has 5 members with ages, so it is kept (Michael, Sarah, Ethan, Mia, Linda), with
  the mixed statuses from §4.3 (Sarah banking, Ethan IDs, Linda IDs + banking).
- **Region:** `region` in `mocks/data.ts`; `'US'` because the mock currency is `$`.
- **Profile menu chip:** the number of members with at least one section needing an update.
- **Storage:** the family service persists members to AsyncStorage and the ID, health and banking section data to
  SecureStore (`member_<id>_<section>`), so the store and screens only see the service.

## Files

- Touch: `graphics/{sceneState,OrbitScene,crystalRenderV2,ambientShader,MiniGem,orbitLayout}`, `screens/{HomeOrbitScreen,
  SatelliteLayer,ProfileMenu,SettingsScreen}`, `components/Toast`, `navigation/*`, `services/interfaces`, `mocks/data`,
  `graphics/avatars`, `store/useFamilyOS`.
- New: `graphics/coreMotion.ts`, `screens/CoreGestureLayer.tsx`, `family/` (model, validation, fields, wizard
  sections), `mocks/familyService.ts`, `mocks/familySeed.ts`, `store/useFamily.ts`, `screens/family/*` (hub, orbit
  header, member card, profile, add/edit sheet, wizard, remove dialog).

## Phases

- [x] Phase 0 — read the code, libraries, this section
- [ ] Part A — jelly tap and finger rotation (`feat(core): …`)
- [ ] Part B — data model, storage, service · hub + profile · add/edit + wizard · remove + undo
- [ ] Verification on the Xiaomi and the iOS simulator + report section
