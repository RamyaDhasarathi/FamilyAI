# FamilyOS Mobile UI — Report

Branch `feat/mobile-familyos-ui` · built from `AGENT (1).md`, `design-reference/desing.mp4` and
`design-reference/UI_Design1/` · plan and decisions in [`MOBILE_UI_PLAN.md`](MOBILE_UI_PLAN.md).

## 1. What was built

The repo had no React Native app: the mobile client was a SwiftUI iPhone app (`ios/`), and the four web UIs are static
files served by FastAPI. The new UI is an **Expo SDK 58 / React Native 0.88 app in `mobile/`** that runs on Android and
iOS. Nothing outside `mobile/` and `design-reference/` was changed, apart from adding this report and the plan.

| Area | Where | Notes |
|---|---|---|
| Design system | `mobile/src/familyos/theme/` | Colour tokens, the four scenario moods (calm, insight, heads-up, urgent), Inter type scale, motion springs and durations |
| Crystal gem | `graphics/crystalGeometry.ts`, `crystalRender.ts` | Convex-hull polyhedron (Fibonacci points + seeded jitter), shaded per frame on the UI thread: `irid()` cosine palette, Lambert key/fill, Fresnel rim, Blinn sparkle. Facet edges are drawn by an SkSL shader inside the triangle batch |
| Ambient scene | `graphics/ambientShader.ts` | One GPU shader: scenario tint, corner glow, twinkling star field, uneven dust halo, satellite glow. Seamless 72 s loop, whole-number frequencies only |
| Satellites | `graphics/OrbitScene.tsx`, `orbitLayout.ts` | Five agent crystals at the video's positions with Lissajous drift, severity badges, walkthrough ring and dimming |
| Particle morph | `graphics/ParticleMorph.ts`, `iconPoints.ts` | 1,200 particles fly gem → icon → icon → gem with stagger, cubic easing and sideways curl. Icons are SVG paths sampled by fill and outline |
| Charts | `graphics/Charts.tsx` | Catmull-Rom sparkline with path-trim draw-in, week bars, progress bars, task ring, count-up stats |
| Home (Orbit) | `screens/HomeOrbitScreen.tsx` + parts | Header, summary line, avatar pill, status block, single-item card mode, Ask bar with listening state, summary button (Listen/Read) with progress ring, swipe-up Dashboard, toasts |
| Sheets | `screens/TodaySheet`, `NeedsYouSheet`, `ChatSheet`, `ProfileMenu`, `DashboardSheet` | Glass cards over the blurred, dimmed scene. Needs-you cards swipe right = Done, left = Later. Chat has a typing indicator and chips. The Dashboard is driven by the same value that shrinks the gem to the mini gem |
| Agent Deep Layer | `screens/AgentDetailScreen.tsx` | All five agents: hero (sparkline / week bars / progress / ring), stat tiles, expandable "What I did" timeline with Undo and "Ask about this", agent chat |
| Restyled existing screens | `LoadingScreen`, `LoginScreen`, `SettingsScreen`, `FamilyScreen`, `PlaceholderScreen` | Loading and Log in follow `design.md` §13. Family members use the avatar-stage GIFs chosen by age |
| Data | `mocks/`, `services/interfaces.ts`, `store/useFamilyOS.ts` | Every string and number in `mocks/data.ts`. Typed service contract. Zustand store |

The flows follow the video. Two differences from AGENT.md (the video wins, rule 3):

- **Satellite tap** plays that agent's walkthrough (video 0:26). **Long-press** opens its Deep Layer screen, with a
  circle expanding from the satellite.
- **Summary-button modes** are labelled **Listen / Read**, as in the video, and default to Listen.

## 2. Dependencies (installed in `mobile/` only)

| Package | Version | Package | Version |
|---|---|---|---|
| expo | 58.0.17 | react-native | 0.88.0 |
| react | 19.3.0 | react-native-reanimated | 4.7.1 |
| react-native-worklets | 0.13.0 | @shopify/react-native-skia | 2.14.0 |
| react-native-gesture-handler | 3.3.0 | react-native-safe-area-context | 5.10.1 |
| react-native-screens | 4.30.0 | react-native-svg | 15.16.0 |
| @react-navigation/native | 7.5.1 | @react-navigation/native-stack | 7.21.0 |
| expo-linear-gradient | 58.0.3 | expo-haptics | 58.0.7 |
| expo-speech | 58.0.3 | expo-image | 58.0.16 |
| expo-font | 58.0.9 | @expo-google-fonts/inter | 0.4.2 |
| expo-splash-screen | 58.0.11 | expo-status-bar | 58.0.4 |
| expo-system-ui | 58.0.6 | expo-navigation-bar | 58.0.4 |
| expo-screen-orientation | 58.0.3 | expo-dev-client | 58.0.14 |
| lucide-react-native | 1.61.0 | zustand | 5.0.16 |
| *dev:* typescript | 6.0.x | *dev:* eslint + eslint-config-expo | 9.39 / 58.0.x |

