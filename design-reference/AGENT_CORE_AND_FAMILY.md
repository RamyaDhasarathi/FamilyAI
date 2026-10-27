# AGENT_CORE_AND_FAMILY.md — Interactive Core + Family Member Management

This is the second task for the FamilyOS mobile app in `mobile/` (Expo, React Native, TypeScript). The first task, described in `AGENT.md`, built the current UI: the Home orbit screen with the faceted crystal core, the five agent satellites, the sheets, the agent screens and the mock service layer. That UI is approved. This task adds two things on top of it:

- **Part A — Interactive core.** The centre crystal reacts like jelly when tapped, and the user can spin it with a finger.
- **Part B — Family members.** Screens and flows to add, view, edit and remove family members.

Everything new must look and move like what already exists. Reuse the existing theme, components, graphics and patterns. Do not invent a new visual style.

---

## 1. Rules (all rules in `AGENT.md` §1 still apply)

1. **Only change files inside `mobile/`.** The web apps, Python backend, `ios/` SwiftUI app and everything else stay untouched.
2. **Stay Expo Go compatible.** Only add libraries that run in Expo Go, installed with `npx expo install`. If something truly needs a custom dev build, stop and ask first.
3. **Reuse before you build.** Use the existing tokens, `GlassCard`, `GlassPill`, `PillButton`, `Toast`, `SectionLabel`, `SwipeCard`, `ParticleField`, `Crystal`, the bottom-sheet setup, the mock-service pattern and the zustand store. Only create a new component when nothing existing fits, and put it in the same folder structure.
4. **Do not break anything that works.** The Home screen, satellites, sheets, chat, agent screens, summary walkthrough, scenario switcher and swipe-up dashboard must behave exactly as before, apart from the changes this file asks for.
5. **All data goes through the service layer.** New family-member data has a typed interface in `services/interfaces.ts` and a mock implementation, so a real backend can replace it later.
6. Create the branch `feat/core-gestures-and-family` from the current branch. Commit at the end of every phase.
7. Keep 60 fps on Home. All per-frame and gesture work runs on the UI thread in worklets.

---

## 2. Phase 0 — Read the current code first

Before changing anything:

1. Read `AGENT.md`, `MOBILE_UI_PLAN.md` and `MOBILE_UI_REPORT.md` (if present) to recall the decisions already made.
2. Read the existing implementation, at minimum:
   - the crystal: `Crystal.tsx`, `crystalGeometry.ts`, how rotation is driven now and how faces are projected and shaded;
   - `ParticleField` / `ParticleMorph` and how the dust is drawn;
   - the Home screen's gesture setup: the swipe-up-to-Dashboard pan, the satellite taps, the current tap-on-core behaviour and the summary walkthrough trigger;
   - the profile menu and what the "Family members" row currently opens;
   - the mock data for family members (if any), `mocks/`, `store/`, `services/interfaces.ts`;
   - the theme tokens, `SwipeCard` (the Needs-you swipe), toasts and the bottom-sheet wrapper;
   - how the avatar-stage images from `UI_Design1.zip` are stored and whether an `avatarForAge()` helper exists.
3. Check which of these are installed: `@react-native-async-storage/async-storage`, `expo-secure-store`, `@react-native-community/datetimepicker`, `expo-image-picker`, `expo-document-picker`.
4. Add a short "Task 2" section to `MOBILE_UI_PLAN.md`: what you found, which files you will touch, which new files you will add, and which libraries you will install. Then continue without waiting.

**Small polish to include:** on the current Home screen a vertical scroll indicator is visible at the top-right edge. Home should not show a scrollbar. Hide it (`showsVerticalScrollIndicator={false}`), or remove the scroll container if Home doesn't need to scroll.

---

## 3. Part A — Interactive crystal core

### 3.1 What the user should feel
- **Tap:** the crystal behaves like a soft jelly. It squashes where the finger lands, bulges out at the sides, then wobbles back into shape with 3–4 decaying oscillations over about 0.9 s. A ripple travels across the facets from the touch point. The dust around it puffs outwards and settles back.
- **Drag:** the crystal follows the finger like a trackball. The surface under the finger moves in the same direction as the finger. While dragging it stretches slightly in the direction of motion.
- **Flick and release:** it keeps spinning with momentum, slows down smoothly, wobbles slightly as it settles, then gently blends back into its normal idle rotation. It never snaps or jumps to a fixed orientation.

