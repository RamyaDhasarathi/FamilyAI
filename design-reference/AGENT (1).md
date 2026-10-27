# AGENT.md — FamilyOS Mobile UI Rebuild (React Native · iOS + Android)

You are working inside a project that contains BOTH a web application and a React Native mobile application. Your job is to **rebuild the UI of the mobile application only** so that it matches the FamilyOS design shown in the reference video (`desing.mp4`) and the design pack (`UI_Design1.zip`), with rich, graphical, 60 fps animation. All data is dummy for now: the real backend and business logic will be added later by the developer, so build a clean mock layer that is easy to swap out.

Work autonomously. Install and configure every dependency yourself. Only stop and ask in the situations listed in §14.

---

## 1. Non-negotiable rules

1. **Do not change the web application in any way.** No edits to web source, web configs, web routes, web styles, web tests or web build scripts. If a file is shared between web and mobile, do not change its behaviour on web (see §5 for how to isolate).
2. **The finished UI must run on both Android and iOS** (simulator/emulator at minimum). Never ship a feature that works on one platform only without a graceful fallback on the other.
3. **The video is the source of truth** for layout, screens, flows, copy, colours and motion. The zip is the source for design tokens, avatar-stage assets, extra specs and anything the video does not show. If they conflict, the video wins (§2.3).
4. **Never delete existing mobile business logic, API clients, stores or hooks.** You are replacing the presentation layer. Leave existing non-UI code in place (unused is fine) so the developer can rewire it later.
5. **All data goes through the mock service layer** (§10). No hard-coded strings or numbers inside screen components except UI labels.
6. Work on a new git branch: `feat/mobile-familyos-ui`. Commit at the end of every phase with a clear message.
7. Read the current install docs of each library before configuring it. Do not rely on memory for versions, Babel plugins or native setup steps; they change between releases.

---

## 2. Reference material

### 2.1 Where to find it
Look for these in the project (search the whole repo if they are not where expected):
- `desing.mp4` (note the spelling) — 5 min 27 s screen recording of the target UI, 224×464, portrait phone.
- `UI_Design1.zip` — contains:
  - `design.md` — full written spec (colours, motion system, avatar stages, home-screen tension curve, Deep Layer layout, onboarding flows §13, sample family pod).
  - `familyos_prototype_template.html` — HTML/CSS/JS prototype; mine it for CSS variables, spacing, radii, blur values and copy.
  - `familyos_3d.py` — the renderer that produced the GIFs; mine it for crystal geometry, lighting and colour maths.
  - `stage1…stage8_*.gif/.png` — the 8 avatar life-stage renders (320×320).
  - `home_screen_*.png/.gif`, `avatar_evolution_grid.*` — reference renders.
  - `familyos_prototype.html` (8 MB) — built prototype. Reference only. Never bundle it.

Move both into `design-reference/` at the repo root if they are not already in a dedicated folder, and add `design-reference/frames/` and `design-reference/scenes/` to `.gitignore`.

### 2.2 Watching the video (you cannot play it — extract frames)
Install `ffmpeg` if it is missing (`brew install ffmpeg` on macOS, `winget install ffmpeg` or `choco install ffmpeg` on Windows, `apt-get install ffmpeg` on Linux). Then:

```bash
mkdir -p design-reference/frames design-reference/scenes
# one frame every 2 s for an overview
ffmpeg -i design-reference/desing.mp4 -vf "fps=1/2,scale=448:-1" design-reference/frames/f_%03d.png
# one frame per scene change, to catch every distinct screen and state
ffmpeg -i design-reference/desing.mp4 -vf "select='gt(scene,0.18)',scale=448:-1" -vsync vfr design-reference/scenes/s_%03d.png
# short clip at 10 fps to study one animation frame by frame (example: 0:40–0:46)
ffmpeg -ss 00:00:40 -t 6 -i design-reference/desing.mp4 -vf "fps=10,scale=448:-1" design-reference/frames/anim_%03d.png
```

Open and study the frames (you can view images). Before building each screen in §8, re-open the matching frames and compare. The written spec in §6–§10 was transcribed from the video and is your primary guide; the frames are for visual checking.

Unzip the design pack into `design-reference/UI_Design1/` and read `design.md` fully before Phase 2.

### 2.3 Video vs zip conflicts (already resolved — follow these)
| Topic | Video (use this) | Zip (older) |
|---|---|---|
| User / family | Michael; children Ethan and Mia; "Family plan · 5 agents" | Mahesh, Rao family pod |
| Currency in copy | `$` | `₹` |
| Agent satellites | Small faceted crystals in agent colours, floating freely around the core (no visible orbit lines) | Glass orbs on tilted orbit lines |
| Home bottom area | "Ask FamilyOS" glass input with mic, plus a separate circular summary button | Single central FAB, "Tap to chat • Hold to listen" |
| Core during summary | Core dissolves into particles that reform into the agent's icon | Not present |

Keep currency and names in the mock data file only, so the developer can switch to `₹` or other names later in one place.

---

## 3. Phase 0 — Reconnaissance (before writing any UI code)

1. Map the repo. Determine which of these shapes it is:
   - **A. Separate apps** (e.g. `apps/web` + `apps/mobile`, `web/` + `mobile/`, or a Next/Vite app beside an RN app). → Only ever touch the mobile package.
   - **B. One codebase with React Native Web** (the same components render on web through `react-native-web`, often Expo with the `web` platform). → Isolation through platform-specific files is mandatory (§5.2).
   - **C. Something else.** Describe it in the plan and choose the safest isolation.
