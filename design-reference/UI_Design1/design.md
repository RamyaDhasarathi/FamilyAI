# FamilyOS 3D Renders — Design Document

**Companion to:** *FamilyOS: Master UI/UX Architecture & Design Specification*
**Implementation:** `familyos_3d.py` (renderer and prototype builder; Python 3, NumPy, Pillow) and `familyos_prototype_template.html` (clickable prototype UI; HTML, CSS, JavaScript)
**Status:** Concept renders. Visual values are tuned for these renders and are expected to change as the global aesthetic is refined, as the master spec itself notes.

---

## 1. Purpose and scope

This document describes how the visual concepts in the FamilyOS master specification were translated into procedurally rendered, looping 3D animations. It covers the visual system (colours, materials, motion, layout), the rendering architecture, the specification of every rendered asset, and how to extend or tune the code.

Three areas of the master spec are rendered. The first is the **Avatar Evolution**: all eight life-cycle stages of the master avatar, from The Playful Spark (ages 3–5) to The Warm Solaria (60+). The second is the **Home Screen (Mature Adult view)**: the Quantum Glass Hub core, the five colour-mapped agent satellites, state-driven tension, core status glow and the unified FAB. The third is the **Evolution grid**, which shows all eight stages animating side by side, mirroring the "Avatar Evolution" slide.

The renders are also wired into a **clickable prototype** (Section 12). GIF and PNG files cannot carry links, so the prototype plays the same renders on a canvas and overlays live, clickable hotspots that follow each orbiting item frame by frame. The prototype also implements the Dashboard (Bento grid), the Deep Layer agent screens and the navigation model from the spec as HTML.

---

## 2. Design principles carried over from the spec

The renders follow five principles taken directly from the master specification.

**The Orbital Self.** The user's avatar is the immovable centre of every scene. Everything else (agents, moons, particles, rings) orbits it. No asset places anything other than the avatar at the visual centre.

**OLED-first darkness.** Every scene sits on pure black. To stop the screen feeling dead, each scene adds a faint radial colour tint and a field of slowly drifting, twinkling dust, as the spec describes.

**Communicate state through physics and light, not text.** On the Home Screen, urgency is shown by a satellite pulling closer to the core, vibrating and glowing brighter, while the core's internal glow shifts colour. The status pill is a supporting cue, not the primary one.

**Demographic expression.** The avatar's form, material and motion change with age. Stages move from soft, saturated and playful, through neon and edgy, to dense and technical, and finally to calm, warm and high-contrast for older adults.

**Seamless ambience.** Every animation loops perfectly, so it can sit on a screen indefinitely without a visible restart.

---

## 3. Visual system

### 3.1 Agent colour mapping (Home Screen)

These follow the spec's Home Screen colour mapping exactly.

| Agent | Spec name | RGB (0–1) | Hex | Icon |
|---|---|---|---|---|
| Finance | Deep Teal | 0.12, 0.78, 0.72 | `#1FC7B8` | ₹ glyph |
| Education | Soft Lavender | 0.74, 0.62, 1.00 | `#BD9EFF` | Graduation cap |
| Household | Warm Amber | 1.00, 0.62, 0.20 | `#FF9E33` | House |
| Grocery | Mint Green | 0.42, 0.95, 0.58 | `#6BF294` | Basket |
| Calendar | Sky Blue | 0.38, 0.72, 1.00 | `#61B8FF` | Calendar grid |

### 3.2 Core status colours

| State | Use | RGB (0–1) | Hex |
|---|---|---|---|
| Normal / Calm | Subtle internal glow and halo | 0.30, 1.00, 0.55 | `#4DFF8C` |
| Needs Attention | Warm internal glow and halo | 1.00, 0.62, 0.12 | `#FF9E1F` |
| Alert badge | Badge on the agent in tension | 1.00, 0.35, 0.20 | `#FF5933` |

The renders demonstrate Calm and Needs Attention. The spec's third state, **Critical / Urgent (deep pulsing red)**, is not animated yet. It can be added by passing a red tint and a faster pulse to `quantum_core()` (see Section 10).

### 3.3 Shared accent colours

| Token | RGB (0–1) | Hex | Used in |
|---|---|---|---|
| `MAGENTA` | 1.00, 0.15, 0.78 | `#FF26C7` | Glitch Synth, Kinetic Prism |
| `CYAN` | 0.15, 0.85, 1.00 | `#26D9FF` | Glitch Synth, Kinetic Prism, FAB waveform |
| FAB violet | 0.50, 0.45, 1.00 | `#8073FF` | FAB orb and rings |
| Dust | 0.75, 0.82, 1.00 | `#BFD1FF` | Background particles |