Not used, although AGENT.md suggested them: `@gorhom/bottom-sheet` (every sheet here is a floating card, and the
Dashboard has to share its drag value with the gem) and `expo-blur` (the Skia-blurred live scene gives the same frosted
look on both platforms). The Worklets Babel plugin is added automatically by `babel-preset-expo`; there is no
`babel.config.js`.

## 3. Running it

```sh
cd mobile
npm install
npx expo run:android            # dev build on a connected phone or emulator (needs JDK 17)
npx expo run:ios                # dev build on the iOS simulator (runs pod install)
npx expo start --dev-client     # Metro, for later sessions
npx expo run:android --variant release   # standalone APK with the JS bundled in
```

`android/` and `ios/` are generated by `expo prebuild` (Continuous Native Generation) and are git-ignored. Configure
native settings in `app.json` and `mobile/plugins/`, never in the generated folders.

**Native steps you still have to do**

1. **iPhone (physical device):** set your signing team in Xcode for `com.rortechnologies.familyos`. The simulator needs
   nothing.
2. **Store builds:** the release APK is signed with the debug keystore. Add a real keystore (or use EAS Build) before
   distributing. The local APK (`mobile/android/app/build/outputs/apk/release/app-release.apk`) is 175 MB because it
   carries all four CPU architectures; a Play Store AAB splits this per device.
3. **adb on macOS 27:** platform-tools **37.0.1 crashes** (libunwind) and drops the phone. Use platform-tools
   **35.0.2** with `ADB_LIBUSB=0`. This only affects the machine, not the app.
4. **Android "Force RTL layout"** is on in this phone's developer options. The app declares itself LTR-only
   (`plugins/withLtrOnly.js`), so it is unaffected.

## 4. Switching the demo scenario (dev builds only)

- **Long-press the date** on Home to cycle calm → insight → heads-up → urgent.
- **Settings → Developer → Demo scenario**: pick one directly.
- Deep link: `familyos://dev?scenario=urgent`. Other dev links (screens, sheets, walkthrough, frame-rate sampler) are
  listed in `src/familyos/navigation/devLinks.ts`.

Scenarios only choose which needs-you items are open. Home's mood always follows the most severe open item, so
resolving items changes the mood live. Resolving the last one returns Home to calm with a particle burst.

## 5. Replacing the mocks with the real backend

1. Implement `FamilyOSService` from `src/familyos/services/interfaces.ts` (for example in `services/apiService.ts`).
   The SwiftUI client `ios/Kit/API.swift` already knows the endpoints (`/v1/me`, `/v1/household`,
   `/v1/obligations`, `/v1/reminders`, …).
2. Change the single line at the bottom of `src/familyos/mocks/services.ts`
   (`export const service = mockService;`).
3. The screens and the store only talk to `FamilyOSService`, so nothing else changes. Currency (`$`), names and
   amounts live in `mocks/data.ts`; switch to `₹` or other names there.

## 6. Verification (AGENT.md §13)

| Check | Result |
|---|---|
| Web untouched | `design-reference/web-check.sh` re-run: **identical to `web-baseline.txt`** (ruff, `node --check` on all 7 web JS files, SHA-256 of all 374 files outside `mobile/` and `design-reference/`). The only other file in the diff is `MOBILE_UI_PLAN.md` (this report is new too). pytest was not part of the local baseline: it needs Postgres and tesseract |
| Type-check / lint | `npx tsc --noEmit` clean · `npx expo lint` clean · `npx expo-doctor` 20/20 |
| Android | Dev and **release** builds installed and run on a **Xiaomi 11 Lite NE** (Android 14, Snapdragon 778G, 1080×2400). The release build is on the phone now and runs without the Mac. It also caught a real bug the dev build hides: `x.png` and `x.gif` in one folder collide as Android resources, fixed by `avatars/still/` and `avatars/anim/` |
| iOS | Dev build runs on the **iPhone 18 Pro simulator** (Xcode 27.1) |
| Visual | 13 video-frame / device pairs in `design-reference/compare/` |
| Mock layer | No data strings in screens or components; all copy comes from `mocks/` |

**Frame rate on the Xiaomi** (UI thread, 300-frame samples, dev build):