### 3.2 Gesture behaviour and conflicts
Attach the gestures to a circular hit area exactly over the crystal (radius = crystal radius + 12 px). Outside that circle, nothing changes.

| Gesture on the crystal | Result |
|---|---|
| Single tap | Jelly wobble only (§3.3), light haptic. |
| Drag (pan, activates after 6 px) | Rotate the crystal (§3.4). Auto-rotation pauses while the finger is down. |
| Flick | Momentum spin with friction, then return to idle rotation. |
| Long-press (500 ms) | Starts the summary walkthrough (what a tap used to do), medium haptic. |
| Tap during the summary walkthrough | Stops the walkthrough, as before. Jelly and rotation are disabled while the crystal is morphed into an icon. |

Rules:
- A pan that **starts on the crystal** must never open the Dashboard. A vertical swipe that **starts outside the crystal** must still open the Dashboard exactly as before. Use React Native Gesture Handler's composition and cross-component relations (`Gesture.Exclusive` / `Race`, `blocksExternalGesture` or `requireExternalGestureToFail`) to achieve this, and test both cases.
- Satellite taps keep working and take priority over the crystal wherever hit areas could touch.
- Update the accessibility label of the crystal: "Family core. Tap to wobble, drag to spin, long-press to hear today's summary." Add an accessibility action for "Play summary".

### 3.3 Jelly implementation (tap)
Do this in the geometry worklet, not with a simple view scale, so the facets genuinely deform.
1. **Find the touch point on the crystal.** Convert the tap's screen position into a ray from the camera, intersect it with the crystal's bounding sphere, then rotate the hit point into the crystal's model space using the inverse of the current rotation. If the ray misses (tap on the edge of the hit area), use the nearest point on the silhouette.
2. **Ripple deformation.** For each vertex, compute the angle θ between the vertex direction and the touch direction. Displace the vertex along its normal by:
   `d = −A · e^(−θ²/σ²) · e^(−λt) · cos(ωt) + B · e^(−λt) · sin(ωt − kθ)`
   The first term is the dent under the finger. The second is a ripple travelling outwards. Start with A ≈ 0.10, B ≈ 0.035 (fractions of the radius), σ ≈ 0.7 rad, λ ≈ 4.5 /s, ω ≈ 22 rad/s, k ≈ 3. Tune by eye so it reads as soft jelly, not rubber or liquid.
3. **Global squash and stretch.** Apply a volume-preserving scale along the tap direction: shrink along it by s and grow perpendicular by s/2, driven by a low-damping spring (about damping 7, stiffness 180, mass 1) from s = 0.12 back to 0.
4. **Light.** While the ripple runs, brighten facet edges near the ripple front and add a short pulse to the halo glow.
5. **Dust.** Push dust particles outward radially by up to 10 px, scaled by their closeness to the touch point, then spring them back.
6. **Repeated taps** add together: each tap starts a new ripple with its own start time (keep up to 3 active ripples) and re-kicks the squash spring, clamped so the shape never inverts.
7. Recompute face normals from the deformed vertices so shading follows the dent. If that is too slow on a mid-range Android phone, approximate by tilting each face normal using the displacement of its centroid.