### 3.4 Interface text colours (Home Screen)

| Role | Hex | Size at 1x |
|---|---|---|
| App title "FamilyOS" | `#E1E4EB` | 27 px |
| Pod selector, hints | `#969BA8` | 12 px / 8 px |
| Agent labels | `#C8CDD7` | 9 px |
| Status pill text | Current status colour | 9 px bold |

### 3.5 Typography

The spec recommends Inter, SF Pro or Roboto Flex for adults. The renderer uses **DejaVu Sans** because it is available on almost every system and includes the ₹, ▾, ↑ and ● glyphs the interface needs. The `font()` helper searches common font folders and falls back gracefully. To match the spec, point `_FONT_DIRS` and the font names at an Inter installation.

### 3.6 Materials

All materials are built from a shared set of lighting terms.

| Term | Meaning | Function |
|---|---|---|
| Key light | Top-left-front, direction (−0.55, 0.70, 0.55) | `L_KEY` |
| Fill light | Lower-right, direction (0.65, −0.35, 0.60) | `L_FILL` |
| Diffuse | Lambert shading | `lambert()` |
| Specular | Blinn-Phong highlights | `blinn()` |
| Fresnel | Edges brighten at grazing angles: the core of the glass look | `fresnel()` |
| Iridescence | Cosine rainbow palette, periodic so it loops | `irid()` |

From these, the renderer builds five recurring material families. **Pastel jelly** (Stage 1) is soft iridescence lifted towards white, with a gentle inner glow suggesting subsurface light. **Soap bubble** (Stage 2, floating bubbles) is mostly transparent, with a strong rainbow rim and bright highlights. **Glossy putty-glass** (Stage 3) has solid colour blended between merging blobs, with sharp highlights and a cool rim. **Frosted faceted crystal** (Stage 7, Home core) is a polyhedron with per-facet frost variation, faint facet edges, and a refracted, flowing colour pattern inside. **Warm emissive sphere** (Stage 8) is gold with slow surface bands, a bright rim and a large corona.

### 3.7 Glow and bloom

Every scene finishes with a bloom pass. Bright pixels above a threshold (0.55–0.70) are blurred and added back. Orbit lines and wireframes are drawn on separate emission layers that receive their own soft glow. Satellites carry a small halo. Together these give the luminous, "lit from within" quality of the reference mockups.

---

## 4. Motion system

### 4.1 Seamless looping

Every animation is driven by a single phase value `t` that runs from 0 to 2π across the loop. Every moving quantity is a function of `t` with a **whole-number frequency** (for example `sin(t)`, `sin(3t)`, or a rotation of `t`). This guarantees that the last frame flows back into the first with no jump.

When adding motion, never use a fractional multiple of `t` (such as `0.7 * t`), or the loop will visibly snap.

### 4.2 Motion vocabulary by stage

| Stage | Motion character |
|---|---|
| 1 Playful Spark | Bounce with squash-and-stretch, surface wobble, twinkling sparkles |
| 2 Adventure Pod | Lobes circling and breathing, bubbles drifting in both directions |
| 3 Bio-Kinetic Catalyst | Blobs orbiting, merging and separating; beads circling on rings |
| 4 Glitch Synth | Spinning ring, shards pulsing to a 4-beat, periodic glitch bursts |
| 5 Kinetic Prism | Outer and inner wireframes counter-rotating, spikes pulsing on a beat |
| 6 Digital Oasis | Colour swirl rotating, satellites at 2× and 3× speed |
| 7 Quantum Glass Hub | Crystal rotating once per loop, interior flowing, satellites orbiting |
| 8 Warm Solaria | Slow breathing pulse, slow moons; deliberately the calmest motion |

This progression follows the spec: playful and bouncy for children, energetic and audio-reactive for teens, fast and technical for young adults, rich but composed for mature adults, and slow with high-contrast orbits for older adults.

### 4.3 Home Screen tension curve

The Home Screen loop tells a short story: calm, then a calendar conflict appears, then it resolves. A single tension value `T` (0 = calm, 1 = full tension) controls everything:

```
T = smoothstep( clip( 1.7 × (0.5 − 0.5·cos t) − 0.35, 0, 1 ) )
```

This holds calm at the start and end of the loop and plateaus at full tension in the middle. `T` drives the following:

| Effect | Calm (T = 0) | Tension (T = 1) |
|---|---|---|
| Calendar orbit radius | 1.28 | 0.98 (pulls in by 0.30) |
| Calendar vibration | None | ±0.035 rad at 13 cycles/loop, ±0.02 radius at 17 cycles/loop |
| Calendar glow strength | 0.7 | 2.3 |
| Calendar badge | Sky blue | Alert orange-red, pulsing in size |
| Core interior tint | Green, 22% mix | Amber, 67% mix |
| Core halo | Green, faint | Amber, stronger |
| Status pill | "CORE ● CALM" | "CORE ● NEEDS ATTENTION" (switches at T > 0.5) |