| State | Average | p95 | Frames > 20 ms |
|---|---|---|---|
| Home calm / insight | 60 fps | 16.6 ms | 0 |
| Home urgent (tremble + fast pulse) | 60 fps | 16.6 ms | 2 |
| Low-power graphics | 60 fps | 16.6 ms | 0 |
| Summary walkthrough (particle morph) | 57 fps | 33 ms | 16 (during the 0.9 s particle flights) |

Getting there took profiling (`familyos://dev?perf=1`). The first version ran at 43 fps. The cost turned out not to
be the GPU or the maths but Skia stroking freshly built edge paths every frame, then JSI object conversion. The
renderer was reworked to draw edges with a shader inside the triangle batch, draw the far wall as one path, and cache
satellites and particle buckets as pictures re-recorded round-robin.

**Flows walked (§9)**

- **Android, by touch:** app open, tap gem, satellite tap (agent walkthrough) and long-press (agent screen), swipe-up
  Dashboard and drag back, summary line, summary button in Read and Listen (with stop), profile menu Listen/Read toggle with toast, Ask bar and mic → listening → chat,
  Needs-you swipe right and left, resolving the last item (→ calm + burst), timeline expand, Undo, "Ask about this",
  hardware back.
- **iOS, by dev links:** every sheet, the Dashboard, a walkthrough, all five agents, Settings, Family, Log in,
  Loading.
- **Not verified by touch on iOS:** gestures (swipes, edge swipe-back). The simulator could not be driven by touch
  here because the idb tap is untrusted on this machine. They use the same Gesture Handler code as Android.

## 7. Known gaps versus the video

- **The gem** is a shaded low-poly mesh, not the ray-marched refraction of `familyos_3d.py`. It reads very close
  (see `compare/01`), but interior refraction is approximated by a flowing colour field.
- **The walkthrough** drops a few frames while particles are in flight (57 fps). Settled icons hold 60.
- **No GIF fallback for the gem** (§7.1). The `stage7` render carries its own orbiting satellites, so overlaying it
  would duplicate the live ones. The low-power path (fewer facets, fewer particles, no satellite spin) holds 60 fps on
  the test phone instead, and is switched on automatically if the first 2 s average below ~42 fps.
- **Voice is simulated:** the mic shows a listening state and drops in a canned transcript, as specified. Spoken
  summaries use the device's TTS voice, which varies by phone.
- **Not built** (not in the video, and the existing app had no such flows, per §8.8): sign-up, one-time code and the
  family-pod wizard. A Health agent was not added either. Profile-menu rows without a destination open a placeholder.
- **The SwiftUI app** (`ios/`) is untouched and still uses its own bundle id. Its share extension, inbox and notice
  screens have no counterpart in the new app yet.

## 8. Stone design v2 (visual refresh, no behaviour change)

Branch `feat/stone-design-v2`. Only the drawing of the core gem, the five satellites and the mini gems changed. Taps,
gestures, flows and data are untouched. Side by side: `design-reference/compare/stones_video_v1_v2.png`.

| Stone | v2 changes |
|---|---|
| Core gem | Larger facets (52-point hull); hairline edges with a soft glow; light pooling at the lower right with the scenario palette swept across the gem (cyan → pink in calm); clear upper facets showing the far wall and its faint edges; inner glow; star glint; occasional corner sparkles |
| Satellites | Rough "uncut" shapes (per-stone proportions, stronger jitter); dark heart and bright rim; glowing agent-colour edges; faint inner edges; glitter; soft halo |

**Going back to the original design.** Both versions are kept:

- **One line:** in `mobile/src/familyos/graphics/stoneStyle.ts`, set `STONE_STYLE = 'v1' as StoneStyle`. v1's files
  (`crystalRender.ts`, `crystalGeometry.ts`) are byte-for-byte unchanged.
- **Whole app as approved:** `git checkout ui-v1-approved` (tag) or `git checkout feat/mobile-familyos-ui` (branch).

v2 lives in `crystalRenderV2.ts` and `stoneGeometryV2.ts`. Per-frame work on the simulator: v1 1.32 ms, v2 1.55 ms
(+17%; larger facets and shared point objects pay for most of the new detail). Low-power mode still applies.

Tested on the Xiaomi 11 Lite NE (dev build, 300-frame samples): Home at **60 fps in calm, insight, heads-up and
urgent** (p95 16.6 ms, no frames over 20 ms); summary walkthrough 58 fps (p95 16.6 ms, 12 slow frames during particle
flights; v1 had 16). Touch flows re-checked: satellite tap and long-press, swipe-up Dashboard, hardware back. On the
iOS simulator every screen with a stone was checked: four moods, walkthrough, sheets, Dashboard, agent screen and
Loading. Known dev-only quirk, the same with v1: after a full JavaScript reload on the iOS simulator the Skia canvas
stays black until the app is relaunched. A normal launch renders correctly.