2. Detect: package manager (lockfile), monorepo tooling (workspaces / turbo / nx), Expo vs bare RN (`expo` in the mobile `package.json`? `app.json` / `app.config.*`? `ios/` and `android/` checked in?), Expo SDK and RN version, New Architecture on or off, TypeScript or JS, navigation library and version, state library, existing theme and fonts.
3. List every existing mobile screen and route and map each one to a target screen in §8, or mark it "keep, restyle with the new design language" or "not in design, leave untouched".
4. **Record the web baseline:** run the web build (and web tests and lint, if present) and save a summary to `design-reference/web-baseline.txt`, including the exact commands. You will re-run them at the end (§13). Also record `git status` so you know which files were already modified.
5. Write `MOBILE_UI_PLAN.md` at the repo root: repo shape, isolation strategy, dependency list with versions, the screen-mapping table, and the phase checklist. Then continue; do not wait for approval unless §14 applies.

---

## 4. Phase 1 — Dependencies (install and configure them yourself)

Install into the **mobile package only** (in a monorepo, run the install from the mobile workspace or with the workspace filter, never into the web package). Use `npx expo install <pkg>` in Expo projects so versions match the SDK; otherwise use the repo's package manager.

| Purpose | Library | Notes |
|---|---|---|
| Animation engine | `react-native-reanimated` (+ `react-native-worklets` if the installed Reanimated major requires it) | Pick the major that fits the RN version and architecture. Its Babel plugin goes **last** in the plugin list. |
| Gestures | `react-native-gesture-handler` | Wrap the app root in `GestureHandlerRootView`. |
| GPU graphics (crystal, particles, glows, charts) | `@shopify/react-native-skia` | The core visual engine. In shape B, import it only from `.native.*` files. |
| Bottom sheets | `@gorhom/bottom-sheet` | Confirm the version supports your Reanimated major. |
| Frosted glass | Expo: `expo-blur`. Bare: `@react-native-community/blur` | On Android, check that the blur looks right and stays smooth; otherwise fall back to Skia `BackdropBlur` or a translucent tinted surface. |
| Gradients | Expo: `expo-linear-gradient`. Bare: `react-native-linear-gradient` | Inside Skia canvases use Skia gradients. |
| Vector / icons | `react-native-svg` + `lucide-react-native` | Agent icons for the particle morph are custom paths (§7.4). |
| Safe areas | `react-native-safe-area-context` | Usually present already. |
| Haptics | Expo: `expo-haptics`. Bare: `react-native-haptic-feedback` | Light impact on taps; success notification on "Done". |
| Spoken summary | Expo: `expo-speech`. Bare: `react-native-tts` | Used by the summary button's "Play" mode. |
| Fonts | Inter 400/500/600/700. Expo: `@expo-google-fonts/inter` + `expo-font`. Bare: add the TTFs and link with `npx react-native-asset`. | Inter is the spec font. |
| Images / GIFs | Expo: `expo-image`. Bare: `react-native-fast-image`, or `<Image>` with Fresco animated-GIF support enabled on Android | For the avatar-stage GIFs from the zip. |
| Mock app state | `zustand` | Scenario, needs-you list, chat threads, settings. |
| Navigation | Keep the existing library. If there is none, `@react-navigation/native` + `@react-navigation/native-stack`. | Add a mobile-only navigator. |

After installing:
- Bare iOS: `cd ios && pod install` (macOS only). If you are not on macOS, say in the final report that the developer must run it.
- Expo with native folders or a dev client: rebuild the native app (`npx expo run:ios` / `npx expo run:android`, or `npx expo prebuild` if the project uses Continuous Native Generation). Clear the bundler cache once (`npx expo start -c` or `npx react-native start --reset-cache`).
- **Smoke test** before building screens: one Skia canvas with a Reanimated-driven animated circle, inside a bottom sheet, with a blur view behind it, on both platforms. Fix every setup problem now.

---

## 5. Architecture and web isolation

### 5.1 Folder layout (inside the mobile app's source root)
```
src/familyos/
  theme/        tokens.ts, stateThemes.ts, typography.ts, motion.ts
  graphics/     Crystal.tsx, crystalGeometry.ts, ParticleField.tsx, ParticleMorph.tsx, iconPoints.ts,
                AmbientBackground.tsx, Satellite.tsx, GlowDot.tsx, Sparkline.tsx, WeekBars.tsx
  components/   GlassCard, GlassPill, PillButton, StatusLine, AskBar, SummaryButton, Toast,
                SectionLabel, StatTile, TimelineItem, ChatBubble, SuggestionChips, SwipeCard, Badge
  screens/      HomeOrbitScreen, DashboardSheet, TodaySheet, NeedsYouSheet, ProfileMenu,
                ChatSheet, AgentDetailScreen, plus restyled existing screens
  navigation/   FamilyOSNavigator.tsx
  mocks/        data.ts (all copy and numbers), scenarios.ts, services.ts, chatReplies.ts
  store/        useFamilyOS.ts (zustand)
  services/     interfaces.ts (typed contracts the real backend will implement later)
assets/familyos/ avatars/stage1…8 (png + gif), fonts/ (if bare)
```