All other agents drift gently (±0.10 rad) so the scene never freezes.

---

## 5. Rendering architecture

### 5.1 Camera and coordinates

The camera sits at (0, 0, 4) looking towards −Z, with a focal length of 2.6. In world units, the visible half-height at the centre plane is about 1.54. Avatar bodies have a radius of around 0.7–0.9 and orbits around 1.0–1.4, so everything fits in frame with breathing room. Positive Z points towards the viewer; this matters for depth ordering (Section 5.3).

### 5.2 Ray-marched bodies (signed distance fields)

Each avatar body is described as a **signed distance field (SDF)**: a function that returns how far any point is from the surface. A sphere-tracing ray-marcher (`render_body()`) fires one ray per pixel and steps along it until it reaches the surface. Surface normals are taken from the gradient of the SDF.

Two optimisations keep this fast in pure NumPy. Rays are first intersected with a bounding sphere, so only pixels that could hit the body are marched, and each march begins at the sphere's entry point. Rays that have already hit or exited are dropped from the working set every step, so later steps process far fewer rays.

Shapes are built with a small set of SDF operations:

| Shape | How it is built |
|---|---|
| Jelly blob (Stage 1) | Ellipsoid plus a sine-wave wobble |
| Bubble cluster (Stage 2) | Spheres fused with a smooth minimum (metaball blending) |
| Merging blobs (Stage 3) | Five spheres fused with a tighter smooth minimum |
| Neon core and ring (Stage 4) | Sphere combined with a torus |
| Ghost body (Stage 5) | Icosahedron from its 20 face planes |
| Glass sphere (Stages 6, 8) | Plain sphere |
| Faceted crystal (Stage 7, Home) | Intersection of 150 planes whose normals are spread evenly over a sphere, slightly jittered |

Each body is paired with a **shade function** that receives the hit position, surface normal and view direction, and returns colour and opacity. Opacity below 1 lets transparent bodies such as bubbles show what is behind them.

### 5.3 Compositing order and depth

Orbits, satellites, shards and particles are not ray-marched. They are drawn as 2D primitives positioned by 3D projection. To make them pass correctly behind and in front of the body, every element is split by depth: anything with Z ≤ 0 is behind the body's centre plane and is drawn first; anything with Z > 0 is drawn after.

Because all orbits are larger than the body they circle, this simple split is always correct: any orbit point in front of the centre plane is also in front of the body's surface. Each frame is assembled in this order:

1. Background (black, radial tint, drifting dust)
2. Back emission layer (rear halves of orbits, rear shards), with glow
3. Back sprites (satellites behind the body), drawn far to near
4. Ray-marched body
5. Front emission layer (front halves of orbits, front shards), with glow
6. Front sprites (satellites in front), drawn far to near
7. Bloom
8. Optional pixel effects (the Stage 4 glitch)
9. Optional overlay drawing (the Stage 1 face; Home Screen text, icons and badges)
10. Downsample to final size

### 5.4 Sprites

Satellites, moons and floating bubbles are drawn by `orb_px()` as shaded discs that imitate small spheres. Three styles are available. **Glass** has a dark centre, a bright coloured rim, an inner glow and two highlights; it is used for agents and most satellites. **Bubble** is mostly transparent with a rainbow rim. **Solid** is lit like an opaque ball and is used for beads and Solaria's moons. Each can carry a soft additive halo.

### 5.5 Anti-aliasing

Everything is rendered at 2× resolution (`SS = 2`) and reduced with a Lanczos filter at the end. This smooths silhouettes, thin orbit lines and text without needing anti-aliased drawing primitives.

### 5.6 GIF encoding

GIF frames are limited to 256 colours. If each frame chose its own palette, the background and gradients would flicker. `save_gif()` instead builds one palette from a sample of frames spread across the loop, then converts every frame to that shared palette with Floyd–Steinberg dithering. Frames use a fixed duration and loop forever.

---

## 6. Avatar stage specifications

Each stage is a function `stageN(t, size)` that returns one frame. The table gives the essentials; the subsections note design intent.