### 3.4 Rotation implementation (drag and flick)
1. Store the crystal's orientation as a **quaternion** in a shared value. The existing idle rotation should also become a quaternion step applied each frame, so manual and automatic rotation combine cleanly.
2. **Drag:** each pan update with movement (dx, dy) in pixels rotates around the screen-space axis perpendicular to the movement, by angle = distance / crystal radius in pixels. Pre-multiply this delta onto the current orientation. Check the axis signs on device: the facet under the finger must move with the finger in both directions on both axes.
3. **Stretch while dragging:** stretch the crystal by up to 6 % along the drag direction, proportional to the drag speed, and release it with the jelly spring when the finger lifts.
4. **Flick:** on release, convert the pan velocity into an angular velocity vector (clamp to about 4 full turns per second). Each frame, apply it and decay it frame-rate-independently (`ω *= exp(−2.8 · dt)`).
5. **Settle:** when the angular speed drops below the idle rotation speed, blend the idle rotation back in over 1.2 s, continuing from the current orientation. Add one small jelly wobble as it settles.
6. Dust and satellites do not rotate with the crystal. Satellites can respond with a subtle 2–3 px parallax shift in the drag direction.
7. **Haptics:** light impact on touch-down; a soft selection tick roughly every half turn during a fast spin, at most 6 ticks per spin.