### 5.2 Isolation strategy
- **Shape A:** everything above lives only in the mobile app. Done.
- **Shape B (React Native Web):** every new file that imports Skia, Reanimated worklets, bottom-sheet, blur, haptics or speech is a `*.native.tsx` file. Where a web-visible file must route to the new UI, add a platform split: `Screen.native.tsx` holds the new UI and the existing `Screen.tsx` stays byte-for-byte unchanged, so web keeps resolving it. Never let the web bundle import a native-only package. Use `Platform.OS` guards only as a last resort.
- Do not edit shared config (root Babel / Metro / webpack / tsconfig) in a way that changes web output. If a plugin must go into a shared config, scope it to native and prove web is unchanged with the baseline (§13).
- Only copy the assets you use from the zip into the app (the 8 stage PNGs and GIFs). Do not bundle `familyos_prototype.html`, the evolution grid or the home-screen GIFs.

### 5.3 Service contracts
Define TypeScript interfaces in `services/interfaces.ts`, for example `getHomeSummary()`, `getTodayItems()`, `getNeedsYou()`, `resolveItem(id, actionId)`, `snoozeItem(id)`, `getAgentDetail(agentId)`, `undoAction(actionId)`, `sendChat(threadId, text)`, `getProfile()`, `getFamily()`, `setSummaryMode(mode)`. `mocks/services.ts` implements them with the dummy data and a simulated latency of 250–600 ms. Screens use them only through hooks. Put a short comment at the top of `services.ts` explaining how to swap in the real backend.

---

## 6. Design system (Phase 2: build this before any screen)

### 6.1 Colour tokens
```ts
// theme/tokens.ts
export const colors = {
  bg: '#000000',                 // OLED black, always (the app is dark-only)
  ink: '#E8EAF0',                // primary text
  inkStrong: '#FFFFFF',          // greeting, hero numbers
  muted: '#8E93A3',              // secondary text, dates, meta
  dim: '#5D6272',                // tertiary, section labels
  glassFill: 'rgba(255,255,255,0.06)',
  glassFillStrong: 'rgba(255,255,255,0.10)',
  glassBorder: 'rgba(255,255,255,0.12)',
  scrim: 'rgba(0,0,0,0.55)',
  pillPrimaryBg: '#FFFFFF', pillPrimaryInk: '#0B0C10',   // "Move call to 3:30", mic button, send button
  pillSecondaryBg: 'rgba(255,255,255,0.08)',             // "Later", "Close", "Ask about this"
  danger: '#FF5A5F',             // "Log out"
  agents: {
    finance:   '#1FC7B8',  // deep teal
    education: '#BD9EFF',  // soft lavender
    household: '#FF9E33',  // warm amber
    grocery:   '#6BF294',  // mint green
    calendar:  '#61B8FF',  // sky blue
    health:    '#FF6B9A',  // only if a Health screen exists
  },
  dust: '#BFD1FF',
};
```

### 6.2 Scenario states (they drive the whole home screen)
The home screen has four moods. One value, `scenario`, controls the core's palette, the background tint, the status dot and label, the headline, the satellite badges and the sheet tint. Animate every change over 600–800 ms (colours interpolate, never snap).

| Scenario | Label (status) | Status dot | Core palette (facet gradient) | Background radial tint | Summary line under greeting |
|---|---|---|---|---|---|
| `calm` | `● CALM` | `#4DFF8C` | teal → emerald → violet iridescence (see video 0:00) | teal/green, very faint | `Today's summary · all clear ›` |
| `insight` | `● INSIGHT` | `#A98BFF` | lavender → violet → indigo | violet | `Today's summary · 1 needs you ›` |
| `headsup` | `● HEADS-UP` | `#FFB23F` | gold → amber → warm white | amber | `Today's summary · 7 need you ›` |
| `urgent` | `● URGENT` | `#FF4D5E` | crimson → rose → pink highlights | deep red | `Today's summary · 3 urgent ›` |

The count in the summary line comes from mock data. Ship a **dev-only scenario switcher** (`__DEV__` only): long-press the date text on Home to cycle `calm → insight → headsup → urgent`. Also expose it as a "Demo scenario" row inside Settings, shown only in dev builds.

### 6.3 Typography (Inter)
| Role | Size / weight | Notes |
|---|---|---|
| Greeting "Good evening, Michael" | 26 / 500, letter-spacing −0.4 | White. Greeting changes with time of day (morning / afternoon / evening). |
| Date "Tuesday, October 20" | 12 / 500 | Muted. Use the real current date. |
| Summary line | 12 / 500, the state word in 600 white | Coloured dot 6 px before it. |
| Satellite labels | 11 / 500 | `#C8CDD7`, centred under each crystal. |
| Status label `● CALM` | 10 / 600, letter-spacing 1.6, uppercase | State colour dot, muted text. |
| Home headline "Everything is on track." | 19 / 400, centred, max 2 lines | Large and calm. |
| Sheet titles "Today", "Finance" | 30 / 500 (agent screen), 22 / 500 (sheets) | Agent title gets a 64×3 px gradient underline in the agent colour. |
| Section labels "YOUR AGENTS", "WHAT I DID", "TODAY" | 10 / 600, letter-spacing 1.2 | Dim colour. |
| Card meta "CALENDAR · URGENT" | 9 / 600, letter-spacing 1.0 | Muted; timestamp right-aligned ("NOW", "3 MIN AGO"). |
| Card body | 15 / 500 | Ink. |
| Hero number "$12,450" | 40 / 500 | White. |
| Body small / descriptions | 13 / 400 | Muted. |