| # | Name | Ages | Body | Satellites and extras | Bloom threshold |
|---|---|---|---|---|---|
| 1 | The Playful Spark | 3–5 | Wobbling jelly ellipsoid | Smiling face, 7 sparkles, floor glow | 0.70 |
| 2 | The Adventure Pod | 6–8 | Central bubble + 4 fused lobes | 10 floating bubbles, inner sparkle motes | 0.65 |
| 3 | The Bio-Kinetic Catalyst | 9–12 | 5 fused coloured blobs | 2 rings, 10 coloured beads | 0.65 |
| 4 | The Glitch Synth | 13–15 | Dark sphere + neon torus | 18 shards, 26 debris particles, glitch | 0.55 |
| 5 | The Kinetic Prism | 16–18 | Faint icosahedron | Outer and inner wireframes, 20 spike tips | 0.55 |
| 6 | The Digital Oasis | 19–25 | Iridescent glass sphere | 2 rings, 4 fast satellites | 0.60 |
| 7 | The Quantum Glass Hub | 26–59 | 150-facet frosted crystal | 5 orbits, 5 glass satellites | 0.65 |
| 8 | The Warm Solaria | 60+ | Golden sphere | Corona, 2 thick rings, 2 moons | 0.70 |

**Stage 1 — The Playful Spark.** The spec asks for "pure joy" and a friendly face. The blob bounces twice per loop and squashes as it lands. The face (closed happy eyes, a smile and pink cheeks) is projected onto the blob's front surface so it moves and squashes with the body.

**Stage 2 — The Adventure Pod.** Four smaller lobes circle the main bubble in alternating directions, fused smoothly so they look like one soft cluster. The material is mostly transparent so the cluster feels like "bouncy water".

**Stage 3 — The Bio-Kinetic Catalyst.** The face is dropped, as the spec requires for pre-teens. Five coloured blobs (`#FF8C26`, `#FF479E`, `#26CCFF`, `#8CFF4D`, `#9461FF`) orbit and merge, with each surface point coloured by its nearest blobs. Ringed beads give the "virtual pet with orbiting particles" feel.

**Stage 4 — The Glitch Synth.** Acid magenta and cyber blue, as specified. The core has coloured rim lighting and scrolling scan bands. Shards burst outward and pulse on a four-beat rhythm to suggest audio reactivity. A glitch pass always offsets the red and blue channels slightly, and three times per loop it intensifies with sliced, shifted bands. Faint scanlines are always present.

**Stage 5 — The Kinetic Prism.** "Faceted glass with intense glowing wires." A faint glass icosahedron is wrapped in a glowing wireframe, with a smaller counter-rotating wireframe inside and spokes linking the two. Each face has a spike that extends on its own beat. Lines are coloured by height between cyan and magenta and dimmed with distance.

**Stage 6 — The Digital Oasis.** Symmetrical, fluid and iridescent. The colour pattern swirls around the sphere's axis, and two thin rings carry satellites at twice and three times the base speed.

**Stage 7 — The Quantum Glass Hub.** "Your masterpiece." The 150-facet crystal has slight per-facet frost variation and faint edges. Inside, a flowing three-wave colour pattern is sampled along a direction bent by each facet's normal, so every facet shows a slightly different slice. This imitates refraction and makes the interior look alive. Five satellites (`#40F2CC`, `#C78CFF`, `#FF992E`, `#59A6FF`, `#73F273`) orbit on separate tilted paths.

**Stage 8 — The Warm Solaria.** Zero clutter, high visibility, slow motion. A golden sphere breathes once per loop with gentle surface bands, a bright rim and a large warm corona. Two deliberately thick rings carry two moons that each orbit just once per loop. Background dust is reduced (90 particles instead of 170–220) to keep the scene calm.

---

## 7. Home Screen specification (Mature Adult view)

### 7.1 Layout

The canvas is 360 × 640 px at 1× (rendered at 720 × 1280). The core is centred at (180, 300) with a projection scale of 190, which gives the core a diameter of roughly 180 px, close to the reference mockup.

| Element | Position (1×) | Notes |
|---|---|---|
| Title "FamilyOS" | Centre, y = 52 | 27 px |
| Pod selector "Active Pod - Mahesh ▾" | Centre, y = 80 | 12 px |
| Core status pill | Centre, y = 98–116 | Tinted fill and outline in status colour |
| Core (Quantum Glass Hub) | (180, 300) | Radius 0.72 world units |
| Agent orbit | Around core | Radius 1.28, plane tilt `ax = 1.15`, `ay = 0.22` |
| "↑ SWIPE UP FOR DASHBOARD" | Centre, y = 506 | 8 px hint |
| FAB | (180, 566), radius 34 | Glass orb, mic glyph, 3 expanding rings, waveform bars |
| "TAP TO CHAT • HOLD TO LISTEN" | Centre, y = 618 | 8 px hint |

### 7.2 Agent placement