### 3.5 Reduce Motion and low-power mode
- With Reduce Motion on: the tap gives only a gentle 0.96 scale pulse; drag rotation still works (it's user-driven), but flicks stop within 0.3 s and there is no wobble.
- In the existing `lowPowerGraphics` mode: skip per-vertex ripple; use only the global squash, normal rotation and fewer dust particles.

### 3.6 Done when
- Tapping anywhere on the crystal gives a visible dent at that spot and a jelly wobble, on both platforms.
- Dragging spins it in the direction of the finger; flicking spins and slows smoothly back to idle.
- Swipe-up outside the crystal still opens the Dashboard; pans on the crystal never do.
- Long-press starts the summary walkthrough. Satellites still open their agent screens.
- Home stays near 60 fps while spinning and tapping repeatedly.

Commit: `feat(core): jelly tap and finger rotation for the crystal core`.

---

## 4. Part B — Family member management

The spec for this area is `design.md` §13.5–§13.7 in `UI_Design1.zip`, adapted to the current app's look (§4.10). Where this file and `design.md` disagree, follow this file.

### 4.1 Where it lives
- **Entry:** Profile menu → "Family members" opens the **Family** screen (§4.4). Add a trailing amber count chip to that row when any member has sections needing an update (e.g. `3`).
- Also add an "Add family member" row to the Profile menu, directly under "Family members", which opens the Add sheet (§4.5) straight away.
- In the Profile menu header, keep "Family plan · 5 agents" as it is.

### 4.2 Data model (`services/interfaces.ts`)
```ts
type Relationship =
  | 'Self' | 'Spouse' | 'Partner' | 'Son' | 'Daughter' | 'Father' | 'Mother'
  | 'Brother' | 'Sister' | 'Grandfather' | 'Grandmother' | 'Grandson' | 'Granddaughter'
  | 'Uncle' | 'Aunt' | 'Nephew' | 'Niece' | 'Cousin' | 'In-law' | 'Other';

type SectionId = 'basic' | 'contact' | 'ids' | 'health' | 'banking';
type SectionStatus = 'complete' | 'needsUpdate' | 'notStarted';

interface FamilyMember {
  id: string;
  isOwner: boolean;              // true only for the account holder ("Self")
  fullName: string;
  preferredName?: string;
  relationship: Relationship;
  relationshipOther?: string;    // when relationship === 'Other'
  dateOfBirth: string;           // ISO date
  photoUri?: string;
  sections: Record<SectionId, { status: SectionStatus; data: Record<string, unknown> }>;
  createdAt: string;
  updatedAt: string;
}
// Derived, never stored: age, avatarStage (1–8), stageName, completion (0–1), sectionsNeedingUpdate
```

Service contract (mock implementation with 250–600 ms latency, like the others):
`listMembers()`, `getMember(id)`, `createMember(basics)`, `updateBasics(id, patch)`, `updateSection(id, sectionId, data, status)`, `deleteMember(id)` (soft delete), `restoreMember(id)`, `purgeMember(id)`, `resetDemoFamily()`.

### 4.3 Storage (dummy, but survives app restarts)
- Non-sensitive fields: persist with `@react-native-async-storage/async-storage` (zustand `persist` middleware is fine).
- Sensitive fields (ID numbers, account numbers, policy numbers, medical details): store with `expo-secure-store`, one key per member and section (`member_<id>_<section>`), kept small. Never log them.
- Add "Reset demo family" to the dev-only Settings area next to the scenario switcher.
- On a fresh install, seed from the existing mock family. If the existing seed has fewer than 5 members or no ages, seed: Michael (Self, 42, all complete), his spouse (39, Banking needs update), Ethan (Son, 14, IDs needs update), Mia (Daughter, 10, complete), a grandparent (68, IDs and Banking need update). Keep names already used elsewhere in the mock copy (Michael, Ethan, Mia). Mixed statuses make the amber states visible straight away.

### 4.4 Family screen (the hub)
Full-screen push from the Profile menu, styled like the agent Deep Layer screens.
- **Top bar:** circular glass back button (left). Title "Family" (30/500) with a short gradient underline that runs through the five agent colours. Subtitle "{N} members · {K} sections to update" (or "Everyone's details are up to date").
- **Family orbit header (graphical):** a compact Skia scene about 150 px tall: the mini crystal in the centre with one glowing dot per member orbiting it on a tilted ring. Each dot uses the accent colour of that member's avatar stage; the owner's dot is slightly larger. When a member is added, a new dot flies in from the edge and joins the ring; when one is removed, its dot dissolves into particles. Tapping the mini crystal gives the same jelly wobble as Home.
- **Summary card** (glass): an animated completion ring (Skia arc, count-up on mount), "{x} of {N} profiles complete", "{K} sections still need updating".
- **Section label** `YOUR FAMILY`, then one card per member, owner first, then by age descending:
  - 56 px circular avatar (the stage image chosen by age, in a glass ring with a faint halo in the stage colour; use the GIF only for the owner card and the member profile hero to keep the list light);
  - name (600) with a small "You" chip on the owner;
  - "Son · 14 · The Glitch Synth" (muted);
  - a 28 px completion ring on the right;
  - tags underneath: an amber pill per section needing update ("IDs & documents", "Banking") or one green pill "All details up to date".
  - **Tap** → Member profile (§4.6). **Swipe left** (same feel as the Needs-you `SwipeCard`) reveals two round buttons: Edit (glass) and Remove (red). **Long-press** → a small glass context menu with Edit details / Remove from family. The owner card has no Remove anywhere.
  - Cards stagger in on mount (40 ms apart, fade + 12 px rise).
- **Footer:** a full-width white primary pill "+ Add family member", fixed above the safe area, over a soft fade-out gradient.
- **Empty state** (only the owner exists): the family orbit shows empty dashed slots, with the text "Add your family so your agents can plan for everyone." and the Add button.

### 4.5 Add family member sheet
A glass bottom sheet using the existing sheet wrapper (keyboard aware on both platforms).
- Title "Add family member", `Close` pill.
- **Live avatar preview card** at the top: shows the avatar for the date of birth entered so far (or a soft placeholder orb before a date is chosen), the stage name and age range ("Stage 4 · The Glitch Synth · 13–15"). When the stage changes, cross-fade the image with a small particle sparkle.
- Fields:
  - Full name (required, 2–60 characters, letters, spaces, `.'-`).
  - Relationship: wrapped glass chips; selected chip filled white with dark text. "Other" reveals a text field. "Self" is not offered (only one owner).
  - Date of birth: tap opens the native date picker (`@react-native-community/datetimepicker`; spinner/inline on iOS in the sheet, dialog on Android). Not in the future, not more than 120 years ago. Show "14 years" beside it once set.
- Validation messages appear under each field in a muted red, clear as soon as the field is fixed, and the sheet scrolls to the first problem.
- Buttons: primary "Add and fill details" (creates the member, closes the sheet, opens the details wizard at Basic information) and secondary "Add now, finish later" (creates the member with every section `notStarted`).
- After creating: success haptic, toast "{Name} added to your family", the new card springs into its sorted place in the list with a short glow, and a new dot joins the family orbit.
- Closing with unsaved input asks "Discard this new member?" (Discard / Keep editing).

### 4.6 Member profile screen
Full-screen push from a member card.
- Top bar: back button (left), "⋯" button (right) opening Edit basics / Remove from family.
- **Hero:** 140 px avatar-stage GIF floating with a slow bob, surrounded by the existing dust `ParticleField` tinted in the stage colour. Below: name (26/500), "Son · 14", a glass chip with the stage name. Tapping the avatar gives a small jelly squash (reuse the spring values from §3.3).
- **Completion:** ring + "3 of 5 sections complete".
- **Section label** `DETAILS`, then a row per section: icon in a circle tinted with the section colour, section title, a one-line masked summary ("Mobile ••••••4417 · Austin, TX"), a status pill (Complete green / Needs update amber / Not started dim) and a chevron. Tap → the wizard at that section.
- **Edit basics** opens a sheet like the Add sheet, prefilled (name, preferred name, relationship, date of birth, photo). Photo: "Choose photo" with `expo-image-picker` (library or camera, square crop), shown in the avatar ring with the stage halo still around it; "Remove photo" goes back to the stage avatar.
- Changing the date of birth so the stage changes: the avatar morphs (particle cross-fade), age-dependent wizard fields update, and a toast says "{Name} moved to Stage 5 · The Kinetic Prism".
- At the bottom: a red text button "Remove from family" (not shown for the owner).

### 4.7 Member details wizard
Implements `design.md` §13.6 in the current app style: a full-height glass sheet.
- **Header:** small avatar + name + "Step 2 of 6 · Contact and address", and a `Close` pill (saves and exits).
- **Progress bar:** six segments (five sections + Review) in each section's colour: Basic `#61B8FF`, Contact `#6BF294`, IDs `#BD9EFF`, Health `#FF6B9A`, Banking `#1FC7B8`, Review white. Completed segments stay tinted, skipped ones turn amber, the current one pulses gently. Every segment is tappable.
- Each section opens with its icon, title and one sentence saying which agents use the information and why (e.g. Health: "Used by your agents to plan appointments and remind you about medicines.").
- **Footer:** "Skip for now" (marks the section `needsUpdate`) and primary "Save and continue" (validates first and scrolls to the first problem).
- Moving between steps slides the content horizontally (300 ms, `soft` spring), and the sheet's background glow cross-fades to the next section colour.
- Sensitive sections (IDs, Health, Banking) show a dashed-border note: "Demo app: these details are stored only on this device."
- **Review step:** a card per section with a Complete / Needs update badge, a short masked summary and an "Edit" link. Primary button "Done".
- Fields, required markers and the child/teen variants follow `design.md` §13.6, with the region rules in §4.8.

### 4.8 Region-specific fields and formats
The current app's mock copy uses `$` and US-style names, but `design.md` §13.6 specifies Indian fields. Make this a single setting in `mocks/data.ts` (or the existing locale config): `region: 'IN' | 'US'`. Default it to `'IN'` if the mock currency symbol is `₹`, otherwise `'US'`.
- **IN:** exactly as `design.md` §13.6 (mobile 10 digits starting 6–9 with +91, PIN 6 digits, state, Aadhaar 12 digits, PAN `ABCDE1234F`, voter ID, passport `A1234567` + expiry, driving licence, IFSC `HDFC0001234`, UPI `name@bank`).
- **US:** mobile (+1, 10 digits, shown as `(555) 123-4567`), ZIP (5 digits or ZIP+4), state picker, driver's licence number + state, passport number + expiry, SSN **last 4 only** (optional, never the full number), bank name, account holder, routing number (9 digits), account number; no UPI.
- Both: email format, card nicknames with network and last 4 only, approval limit, auto-pay permissions, dates of birth not in the future, passport expiry not in the past, ID letters upper-cased while typing, and ID/account/policy numbers masked whenever the field isn't focused (`XXXX XXXX 0193`, `••••••••6789`).
- Children and teens follow the variants in §13.6 (school and grade, optional mobile under 13, optional email under 18, "Allowance and payments" instead of banking with "Paid from" choosing an adult member).
- Document uploads use `expo-document-picker` (images and PDFs), shown as small glass file chips with a remove "×". Store only the local file URI in the demo.

### 4.9 Remove flow
1. Trigger from swipe, long-press menu, the profile "⋯" menu or the profile's red button.
2. A centred glass dialog over a dimmed, blurred background: the member's avatar, "Remove {Name} from your family?", and "Their profile and saved details will be deleted from this device. Your agents will stop planning for them." Buttons: red "Remove" and glass "Cancel".
3. **Dependencies:** if the member is the "Paid from" adult for any child's allowance, the dialog also lists those children and lets the user pick another adult or choose "Decide later" (those children's payment sections become `needsUpdate`).
4. On confirm: warning haptic; the member's avatar dissolves into particles (reuse the particle system), the card collapses with a spring, their dot leaves the family orbit, counts update. If the user was on the member's profile, go back to the Family screen first and then animate the removal there.
5. A toast "{Name} removed · Undo" stays for 6 seconds. Undo restores the member to the same place with a reverse particle effect. After the toast expires, purge the member and their secure-store keys.
6. The owner can never be removed. If somehow triggered, show the toast "You can't remove the account owner."