### 6.4 Shape, glass and spacing
- Screen side padding 20. Card radius 20 (large sheets 28, top corners only for bottom sheets). Pills fully rounded (height 32 for small actions, 52 for the Ask bar).
- Glass surface = blur (intensity ~25–30, dark tint) + `glassFill` + 1 px `glassBorder` + a soft inner top highlight (1 px, white 8%). On Android, if blur is unavailable or janky, use `rgba(20,22,28,0.82)` with the same border.
- Sheets inherit a faint gradient of the current scenario colour (e.g. teal-to-blue in calm, red in urgent, see video 4:55).
- Stat tiles have a 2 px top border in the agent colour that fades out to the sides.
- Spacing scale: 4, 8, 12, 16, 20, 24, 32.

### 6.5 Motion tokens
- Springs: `snappy` (damping 18, stiffness 220) for presses and pills; `soft` (damping 22, stiffness 120) for sheets and layout; `float` (sine-based) for ambient motion.
- Every ambient loop must be seamless: drive it from one clock and use whole-number frequencies of the loop phase (see `design.md` §4.1).
- Press feedback on every tappable: scale 0.96, opacity 0.85, light haptic.
- Respect Reduce Motion (`useReducedMotion`): stop ambient rotation and drift, keep transitions as quick fades, keep all hotspots working.

---

## 7. Signature graphics (Phase 3, the most important part)

Everything here is drawn with `@shopify/react-native-skia`, animated with Reanimated shared values on the UI thread. Target 60 fps on a mid-range Android phone. Build each piece as an isolated component with a small dev preview screen so you can tune it alone.

### 7.1 The Crystal (core avatar)
A large, slowly rotating, low-poly faceted gem, roughly 46–48 % of screen width, centred at about 52 % x / 43 % y of the screen. It is the visual heart of the app.
- **Geometry (`crystalGeometry.ts`):** generate an icosphere (subdivision 2 ≈ 320 faces, or subdivision 1 = 80 faces on low-end devices), then jitter each vertex radius by ±6–10 % with a seeded random so it reads as an irregular cut gem, not a ball. Precompute once.
- **Per frame (worklet):** rotate around a tilted axis (one full turn per ~18 s, plus a slow wobble), project with a simple perspective camera, cull back faces, sort front faces by depth, and shade each face:
  - base colour = an iridescent palette lookup (cosine palette, see `irid()` in `familyos_3d.py`) driven by the face normal and time, tinted towards the scenario palette;
  - add Lambert diffuse from a key light at top-left-front and a fill from lower-right;
  - add a Fresnel rim so edge-on faces glow brighter;
  - add a small specular sparkle on 1–3 faces that face the key light.
  - Draw each face as a filled path plus a 0.6 px stroke of white at 10–18 % opacity (the visible facet edges in the video).
- Build the faces into an `SkPicture` inside a `useDerivedValue` (or render a `Picture` / `Atlas`) rather than re-rendering React components per face.
- **Glow:** under the gem, a radial gradient halo in the scenario colour (opacity pulses gently, period 4 s). In `urgent` the halo pulses faster (period 1.6 s) and the gem has a subtle 1–2 px tremble.
- **Tap:** the gem squashes to 0.94 and springs back, light haptic, then starts the summary walkthrough (§8.1.6).
- **Mini variant:** the same component at ~64 px is shown at the top of the Dashboard sheet and the agent screens (video 3:20). It keeps rotating and keeps its dust.
- **Fallback:** if a device cannot hold 50+ fps, swap to the `stage7_quantum_glass_hub.gif` render from the zip (tinted by a coloured overlay for the scenario) and keep the particles. Gate this behind a `lowPowerGraphics` flag decided at start-up (e.g. measured frame time in the first 2 s).

### 7.2 Particle dust halo
A cloud of 500–900 tiny points (1–2 px, colour `dust` mixed with the scenario colour, opacity 0.2–0.8) in an uneven ring around the gem from about 0.9× to 1.6× its radius, denser near the gem. Each particle drifts slowly on its own orbit and twinkles. Draw with Skia `Points` or `Atlas` in one draw call. Also scatter 60–120 very faint stars over the whole background that drift and twinkle.

### 7.3 Agent satellites
Five small crystals (about 12 % of screen width), each made with the same geometry generator (subdivision 0–1, 20–80 faces) and coloured entirely in its agent colour with bright facet edges and a soft halo, each rotating at its own speed. Positions (fraction of screen width / height), with the label centred underneath:

| Agent | x | y |
|---|---|---|
| Finance | 0.50 | 0.23 |
| Education | 0.87 | 0.38 |
| Grocery | 0.73 | 0.61 |
| Household | 0.30 | 0.61 |
| Calendar | 0.12 | 0.38 |

Each satellite floats in a small Lissajous drift (±4–6 px, different phase per agent). When an agent has items needing attention, show a small round badge (16 px) at the satellite's top-right with the count, coloured by the item's severity (urgent red `#FF4D5E`, heads-up amber `#FFB23F`, insight violet `#A98BFF`, positive green `#4DFF8C`). Tapping a satellite opens that agent's Deep Layer screen (§8.7) with a scale-up transition from the satellite's position. During the summary walkthrough, the satellite of the agent being read gets a thin ring around it and the others dim to 60 %.

### 7.4 Particle morph (core → agent icon)
During the summary walkthrough (§8.1.6), the gem dissolves into ~1,200 glowing particles that fly to form the current agent's icon, tinted in the agent colour, holding the shape with a gentle shimmer and a faint circular outline behind it. Moving to the next item, the particles fly from one icon to the next. At the end, they rebuild the gem.
- Icons (as seen in the video): Finance = dollar sign inside a ring; Education = graduation cap; Household = house; Calendar = calendar shape (shown loosely scattered in the video); Grocery = basket.
- Write each icon as an SVG path string in `iconPoints.ts`. At start-up (JS thread, once), sample N target points per icon: fill-sample with `path.contains(x, y)` on a jittered grid, plus outline points from `ContourMeasure` for crisp edges. Cache the arrays.
- The gem's source points = random points inside the gem silhouette.
- Animate one shared progress value 0→1 with a staggered per-particle delay and an ease-in-out cubic, plus a little curl noise in mid-flight. Duration ~900 ms.