Agents sit on one tilted orbit, which keeps them evenly spread around the core like the mockup while still giving real depth.

| Agent | Screen angle | Badge | Label position |
|---|---|---|---|
| Finance | 152° (upper left) | Yes | Above |
| Education | 42° (upper right) | Yes | Above |
| Household | −6° (right) | No | Below |
| Grocery | −50° (lower right) | No | Below |
| Calendar | −142° (lower left) | Yes | Below |

Labels for agents in the upper half sit above the orb, so they never collide with the core. Each agent has a short tether line from the core towards it, a nod to the spec's "organic fluid branches" fused to the core. Two additional faint orbit paths at different tilts add depth.

### 7.3 Interaction cues shown

The FAB uses the label from the reference mockup: "Tap to chat • Hold to listen". It shows three rings expanding outwards twice per loop and a two-sided waveform whose bars rise and fall, signalling that voice is available.

---

## 8. Output specification

| Asset | File | Size | Frames | Frame time | Loop length |
|---|---|---|---|---|---|
| Stage 1–8 avatars | `stageN_<name>.gif` | 320 × 320 | 36 | 70 ms | 2.5 s |
| Stage stills | `stageN_<name>.png` | 320 × 320 | 1 | — | — |
| Evolution grid | `avatar_evolution_grid.gif` | 960 × 584 | 36 | 70 ms | 2.5 s |
| Evolution grid still | `avatar_evolution_grid.png` | 960 × 584 | 1 | — | — |
| Home Screen | `home_screen_mature_adult.gif` | 360 × 640 | 48 | 80 ms | 3.8 s |
| Home stills | `home_screen_calm.png`, `home_screen_needs_attention.png` | 360 × 640 | 1 | — | — |
| Clickable prototype | `familyos_prototype.html` | 360 × 640 screen (rendered at 540 × 960) | 40 per stage × 8 stages | 80 ms | 3.2 s |

The grid uses 240 px tiles in a 4 × 2 layout, each with a 52 px header showing "STAGE n: AGE x–y" and the stage name, matching the evolution slide in the spec.

---

## 9. Running the renderer

Install the two dependencies with `pip install numpy pillow`, then:

```
python familyos_3d.py                         # everything → ./familyos_output (~2 min)
python familyos_3d.py --only home             # Home Screen only
python familyos_3d.py --only 4                # one avatar stage
python familyos_3d.py --only grid             # all stages + grid
python familyos_3d.py --frames 24 --size 256  # faster, smaller preview
python familyos_3d.py --size 512              # larger avatars
python familyos_3d.py --only proto             # rebuild just the clickable prototype
python familyos_3d.py --only gifs              # GIFs and PNGs only, no prototype
```

The prototype build reads `familyos_prototype_template.html` from the same folder as the script (override with `--template`).

| Option | Default | Effect |
|---|---|---|
| `--out` | `familyos_output` | Output folder |
| `--frames` | 36 | Frames per avatar loop (smoothness vs. file size) |
| `--home-frames` | 48 | Frames in the Home Screen loop |
| `--size` | 320 | Avatar GIF size in pixels |
| `--only` | `all` | `all`, `gifs`, `home`, `grid`, `proto` or a stage number 1–8 |
| `--proto-frames` | 40 | Frames per Home Screen loop in the prototype |
| `--proto-scale` | 1.5 | Prototype render scale (1.5 = 540 × 960, sharper on high-density screens) |
| `--proto-quality` | 72 | WebP quality of prototype frames |

Measured on a single CPU core, the full set takes about two minutes. The Home Screen is the slowest asset (about 46 s) because of its larger canvas and the 150-plane crystal; Stage 7 takes about 19 s for the same reason. All other stages take 4–8 s.

---

## 10. Extending and tuning

**Changing colours.** Agent colours live in the `AGENTS` list; stage palettes live inside each stage function or in the shared constants (`MAGENTA`, `CYAN`, `S3_COLS`, `S7_SATS`). Values are RGB in the 0–1 range.

**Adding the Critical (red) state.** In `home_screen()`, extend the status colour blend with a third colour such as `(1.0, 0.15, 0.15)`, and add a faster pulse to the core halo (for example multiplying its strength by `0.7 + 0.3·sin(4t)`). Pass the result to `quantum_core()` as `tint`.

**Putting a different agent under tension.** In `home_screen()`, change the `tense = name == "CALENDAR"` check to another agent name.

**Adding a new avatar stage.** Write a function `stageN(t, size)` that follows the same pattern: create a canvas, draw the background, collect orbits into the back and front layers, collect sprites, render the body with an SDF and shade function, then call `finalize()`. Add it to the `STAGES` list and it will appear in the CLI and the grid. Keep all motion on whole-number multiples of `t`.