### 4.10 Look and motion (match the current app)
- Same OLED black background with the faint scenario tint and drifting stars as the other screens; glass cards, borders, radii, spacing, type sizes and spring presets from the existing theme.
- Primary actions are white pills with dark text; secondary actions are glass pills; destructive actions use the existing danger red.
- Inputs: glass fields with a 1 px border that brightens and takes the current section colour on focus; floating labels; masked values reveal when focused.
- Use avatar-stage accent colours from `design.md` §6 (e.g. Stage 7 teal-violet, Stage 8 warm gold). Add a `stageAccent` map next to `avatarForAge()`.
- Ages under 3 use Stage 1. Stage boundaries: 1: 3–5, 2: 6–8, 3: 9–12, 4: 13–15, 5: 16–18, 6: 19–25, 7: 26–59, 8: 60+.
- Every list, sheet and dialog uses the existing press feedback, haptics and Reduce Motion handling.
- Hardware back on Android closes the top sheet or dialog first, then pops the screen. On iOS, edge-swipe back works on the pushed screens.
- Accessibility labels on everything ("Ethan, son, 14, one section needs updating", "Remove Ethan from family"). Swipe actions also have accessibility actions, so they work without swiping.

### 4.11 Done when
- A member can be added (both buttons), appears in the Family screen and orbit with the right avatar for their age, and survives an app restart.
- Basics and every section can be edited, with validation and masking working for the active region; changing a date of birth updates age, stage, avatar and age-dependent fields.
- A member can be removed from all four entry points, with the dependency check, particle animation and a working 6-second Undo; the owner cannot be removed.
- The Profile menu shows the correct "needs update" count.
- Nothing in Part A or the existing app regressed.