### 7.5 Ambient background
Full-screen Skia canvas behind everything: pure black base, a large soft radial gradient in the scenario colour centred behind the gem (opacity 0.10–0.25), a second faint gradient from the top-left corner, plus the star field. When a sheet opens, the background stays alive but is dimmed and blurred under the sheet.

### 7.6 Charts
- **Sparkline (Finance hero):** smooth curve (Catmull-Rom) in the agent colour, 2 px, with a vertical gradient fill fading to transparent, a glowing end dot, drawn in with a 900 ms path-trim animation on mount.
- **Week bars (Calendar):** 7 rounded bars in muted blue-grey; today's bar highlighted in the agent colour; bars grow from the bottom with stagger on mount.
- **Stat tiles:** count-up animation for numbers on mount (600 ms).

---

## 8. Screens and flows (Phase 4)

Build in this order: Home → Ask bar + Summary button → Today sheet → Needs-you sheet → Profile menu → Chat → Dashboard sheet → Agent screens → restyle remaining existing screens. Check each against the video frames before moving on.

### 8.1 Home — "Orbit" screen (video 0:00)
Full-screen, no tab bar, no header bar. Layers from back to front: ambient background → dust and stars → satellites behind → gem → satellites in front → text and controls.

1. **Top-left block:** date (muted), greeting (white), then the summary line: coloured dot + `Today's summary · all clear ›`. Tapping the summary line opens the Needs-you sheet if anything needs attention, otherwise the Today sheet.
2. **Top-right:** a glass pill with a 28 px circular avatar showing the initial "M" and a chevron (`M ⌄`). Opens the Profile menu (§8.5).
3. **Centre:** gem, dust halo and the five satellites (§7).
4. **Status block** (about 81 % height): `● CALM` label, then the headline below (calm: "Everything is on track."; other scenarios: the top item's text, e.g. "A $1,240 charge on the card ending 4417 looks unfamiliar."). When more items exist, show a small glass pill `+7 more` under it that opens the Needs-you sheet. The headline cross-fades and slides 8 px when it changes.
5. **Bottom bar** (about 93 % height, above the safe area):
   - Left: the **Ask bar**, a 52 px glass pill with a keyboard icon, placeholder "Ask FamilyOS", and a 40 px white circular **mic button** inside its right end. Tapping the bar opens the Chat sheet (§8.6) with the keyboard up. Tapping the mic shows a listening state (the mic button pulses, a small waveform animates in the bar, the gem's halo breathes with fake audio levels) for about 2.5 s, then drops a canned transcript into the chat.
   - Right: the **Summary button**, a 52 px circular glass button with a list-plus icon and a thin coloured ring. Behaviour depends on the "Summary button" setting (§8.5): **Read** opens the Today sheet; **Play** starts the walkthrough (6). While playing, the icon becomes a stop square and the ring fills as progress.
6. **Summary walkthrough** (also started by tapping the gem): steps through today's items one by one (about 3.5 s each). For each item: the gem morphs into the agent's icon (§7.4), the agent's satellite is highlighted, the status label becomes e.g. `● TODAY · FINANCE · 5 OF 7` (or `● EDUCATION · 3 OF 4` when filtered to one agent after tapping a satellite's summary), and the headline shows the item text. In Play mode, read each item aloud with the speech library. Tapping stop, or any tap on the canvas, ends it and the particles rebuild the gem.
7. **Swipe up anywhere on Home** opens the Dashboard sheet (§8.3) while the gem shrinks and travels to the top centre (shared-element style, driven by the sheet position).
8. **Toasts:** small glass pill above the bottom bar, auto-hide after 2.2 s (e.g. "The summary button now opens the written summary", "Done").

### 8.2 Today sheet — written summary (video 0:20 and 3:45)
Modal glass card (fills about 85 % of height, 16 px side margins, rounded 28), with a small `Close` pill floating above it. The Home screen stays visible behind it, blurred and dimmed.
- Header: "Today" (left), date (right, muted).
- Optional top row of two tiles: Weather (`68°F`, "Rain after 3 pm. Pack umbrellas for pickup.") and First event (`9:30 am`, "Dentist. 12 min drive.").
- Section label `TODAY`, then rows. Each row: 28 px glowing orb in the agent colour, agent name small and uppercase above the text, the text, and a chevron. Tapping a row opens that agent's screen. Rows stagger in on open (40 ms apart, fade + 12 px rise).
- Dismiss: `Close`, swipe down, or tap outside.

### 8.3 Dashboard sheet — "Your agents" (video 3:20)
A bottom sheet opened by swiping up on Home, covering about 80 %. The mini gem sits above it at the top centre.
- Handle bar, date, greeting "Good evening, Michael", section label `YOUR AGENTS`.
- 2-column grid of glass agent cards: coloured dot + agent name (600) + one-line status (muted). Finance "$12,450 reserve · up 4.2%", Education "Ethan and Mia on schedule", Household "Electrician at 4 pm", Calendar "3 events today". Grocery is a full-width card: "Cart ready · 14 items · $86.40".
- Full-width "Today's summary" card: "All clear · tap to read ›" (or "3 urgent · tap to read" in the urgent scenario), opens the Today sheet (or Needs-you sheet when urgent).
- In non-calm scenarios, cards with pending items show a badge and the whole sheet takes on the scenario tint (video 4:55, red).
- Bottom: the Ask bar (without the summary button).
- Tapping a card pushes the agent's screen. Dragging the sheet down returns to Home and the mini gem grows back into the core.

### 8.4 Needs-you sheet (video 2:05)
Same modal card style as Today, header `Needs you · 13` (live count), tinted by the most severe item.
- Each item is a glass card with a 3 px left accent bar in its severity colour (urgent red, heads-up amber, insight violet), a meta row `CALENDAR · URGENT` with a timestamp on the right (`NOW`, `3 MIN AGO`, `3:10 PM`, `YESTERDAY`, `TODAY`), the text, then a white primary pill and a glass `Later` pill.
- Items and actions to seed: see §10.
- **Swipe right** to complete: the card's background reveals green with `✓ DONE` on the left; release past 35 % width to complete (success haptic, card collapses, count decrements, toast "Done"). **Swipe left** to snooze: amber background with `LATER ›` on the right. Tapping the primary pill = complete with that action; `Later` = snooze.
- When the list is empty, close the sheet and switch Home to `calm` with a celebratory particle burst from the gem.
- Completing items also updates satellite badges, the summary line count and the Home headline.

### 8.5 Profile menu (video 1:25)
A glass popover card anchored under the top-right avatar pill (scale-from-corner animation). Header: avatar "M", "Michael", "Family plan · 5 agents", `Close` pill. Rows: Profile, Family members, Agents and permissions, Notifications, Privacy and data, **Summary button** (with a trailing chip `Read` / `Play` that toggles in place and shows a toast explaining the new behaviour), Settings, Help and feedback, divider, Log in or switch account, **Log out** (red). Rows without a destination yet open a simple placeholder screen in the new design language. "Family members" shows the family (Michael, partner, Ethan, Mia, plus others from `design.md` §13.8 if you like) with avatar-stage images from the zip chosen by age (§11.3).

### 8.6 Chat sheet — "Ask FamilyOS" and "Ask {Agent}" (video 1:45 and 2:55)
Large glass sheet. Title "Ask FamilyOS" (or "Ask Finance", etc.) with a short gradient underline, `Close` pill.
- Assistant bubbles: left, dark glass, radius 16. User bubbles: right, white background, dark text.
- First message: "Hi Michael. Ask me anything about the family: money, school, home, calendar or groceries." (agent version: "Hi Michael. Ask me anything about finance.")
- Horizontally scrolling suggestion chips above the input (glass pills). Input "Type a message" with a white circular send button (arrow up).
- Replies come from `mocks/chatReplies.ts` by keyword, after a typing indicator (three pulsing dots) of 600–1200 ms. New messages slide up and fade in.
- "Ask about this" on a timeline item opens the agent chat with the user message prefilled as "Tell me more about: {item title}" and sends it.

### 8.7 Agent Deep Layer screens (video 2:30 Finance, 3:00 Calendar, 3:35 Grocery)
Full screen push (slide from right, or scale-up from a satellite). Layout:
- Top bar: circular glass back button (left), mini gem in the agent's colours (centre).
- Glass content panel with: agent title (30/500) + gradient underline, subtitle (e.g. "On track this month", "3 events today").
- Hero card: Finance shows "Projected reserve", "$12,450", "▲ 4.2% this month" in agent colour, and the sparkline. Calendar shows "1 clash needs you" and the week bars. Education, Household and Grocery use an appropriate hero (progress bars, task ring, item chips) in the same style.
- Three stat tiles (Finance: Invested $18.4k, Est. expenses $4.2k, Optimized $620; Calendar: Free time 2.5 h, Clashes 1, This week 14).
- `WHAT I DID` timeline: coloured dot, time ("Today · 9:12 am", "Yesterday", "Oct 4"), title (600), description (muted), and a right link (`Undo` in agent colour for the newest, `Details` for the rest). Tapping an item expands it in place (height animation) to show key/value rows plus `Undo` and `Ask about this` pills.
- Bottom: Ask bar "Ask Finance anything" with mic, which opens the agent chat.
- `Undo` shows a confirmation toast and marks the item as undone (strikethrough title, muted).
- Back: button, edge-swipe on iOS, hardware back on Android.

### 8.8 Existing screens that are not in the video
For screens that already exist in the mobile app but do not appear in the video (e.g. splash, login, sign-up, OTP, settings, onboarding), restyle them in the same design language. Use `design.md` §13 as the spec for loading, log-in, sign-up, one-time code and family-pod screens: OLED black, a faint violet glow from the top and teal from the bottom, drifting dust, frosted inputs with 1 px borders, Inter, violet `#8073FF` primary buttons, and the gem with orbiting agent-coloured dots on the loading screen. Do not invent new flows the app does not already have, except the screens listed in §8.1–§8.7.

---

## 9. Interaction and motion catalogue

| Trigger | Result |
|---|---|
| App open | Ambient fades in (400 ms), gem scales from 0.85 with a soft spring, satellites pop in one by one (80 ms stagger), text rises 8 px and fades in. |
| Tap gem | Squash and spring, then summary walkthrough (§8.1.6). |
| Tap satellite | Satellite scales up and the agent screen expands from its position. |
| Swipe up on Home | Dashboard sheet follows the finger; gem shrinks to the mini gem at the top. |
| Tap summary line / `+N more` | Needs-you sheet (or Today sheet when nothing needs you). |
| Tap summary button | Read mode: Today sheet. Play mode: spoken walkthrough with particle morphs. |
| Tap Ask bar / mic | Chat sheet / listening state then chat. |
| Swipe card right / left | Done (green) / Later (amber), with haptics and count update. |
| Scenario change | Core palette, halo, background, dot, label, headline and badges all interpolate together over 700 ms. |
| Open any sheet | Background dims to 55 % and blurs; sheet springs up with `soft`. |
| Expand timeline item | Height animates, chevron rotates, key/value rows fade in. |

---

## 10. Mock data and copy (put all of it in `mocks/data.ts`)

Use these exact strings; they are from the video. Keep currency symbol, names and amounts as data so they can be changed in one place.

**Profile:** name "Michael", initial "M", plan "Family plan · 5 agents", children Ethan and Mia, summary-button mode default `Read`.

**Today items (7):**
1. Household — "The electrician arrives at 4 pm."
2. Finance — "Reserve is $12,450, up 4.2% this month."
3. Education — "Ethan's math final is tomorrow."
4. Grocery — "Your cart is ready: 14 items, $86.40."
5. Finance — "The mortgage, $2,150, is due Oct 28."
6. Household — "Furnace service is booked for Nov 9."
7. Calendar — "Mia's recital is Saturday at 2 pm."

Education-only walkthrough (4): "Ethan and Mia are on schedule." · "Ethan's math final is tomorrow." · "Mia's science project is 90% done, due Friday." · "The parent-teacher conference is booked for Nov 6."

Today tiles: Weather "68°F" · "Rain after 3 pm. Pack umbrellas for pickup." First event "9:30 am" · "Dentist. 12 min drive."

**Needs-you items** (severity · agent · time · text · primary action):
- urgent · Calendar · NOW · "Your 2 pm client call overlaps Ethan's final." · "Move call to 3:30"
- urgent · Finance · 3 MIN AGO · "A $1,240 charge on the card ending 4417 looks unfamiliar." · "Review charge"
- urgent · Household · 1 MIN AGO · "The basement water sensor just tripped." · "Shut off valve"
- headsup · Household · 3:10 PM · "The electrician arrives at 4 pm." · "Confirm"
- headsup · Calendar · YESTERDAY · "Dentist tomorrow at 9:30 am." · "Add reminder"
- headsup · Education · TODAY · "Mia's science project is due Friday." · "See checklist"
- insight · Education · TODAY · "Ethan is ahead in math this month." · "Got it"
- insight · Finance · TODAY · "You could save $180 a month on subscriptions." · "See how"
Pad the list with a few more plausible items so the header can read "Needs you · 13". Each scenario in `scenarios.ts` selects which subset is active (calm: none; insight: insights only; headsup: heads-ups and insights; urgent: all).

**Dashboard card lines:** Finance "$12,450 reserve · up 4.2%", Education "Ethan and Mia on schedule", Household "Electrician at 4 pm", Calendar "3 events today", Grocery "Cart ready · 14 items · $86.40", Today's summary "All clear · tap to read".

**Finance screen:** subtitle "On track this month"; hero "Projected reserve", $12,450, ▲ 4.2% this month; tiles Invested $18.4k, Est. expenses $4.2k, Optimized $620. Timeline:
- Today · 9:12 am — "Moved Ethan's coaching to a lower tier" — "Saves $120 a month. Classes and materials stay exactly the same." — rows: Saves $120 a month · Takes effect Nov 1 · Checked with Coach Rivera · Done by Finance agent — link `Undo`.
- Yesterday — "Invested $1,500 of surplus" — "Added to your index fund. Within your $2,000 auto-invest limit." — rows: Amount $1,500.00 · Fund Total Market Index · Auto-invest limit $2,000 a month · Time Oct 19, 4:02 pm.
- Oct 4 — "Paid Mia's lab fees and the electric bill" — "Bundled into one payment to avoid late charges. Saved $25." — rows: Lab fees $65.00 · Electric bill $142.30 · Late fees avoided $25.00 · Paid from Checking.
- Oct 2 — "Caught a duplicate Instacart charge" — "Refund of $85 secured from the merchant."
Chat chips: "Show upcoming bills", "Move $500 to savings", "How much did we save?". Replies:
- bills → "Next up: the mortgage, $2,150 on Oct 28, and car insurance, $184 on Nov 2. Both are covered by checking."
- savings / move → "I can move $500 to savings today. It keeps checking above your $4,000 buffer. Want me to do it?"
- saved → "Since September I've saved you $620: $120 a month on Ethan's coaching, an $85 refund on a duplicate charge, and $25 in late fees avoided."
- "Tell me more about…" → "Here is what I did and why. Nothing else changed, and you can undo it from this page at any time."

**Calendar screen:** subtitle "3 events today"; hero "1 clash needs you" + week bars; tiles Free time 2.5 h, Clashes 1, This week 14. Timeline:
- Today · 9:05 am — "Spotted a clash with Ethan's final" — "Your 2 pm client call overlaps his final. Moving it to 3:30 works for everyone." — rows: Ethan's final 2:00 pm · Suggested 3:30 pm · Done by Calendar agent.
- Yesterday — "Moved the dentist to Thursday" — "Thursday at 9:30 am, clear of both school runs." — rows: New time Thu, 9:30 am · Office Lakeside Dental · Reminder 1 day before.
- Oct 4 — "Added Mia's recital" — "Saturday at 2 pm. Directions and parking info attached."
- Oct 2 — "Declined a duplicate invite" — "The same meeting was sent twice, so I kept one." — rows: Meeting Quarterly review · Kept Tue, 10 am.
Chips: "What's on today?", "Move my 2 pm call", "Find a free slot". Reply to the move request: "I can move your client call to 3:30 pm. Everyone on the invite is free. Want me to send the update?"

**Grocery screen** (subtitle "Cart ready · 14 items"). Timeline:
- Yesterday — "Swapped a brand to save $4.20" — "Same size and ingredients, lower price." — rows: Item Pasta sauce · Saved $4.20 · Rating 4.7 stars.
- Oct 4 — "Added milk and eggs" — "Both were running low based on your usual pace." — rows: Milk 1 gallon · Eggs 1 dozen · Added $7.80.
- Oct 2 — "Flagged a duplicate charge" — "Instacart refunded $85 within a day."

**Education and Household screens:** not shown in detail in the video. Build them with the same layout, using the Education and Household items above plus 2–3 plausible timeline entries each (e.g. "Booked the parent-teacher conference", "Scheduled furnace service").

**Home chat replies:** greeting as in §8.6; "What needs me today?" → "Nothing needs you right now." (calm) or a one-line summary of the top items; "How are we doing on money?" → "Finance is on track. Reserve is $12,450, up 4.2% this month."; "What's for dinner groceries?" → a short grocery reply; anything else → a friendly fallback that names the five agents.

---

## 11. Platform, performance and accessibility

### 11.1 iOS and Android parity
- Safe areas on every screen (notch, Dynamic Island, Android gesture bar). Status bar light content; on Android make it translucent with a transparent background and draw under it.
- Android: dark navigation bar, hardware back closes the top sheet first, then pops the screen. Check blur and Skia rendering on a real or emulated mid-range device.
- iOS: native swipe-back on stack screens; keyboard handling for chat (`KeyboardAvoidingView` or the bottom-sheet keyboard behaviour).
- Lock the app to portrait unless the existing app supports landscape.

### 11.2 Performance budget
- 60 fps on Home with gem + 5 satellites + dust. Keep all per-frame work in worklets; no React re-render per frame.
- Draw dust/stars in one `Points`/`Atlas` call. Precompute geometry and icon samples once.
- Pause all Skia animation when Home is fully covered by a screen or when the app goes to the background (`AppState`).
- Provide `lowPowerGraphics`: fewer facets, ~300 particles, no satellite rotation, GIF fallback for the gem.

### 11.3 Avatar stages from the zip
Copy the 8 stage PNGs and GIFs into `assets/familyos/avatars/`. Add `avatarForAge(age)` using the stage table in `design.md` §6 (1: 3–5, 2: 6–8, 3: 9–12, 4: 13–15, 5: 16–18, 6: 19–25, 7: 26–59, 8: 60+). Use them for family-member lists, the profile header (optional) and the loading screen. The live Skia gem remains the Home core for the adult user (stage 7 look).

### 11.4 Accessibility
- Every tappable has `accessibilityRole` and a label ("Finance agent, 1 urgent item", "Summary, plays today's summary").
- Minimum touch target 44×44 (satellites get an invisible larger hit area).
- Text scales with system font size up to 1.3× without breaking layout.
- Reduce Motion support as in §6.5.

---

## 12. Code quality
- TypeScript (if the project uses JS, keep new files in TS only if the project already supports TS; otherwise JS with JSDoc types).
- Small, reusable components; no screen file over ~300 lines.
- No inline magic numbers for colours, spacing or durations; use the theme.
- Run the project's lint and type-check for the mobile package and fix all new errors.
- Comment the non-obvious maths in `crystalGeometry.ts` and `ParticleMorph.tsx`.

---

## 13. Verification and definition of done

Run all of these before declaring the work complete:

1. **Web is untouched.**
   - `git diff --stat main...HEAD` (or against the starting commit) must show no files inside the web app. List every changed file outside the mobile app and justify it (for example a lockfile in a monorepo).
   - Re-run the exact web commands from `design-reference/web-baseline.txt`. Results must match the baseline (same success, no new warnings caused by your changes).
2. **Mobile builds and runs** on an iOS simulator (if on macOS) and an Android emulator. Type-check and lint pass.
3. **Visual check:** for each screen in §8, take a screenshot (`xcrun simctl io booted screenshot`, `adb exec-out screencap -p`) and put it next to the matching video frame. Fix obvious differences in layout, size, colour and spacing. Save the pairs in `design-reference/compare/`.
4. **Flow check:** walk through every row of §9 on both platforms.
5. **Performance check:** use the React Native perf monitor on Android; Home must stay near 60 fps on the UI thread.
6. **Mock layer check:** search the screens for hard-coded data strings; they must all come from `mocks/`.

When done, write `MOBILE_UI_REPORT.md` with: what was built, the dependency list with versions, any native steps the developer still has to run, known gaps versus the video, how to switch scenarios, and how to replace the mock services with the real backend. Commit, and print a short summary.

---

## 14. When to stop and ask (otherwise keep going)

Ask the developer only if:
- you cannot find the mobile app, or cannot tell which code is web and which is mobile;
- isolating the web app would require changing a shared file in a way that could alter web behaviour;
- a required dependency conflicts with the existing RN/Expo version and the only fix is a major upgrade of React Native, Expo SDK or React;
- the build needs credentials, signing, paid services or a machine you do not have (e.g. iOS build without macOS — in that case finish Android, note iOS steps, and continue);
- existing mobile code you would have to delete contains real business logic.

For everything else, make a sensible decision, note it in `MOBILE_UI_PLAN.md`, and continue.