**Making the crystal finer or coarser.** Change the first argument of `fib_sphere(150, …)` for `FACETS`. More facets look smoother but render more slowly.

**Higher quality output.** Raise `SS` to 3 for smoother edges (roughly doubling render time), or increase `--frames` for smoother motion. For video or web use, the PNG frames can be exported instead of GIF to avoid the 256-colour limit.

---

## 11. Known gaps and open questions for the spec

**Not yet built.** Orbital notification orbs that snap into orbit and expand into modals, the Critical (red) core state, and the demographic layouts beyond the avatar itself: the older-adult centred alert card and low-density dashboard, and the teen "Allowance/Budget" dashboard. In the prototype every family member currently sees the same pod data and the adult Bento grid.

**Font.** The renders use DejaVu Sans as a portable stand-in for Inter / SF Pro.

**FAB behaviour is contradictory in the spec.** The "Global Aesthetics" section says a tap gives a spoken summary and a long press opens chat. The "Unified Interaction Layer" section and the mockups say the reverse: tap to chat, hold to listen. The renders follow the mockups. This should be settled in the master spec.

**Agent colours differ between sections of the spec.** The Home Screen section maps Finance to Deep Teal, while the Typography section maps the Financial agent to Deep Blue and introduces Emerald for Health and Amber for an Emotional agent. The renders use the Home Screen mapping. The spec should also clarify whether Health appears on the Home Screen, since it is in the Dashboard but not among the "5 core agents".

**Reference imagery.** The mockups in the spec are photorealistic AI-generated images. These renders are stylised, code-generated approximations intended to show form, colour and motion, not to match the reference images pixel for pixel.

---

## 12. Clickable prototype

### 12.1 Why a prototype instead of clickable GIFs

GIF and PNG are image formats with no way to store links or hotspots, and the items in these renders move every frame, so even an HTML image map over a GIF would miss its targets. The prototype solves both: it plays the rendered frames on a canvas and keeps a live, invisible button over every item, repositioned on every frame from coordinates exported by the renderer.

### 12.2 How hotspots stay aligned

`home_screen()` returns, alongside each frame, a small metadata record in 360 × 640 layout pixels: the centre and radius of each of the five agents, the avatar core, the FAB, and the frame's tension value `T`. The prototype frames are rendered **without** burned-in text (`with_text=False`); titles, labels, badges and the status pill are live HTML instead, positioned from the same metadata. As a result labels stay crisp at any scale, the Calendar badge turns to the alert colour exactly when the core turns amber (`T > 0.5`), and labels above the core's centre line sit above their orb.

Each avatar stage can now also render as a Home Screen core. Every stage function accepts `cv` (draw into an existing canvas) and `decor` (set to `False` to drop the stage's own rings and satellites so they don't clash with the agent orbit). `HOME_CFG` sets the projection scale and agent-orbit radius per stage so larger avatars still fit, and `ORBIT_STYLE` gives some stages a distinctive agent track, such as the thick amber track for The Warm Solaria.

### 12.3 What is clickable

| Item | Action |
|---|---|
| Each agent orb (Finance, Education, Household, Grocery, Calendar) | Opens the dashboard sheet directly on that agent's Deep Layer screen; back returns to the dashboard |
| Avatar core | Opens an avatar card: stage, age range, member and the spec's description, with Switch family member and Edit details |
| "Active Pod - Name ▾" | Family member menu (the only member switcher); choosing one swaps the core to that member's avatar. Its footer opens Family details (with a count of sections to update) and Log out |
| "↑ Swipe up for dashboard" or dragging up / scrolling on the home screen | Opens the 90% dashboard sheet |
| Dashboard cards (Finance, Calendar clash, Education, Household, Health, Grocery) | Push the agent's Deep Layer screen in from the right |
| Back arrow, or a swipe from the sheet's left edge | Back one layer |
| Grid icon (top right of the sheet) | Straight back to the dashboard root |
| The exposed top strip, or a tap / drag down on the handle | Collapses the sheet and returns home |
| FAB tap (or Enter / Space) | Opens chat with quick actions; typed questions are routed to the matching agent |
| FAB press and hold (450 ms) | Spoken daily summary using the browser's speech synthesis, with on-screen text |
| Deep Layer "Ask … anything" field | Adds your question and the agent's answer to the top of its timeline |
| Deep Layer action button (Transfer funds, Send proposal, Approve cart …) | Confirms with a toast |
| Escape key | Closes the open overlay, otherwise goes back one layer |
| P key | Pauses or resumes the animation (hotspots keep working while paused) |

### 12.4 Family pod used in the prototype