Commits: `feat(family): data model, storage and service`, `feat(family): family hub and member profile`, `feat(family): add/edit sheets and details wizard`, `feat(family): remove flow with undo`.

---

## 5. Verification (run before you finish)

1. `git diff --stat` against the starting commit shows changes **only inside `mobile/`** (plus `MOBILE_UI_PLAN.md` / report files).
2. Type-check and lint for `mobile/` pass with no new errors.
3. `npx expo start` runs, and the app works in Expo Go on Android (and iOS if available). Run the "Done when" checks in §3.6 and §4.11 on device.
4. Test edge cases: very long names, adding a member born today, changing a child's date of birth across 18, removing the only adult a child's allowance is paid from, rotating the crystal while a toast or sheet is opening, tapping the crystal rapidly 10 times.
5. Watch the performance monitor on Android while spinning the crystal and while scrolling the Family list; keep it near 60 fps.
6. Append a "Task 2" section to `MOBILE_UI_REPORT.md`: what was built, new libraries and versions, the gesture mapping (including that the summary walkthrough moved to long-press), how to switch region, how to reset the demo family, and how the family service maps to a future backend.

---

## 6. When to stop and ask

Ask only if:
- a feature needs a library that does not run in Expo Go;
- you can't make crystal gestures and the swipe-up-to-Dashboard gesture work together without changing how the Dashboard opens;
- the existing code is structured so differently from `AGENT.md` that following this file would mean rewriting working features.

For anything else, make a sensible decision, note it in `MOBILE_UI_PLAN.md`, and keep going.