## 9. Task 2 — interactive core and family members (`AGENT_CORE_AND_FAMILY.md`)

Branch `feat/core-gestures-and-family` (from `feat/stone-design-v2`). Commits: `Task 2 Phase 0`,
`feat(core): jelly tap and finger rotation for the crystal core`, `fix(core): tapping the crystal crashed the UI
thread`, then `feat(family): data model, storage and service`, `… family hub and member profile`, `… add/edit sheets
and details wizard`, `… remove flow with undo`. The last three are grouped by feature from one working session (the hub
hosts the sheets and the remove dialog), so only the branch head is the tested state.

### What was built

| Area | Where | Notes |
|---|---|---|
| Crystal orientation | `graphics/coreMotion.ts` | Quaternion orientation. Idle spin about the tilted axis, trackball drag (the facet under the finger follows it), flick momentum with friction, settle wobble, then a 1.2 s blend back into the idle spin |
| Jelly tap | `graphics/coreInput.ts`, `crystalRenderV2.ts` | Ray-sphere hit gives the tap point on the gem. A damped dent plus a travelling ripple (up to 3 at once), a volume-preserving squash along the tap, a facet flash, a halo pulse and a dust puff. Reduce Motion: a gentle 0.96 pulse only |
| Touch handling | `screens/CoreGestureLayer.tsx` | Gesture handlers only queue input; the frame callback applies it once per frame, so the crystal is drawn once however many touch events arrive. Satellites shift 2–3 px with the drag |
| Family data | `services/interfaces.ts`, `family/model.ts`, `mocks/familyService.ts`, `mocks/familySeed.ts`, `store/useFamily.ts` | `FamilyService` contract. Members in AsyncStorage (`familyos.family.v1`); ID, health and banking details in SecureStore as `member_<id>_<section>` (this device only, never logged). Soft delete, 6 s Undo, then purge |
| Region formats | `family/region.ts`, `family/fields.ts`, `family/summary.ts` | US and India fields, validators (ABA routing checksum, Aadhaar, PAN, IFSC, UPI, ZIP / PIN), as-you-type formatting, masking when a field isn't focused, masked one-line summaries |
| Family hub | `screens/family/FamilyHubScreen.tsx`, `FamilyOrbit.tsx`, `MemberCard.tsx` | Orbit header (a calm mini crystal, one dot per member in their stage colour, tap = jelly), completion summary, cards (owner first, then oldest) with amber tags per section to update, dim "not started", green "all up to date". Swipe left: Edit / Remove (Edit only for the owner). Long-press: menu |
| Member profile | `screens/family/MemberProfileScreen.tsx` | Stage avatar with stage-tinted dust and jelly tap, completion ring, one row per section with masked summary and status, ⋯ menu, "Remove from family" |
| Add / Edit sheet | `screens/family/MemberBasicsSheet.tsx`, `components/form/*` | Live avatar preview for the age entered (babies read "Under 1"), relationship chips, date of birth, photo (edit), discard confirmation. "Add and fill details" opens the wizard; "Add now, finish later" leaves every section not started |
| Details wizard | `screens/family/MemberWizardScreen.tsx`, `WizardFields.tsx`, `WizardReview.tsx` | Six tappable progress segments, slide between steps, section glow cross-fade, sensitive-data note, Skip / Save and continue, Review. Child / teen / adult variants (allowance and "Paid from" for under-18s). The footer and the focused field stay above the keyboard |
| Remove | `screens/family/RemoveDialog.tsx`, `Dissolve.tsx` | From the card swipe, the long-press menu, the profile ⋯ menu or link. Lists children whose allowance the member pays, with another adult or "Decide later". The card dissolves into particles and "Removed · Undo" shows at once |
| Entry points | `ProfileMenu.tsx`, `SettingsScreen.tsx`, `navigation/devLinks.ts` | Profile menu: "Add family member" and a needs-update count chip on "Family members". Settings (dev builds): Reset demo family |

### New libraries (all run in Expo Go)

| Package | Version | Used for |
|---|---|---|
| @react-native-async-storage/async-storage | 2.2.0 | The member list |
| expo-secure-store | 58.0.2 | ID, health and banking details |
| @react-native-community/datetimepicker | 9.2.1 | Dates (system dialog on Android, inline spinner on iOS) |
| expo-image-picker | 58.0.10 | Member photo (library or camera) |
| expo-document-picker | 58.0.4 | Document attachments in the IDs section |