| Stage | Member | Age |
|---|---|---|
| 1 The Playful Spark | Myra | 4 |
| 2 The Adventure Pod | Ishaan | 7 |
| 3 The Bio-Kinetic Catalyst | Diya | 11 |
| 4 The Glitch Synth | Aarav | 14 |
| 5 The Kinetic Prism | Kabir | 17 |
| 6 The Digital Oasis | Riya | 22 |
| 7 The Quantum Glass Hub | Mahesh | 42 (default) |
| 8 The Warm Solaria | Kamala | 68 |

Members are chosen from the Active Pod dropdown, which shows each person's avatar, name, age and stage. Mahesh, Aarav and Diya come from the spec's mockups; the other members were added so every stage has an owner. The spoken summary changes tone by age group (children, teens, adults, older adults, with slower speech for 60+).

### 12.5 Deep Layer screens

Each agent screen follows the spec's Deep Layer layout: a hero metric in the top 30% in large type, a supporting chart (sparkline, day timeline with the clash highlighted, progress bars, task ring or item chips), a stats row, then a scrollable timeline of **agent reasoning logs**, each with a "Why" line explaining the decision. A contextual action button sits at the bottom right and an "Ask … anything" bar sits at the bottom. The content is taken from the spec mockups where it exists (₹3,45,850 projected reserve, the Aarav coaching downgrade, the 14:00–15:30 calendar clash, the 14-item BigBasket cart, 84% bio-harmony) and extended consistently elsewhere.

### 12.6 Prototype visual rules

The phone screen is always OLED black, whatever the viewer's theme. Sheets and dialogs use dark frosted glass (26 px backdrop blur, 1 px white border at 12% opacity). Type is Inter, as the spec recommends, falling back to the system sans-serif. Agent colours come from Section 3.1, with Health in `#FF6B9A`. The page shows only the phone: no side panel or extra content. The phone is centred and scaled to fit the browser window (between 0.3× and 1.4× of its 384 × 664 px frame; the renders are 1.5× resolution, so they stay sharp when enlarged). The background around the phone follows the viewer's light or dark setting. Motion respects the reduced-motion preference: the render is paused on its first frame, the P key resumes it, and all hotspots stay clickable.

### 12.7 Limits

All data is illustrative and nothing is saved: everything entered during sign-up and in the family details screens lives only in memory and is cleared on refresh. Chat replies are canned answers chosen by keyword, not a live AI model. Speech uses the browser's built-in voice, which varies by device. The single HTML file contains every render (about 8–10 MB), so it can take a moment to load on slow connections.

---

## 13. Account and family onboarding screens

### 13.1 Flow

```
Loading ──► Log in ──────────────────────────────► Loading ──► Home
               │  └─► One-time code ──────────────┘
               └─► Sign up ──► One-time code ──► Family pod (setup)
                                                   │   ▲
                                     Add member ───┘   │
                                     Member details ───┘ (5 sections + review)
                                                   └─► Finish setup ──► Loading ──► Home
Home ──► Active Pod ▾ ──► Family details ──► Family pod (manage) ──► Member details
Home ──► Avatar core ──► Edit details ──► Member details ──► Home
Home ──► Active Pod ▾ ──► Log out ──► Log in
```

All onboarding screens are full-screen "routes" that sit above the Home Screen inside the same phone frame. They share the visual language of the rest of the prototype: OLED black with a faint violet glow from the top and a teal glow from the bottom, slowly drifting dust, frosted-glass inputs with a 1 px border, Inter type, and the voice button's violet (`#8073FF`) as the primary action colour. In the member details wizard the primary colour follows the current section, so the screen visibly changes as you move through it.

### 13.2 Loading screen

Shown when the app opens, after logging in, and after finishing setup. The active member's avatar sits in the centre with the five agent colours orbiting it as glowing dots on a faint ring. Below are the FamilyOS wordmark, a status line that steps through messages ("Waking up your agents", "Syncing the family calendar", "Building Mahesh's home") and a thin progress bar using the agent colours in sequence. Loading takes about 2.6 seconds and exposes progress to assistive technology.

### 13.3 Log in

Email or mobile and password (with show/hide), "Keep me logged in", "Forgot password?" (confirms with a toast), a primary Log in button, "Log in with a one-time code", and a link to create an account. A small note states that any credentials work in the prototype. Logging in loads the sample Rao family pod (Section 13.8).

### 13.4 Sign up and one-time code