### Gestures on the crystal

| Gesture | Result |
|---|---|
| Tap | Jelly ripple from the touch point (was: start the summary walkthrough) |
| Drag | Rotates the crystal under the finger, with a slight stretch along the drag |
| Flick | Keeps spinning and slows down, with a light haptic tick per turn (at most 6) |
| **Long-press** | **Starts the summary walkthrough** (moved here from tap) |
| Tap during a walkthrough | Stops it |
| Swipe up from below the crystal | Opens the Dashboard, as before. A drag that starts on the crystal never opens it |
| Screen reader | "Wobble" and "Play summary" actions on the crystal |

### Region, reset and backend

- **Region:** `REGION` in `mobile/src/familyos/mocks/data.ts` follows `CURRENCY`. `'$'` gives US fields and formats;
  set `CURRENCY = '₹'` for India (Aadhaar, PAN, IFSC, UPI, PIN code, +91, ₹ amounts).
- **Reset the demo family:** Settings → Reset demo family (under Demo scenario, dev builds only), or
  `familyos://dev?resetFamily=1`. It restores the five sample members and deletes everything saved on the device,
  including the SecureStore keys.
- **Backend:** implement `FamilyService` (`services/interfaces.ts`) and change the last line of
  `mocks/familyService.ts`. The store and screens only call the service. Suggested mapping: `listMembers` →
  `GET /v1/household/members`, `createMember` → `POST`, `updateBasics` → `PATCH /members/{id}`, `updateSection` →
  `PUT /members/{id}/sections/{section}`, `deleteMember` / `restoreMember` → soft delete and undelete, `purgeMember` →
  `DELETE`. Sensitive sections should then be stored server-side encrypted, and the SecureStore copy dropped.

### Verification

| Check | Result |
|---|---|
| Scope | `git diff feat/stone-design-v2..HEAD` outside `mobile/` touches only `MOBILE_UI_PLAN.md` (and this report) |
| Web untouched | `design-reference/web-check.sh` with ruff 0.17.2: **identical to `web-baseline.txt`** |
| Type-check / lint | `npx tsc --noEmit` clean · `npx eslint src/familyos` clean · `npx expo-doctor` 20/20 |
| Android, by touch (Xiaomi 11 Lite NE) | Crystal: tap, 10 rapid taps, drag, flick, long-press, tap to stop, swipe-up from below. Family: add with both buttons, validation and scroll-to-error, wizard steps and masking, Review, Edit with a stage change (toast), remove from all four entry points, the dependants dialog with reassign and "Decide later", Undo, owner can't be removed, Profile-menu chip, Reset demo family, data kept after an app restart |
| Edge cases (§5.4) | 55-character name (card truncates, profile wraps), member born today (Stage 1, "Under 1"), 16 → 18 years (stage unchanged; banking switches to the adult variant and is marked "Needs update"), removing the only adult paying an allowance, rotating the crystal while a sheet opens, 10 rapid taps |
| iOS simulator (iPhone 18 Pro) | By dev links: hub, profile, wizard steps and Review, Add sheet, Profile menu with chip. Touch could not be injected (no `idb` here); the gestures share the Android code |

**Frame rate, release build on the Xiaomi.** These count frames actually shown on screen: SurfaceFlinger present times
for the app window, over about 2 s each.

| Screen / action | Frames shown | Longest frame |
|---|---|---|
| Home idle · dragging the crystal · 10 rapid taps | 60 fps · 60 · 60 | 17 ms |
| Family hub idle · scrolling · fast flings | 60 fps · 60 · 60 | 17 ms |
| Member profile · wizard step slides | 60 fps · 60 | 17 ms |

**How to read the earlier frame-rate tables.** The tables in §6 and §8 come from the in-app sampler
(`familyos://dev?perf=1`). That sampler times the UI-thread frame callback. In the dev build it reads 58–60 fps, but
the dev build actually shows only about 28–39 frames a second, because of debug JavaScript and dev tooling.
Measure smoothness on a release build. On this phone the release build shows 60 fps on every screen above.

**Bugs found on the device and fixed:**
- Every tap on the Home crystal crashed the UI thread, because a worklet called another one that was declared later
  in the file.
- On Android, a card could stay invisible when the list reflowed during its entrance.
- Undo appeared only after the delete round-trip.
- Close marked an untouched "needs update" section as complete.
- Jumping between wizard steps dropped edits.
- The keyboard covered the wizard's footer and fields.
- Reanimated 4's spring default of mass 4 made the step slide and dialogs wobble.
- New members showed "All details up to date".