Sign up collects full name, email, mobile (+91), date of birth, password with a four-step strength meter, an optional pod name, and agreement to the terms. Each field is validated with a plain message under it, and errors clear as soon as the field is corrected. The pod owner must be 18 or older. Creating the account goes to a one-time-code screen: six digit boxes with auto-advance, backspace to the previous box, paste support, a 30-second resend timer and a link to change the number. Any six digits work in the prototype. Verifying creates the owner's profile (relationship "Self", with mobile and email already filled in) and opens the family pod in setup mode.

### 13.5 Family pod hub

A summary card shows overall completion as a ring and "N of M profiles complete, K sections still need updating". Below, every member has a card with their avatar (chosen by age), relationship, age, stage name, a completion ring, and an amber tag for each section that needs updating (or a green "All details up to date"). Tapping a card opens that member's details at their first incomplete section. "Add family member" asks for name, relationship and date of birth, then opens the details wizard; the avatar is assigned from the age straight away.

In setup mode the footer button is "Finish setup" and there is no back button. In manage mode (from the Active Pod menu) the footer says "Done" and a back button returns home.

### 13.6 Member details wizard

A header shows the member's avatar and name and the current step. Below it, a six-segment progress bar uses each section's colour; completed sections stay tinted, skipped ones turn amber, and every segment is tappable to jump straight there. The footer offers "Skip for now" (the section is flagged as needing an update) and "Save and continue", which validates the section first and scrolls to the first problem. The close button saves and exits at any point. Each section opens with an icon, a title and one sentence on which agents use the information and why.

| Section | Colour | Adults (18+) | Children and teens |
|---|---|---|---|
| Basic information | `#61B8FF` | Full name*, preferred name, relationship*, date of birth*, gender*, occupation, languages, profile photo | School and grade instead of occupation |
| Contact and address | `#6BF294` | Mobile*, email*, "lives at the same address as you", address line*, area, city*, PIN code*, state* | Mobile optional under 13, email optional under 18 |
| Government ID and documents | `#BD9EFF` | Aadhaar*, PAN*, voter ID, passport and expiry, driving licence, document uploads (Aadhaar, PAN, passport, licence), authorisation* | Aadhaar*, passport; uploads for Aadhaar, birth certificate, school ID, passport |
| Health | `#FF6B9A` | Blood group*, weight, allergies, ongoing conditions, current medicines (name, dose, when), family doctor, insurer, policy number, emergency contact name* and mobile* | Adds "Vaccinations up to date" |
| Banking and payments | `#1FC7B8` | Bank*, account holder*, account number*, IFSC*, UPI ID, saved cards (nickname, network, last 4 only), auto-pay permissions, approval limit | Becomes **Allowance and payments**: weekly allowance, paid from (an adult)*, UPI ID (13+), approval threshold, blocked categories |

\* required for the section to count as complete.

Formats are checked for mobile numbers (10 digits starting 6–9), PIN codes (6 digits), Aadhaar (12 digits), PAN (`ABCDE1234F`), IFSC (`HDFC0001234`), passport (`A1234567`), UPI IDs (`name@bank`) and card last-4. Dates of birth can't be in the future and passport expiry can't be in the past. Letters in ID fields are upper-cased as you type. Aadhaar, account and policy numbers are masked whenever the field isn't focused (`XXXX XXXX 0193`, `••••••••6789`). Saved cards only ever take the last four digits. Changing a date of birth immediately updates the member's age, avatar and age-dependent fields.

Sections holding sensitive data (IDs, health, banking) show a dashed note that, in this prototype, details stay in the browser tab and are cleared on refresh. A production build would replace this with the real storage and sharing policy.

The final step is a review screen listing every section with a Complete or Needs update badge, a short masked summary, and an Edit link.

### 13.7 Connections to the Home Screen

The Active Pod menu is built from the live pod, so newly added members appear there with their avatar, relationship and stage, and selecting one switches the Home Screen core. The menu footer adds Family details (with the number of sections to update) and Log out. The avatar card gains an Edit details button that opens the active member's wizard and returns home afterwards.

### 13.8 Sample pod (demo login)

| Member | Relationship | Age | Stage | Sections needing update |
|---|---|---|---|---|
| Mahesh | Self | 42 | 7 | None |
| Priya | Spouse | 39 | 7 | Banking |
| Kamala | Mother | 68 | 8 | IDs & documents, Banking |
| Riya | Niece | 22 | 6 | Health, Banking |
| Kabir | Nephew | 17 | 5 | Contact |
| Aarav | Son | 14 | 4 | IDs & documents |
| Diya | Daughter | 11 | 3 | None |
| Ishaan | Son | 7 | 2 | None |
| Myra | Daughter | 4 | 1 | Health |

All personal numbers in the sample pod are made up. The pod deliberately mixes complete and incomplete profiles so the amber "needs update" states are visible straight after logging in.
