# Morph Landing Page — Setup + Build Prompt

## Part 1 — What to install / invoke BEFORE running the prompt

### 1. Install the Anthropic skills marketplace (once, in your terminal)

```
claude plugin marketplace add anthropics/skills
```

Then inside Claude Code:

```
/plugin install frontend-design
/plugin install webapp-testing
```

- **`frontend-design`** — Anthropic's skill for building distinctive, non-generic web UIs. This is the single most important one for "should not feel AI generated."
- **`webapp-testing`** — drives Playwright (already in your `frontend/package.json` devDeps) so the model can screenshot the page at multiple scroll positions and self-critique visually. Design-track work without a screenshot loop is guessing.

### 2. Skills already available in your session — tell the model to invoke them

- **`/run`** — to launch `npm run dev` in `frontend/` and keep it running while iterating.
- **`claude-in-chrome`** (if you use the Chrome extension) — alternative to Playwright for live visual iteration with real scroll physics.

### 3. Dependencies the model will need to add (mention them so it doesn't reinvent)

```
npm i gsap lenis
# only if it chooses the real-3D route:
npm i three @react-three/fiber @react-three/drei
```

### 4. Assets to have ready (or let the model fetch)

- **3D models (GLTF/GLB, CC-licensed):** Sketchfab has free CC-BY motherboard, CPU, RAM stick, NAND/SSD, and open computer case models — search "motherboard gltf", "ssd exploded". Compress with `gltf-transform` / Draco.
- **HDRI lighting:** Poly Haven (free, CC0) — a dim studio HDRI makes chips look cinematic.
- **Fallback route (often better):** pre-rendered image sequences (Apple-style scroll scrub). Render ~120–180 frames from Blender using the same free models, export as WebP, scrub with canvas. Zero WebGL risk, always smooth.
- **Fonts (Google Fonts):** a characterful display face + a mono for the technical callouts. Suggested: **Instrument Serif** or **Space Grotesk** for display, **JetBrains Mono** or **IBM Plex Mono** for annotations. Never Inter-only.
- You already have `frontend/public/wallpapers/` (morph-bg.png etc.) usable for the OS screens.

### 5. Run the prompt with **Opus, extended thinking on**, and say "iterate with screenshots until it looks premium."

---

## Part 2 — The prompt (paste everything below into Opus/Sonnet)

---

You are building the public landing page for **Morph**, an environment-reproduction tool ("Test your software in environments you don't physically have" — read `README.md` at repo root for the product story). This is for a hackathon **design track**; the bar is "wins the design award," not "looks fine." It must feel like a crafted studio site (Apple product pages, Linear, Vercel Ship, active-theory.net) — absolutely not like an AI-generated template.

First, invoke the **frontend-design** skill and follow it. Use the **webapp-testing** skill (Playwright is already installed) to screenshot the page at at least 12 scroll positions after every major change, look at the screenshots, and fix what looks cheap. Use **/run** to keep the dev server alive.

### Where it lives

The repo's frontend is `frontend/` — Vite + React 19 + TypeScript, plain CSS modules-per-component convention (see `src/screens/*.css`), a theme in `src/theme/theme.css`, and an existing app in `App.tsx`. Add the landing page as the default route (`/`) and move the existing app behind `/app` (introduce a tiny router or conditional render — do not break the existing screens). Landing page code goes in `src/landing/`. Match the repo's code conventions.

### The core experience: one continuous cinematic scroll journey

The entire top of the page is a single scroll-driven "camera flight" through two computers. The user's scroll is the timeline scrubber. Use **GSAP ScrollTrigger with pinning + `scrub`**, and **Lenis** for smoothed scroll. Choose ONE rendering approach and commit:

- **Option A (preferred for reliability): pre-rendered image-sequence scrub.** Render/obtain a frame sequence of the camera journey (CC-licensed GLTF models from Sketchfab rendered in code or sourced as frames), draw to a full-viewport `<canvas>`, map scroll progress → frame index. This is how Apple does it. Overlay all text/annotations as DOM synced to the same ScrollTrigger.
- **Option B: real-time Three.js (react-three-fiber + drei)** with Draco-compressed GLB models and a Poly Haven HDRI. Only if you can keep it at 60fps and it genuinely looks better than A. If models are hard to source, build **stylized geometry in code** — a deliberately abstract, beautiful "schematic 3D" motherboard (emissive traces, extruded chips, glass dielectric) can look MORE premium than a mediocre photoreal model. An intentional art direction beats a bad photoreal one.

Either way: the camera never cuts — it flies. Ease everything; nothing snaps.

### Scene-by-scene storyboard (scroll order)

1. **Scene 0 — Hero.** A computer (desktop/laptop) facing us, screen ON, showing a recognizable OS desktop (use `public/wallpapers/` images as the screen content). Overlay: the word **MORPH** huge, plus one line: "Test your software in environments you don't physically have." Subtle scroll cue.
2. **Scene 1 — Into the machine.** On scroll the camera pushes THROUGH the screen / past the case panel into the interior. Case interior parallax: we glide past **one HDD**, **one RAM stick**, toward **the processor**. Each component gets a fleeting mono-font label with a hairline leader line as we pass (labels fade in/out with scroll).
3. **Scene 2 — The processor, then the silicon.** Camera dives into the processor / across the board to a bank of **NAND chips**, then frames **one single NAND chip**, macro shot. This is the first big annotation stop (see callouts below — the CPU one lives here).
4. **Scene 3 — RAM annotation stop.** Camera slides to the RAM. Second annotation.
5. **Scene 4 — Board chips.** Camera pans across the motherboard; leader lines point at two other (arbitrary) chips for the **locale/timezone** and **process limits** annotations.
6. **Scene 5 — The morph.** Camera pulls back out — and as it does, the hardware **transforms**: the NAND layout rearranges to a different layout, the processor becomes a different processor, the HDD is now an **SSD**, the RAM is different RAM, and we exit into a **different computer** whose screen shows a **different OS** (different wallpaper). This is the money shot — the visual embodiment of the product ("same software, different machine"). A crossfade/morph between two frame-sequences or two model sets, driven by scroll, with a signature moment (e.g., chips gliding into new positions like a k-map).
7. **Scene 6 — Products.** The journey resolves; normal scrolling resumes into the two-product section (below).

### The four technical callouts (exact content, styled as engineering annotations)

Each is a thin leader line from the component to a mono-font annotation card that types/fades in on scroll. Wording (tighten typography, keep meaning):

- **NAND/CPU chip:** "CPU limits tested on cores. Child processes limited via cgroups — frozen by the kernel scheduler when the quota is hit: X ms limit inside a Y ms window."
- **RAM:** "Memory limited by cgroup memory management. Overcommit is policed by the kernel OOM killer."
- **Random board chip #1 (locale/timezone):** "Locale & timezone: retrieved from the target profile and pushed into the sandboxed environment before launch."
- **Random board chip #2 (process limits):** "Threads, file descriptors, max processes — before exec, rlimits are set: RLIMIT_NOFILE & RLIMIT_NPROC (POSIX)."

Annotation cards look like instrument overlays: hairline borders, small caps mono labels, a measurement-tick aesthetic — not generic tooltips.

### Products section (after the journey)

Two large cards/panels, asymmetric layout (not two identical centered boxes):

1. **Solo Dev — "Morph Local".** Open source, completely free. Copy: *"Run it on your own Linux box — or SSH into a Raspberry Pi for the most faithful CPU-level reproduction. Every other condition can be replicated without a Linux environment."* CTA: "Star on GitHub" / "Read the docs".
2. **High-Compute — "Morph Fleet"** (rename allowed; pick something better than "Enterprise" — e.g., Fleet, Grid, or Foundry). Cloud-based infrastructure for teams and heavy matrices: *"Point your app at our cloud workers and sweep hundreds of environment combinations in parallel."* CTA: "Request access".

Below: a short footer (GitHub link, made-at-hackathon credit). Keep total page: hero journey + products + footer. No fake testimonials, no fake logos, no pricing tables.

### Design direction (non-negotiable)

- **Art direction first — WINE palette (required):** the scroll journey plays over a deep reddish-pink / wine background — think dark burgundy-to-oxblood (`#2b060f` → `#4a0e22` range) with a vinous pink glow (`#e0447c`-ish) as the accent, gold PCB-pad tones from the hardware as the secondary warm accent, and off-white/bone text. The background should subtly shift shade as the camera travels (deeper wine inside the machine, brighter rosé glow at the morph moment) so the scroll itself feels lit. No purple-gradient-on-white SaaS look, no glassmorphism cards, no emoji.
- **Typography is the design:** display font (Instrument Serif or Space Grotesk, from Google Fonts) at genuinely large sizes with tight leading; JetBrains Mono / IBM Plex Mono for every annotation, label, and number. Real typographic scale, generous whitespace, deliberate asymmetry.
- **Motion rules:** everything scroll-scrubbed in the journey (reversible — scrolling up rewinds the camera); entrances elsewhere use one consistent easing; respect `prefers-reduced-motion` with a static, still-beautiful fallback (key frames as stills with the annotations laid out editorially).
- **Details that read as human:** film-grain/noise overlay at low opacity, hairline rules, tick marks, frame-counter or scroll-progress indicator styled like a camera HUD, custom cursor optional. Kill all default box-shadows.
- **Performance:** lazy-load the sequence frames progressively, `will-change` sparingly, target 60fps scroll; test at 1440px, 1024px and 390px widths. On mobile, the journey may simplify (fewer frames, larger annotations) but must not break.

### Process requirements

1. Read `README.md` and skim `frontend/src` conventions first.
2. Build the skeleton (routes, Lenis, pinned ScrollTrigger timeline with placeholder gradient frames) and verify the scrub mechanic with screenshots BEFORE investing in visuals.
3. Source/generate the visual assets (state the license of anything downloaded).
4. Then iterate: screenshot at 12+ scroll positions each pass, critique honestly ("does this look like a template?"), and refine at least 3 passes.
5. `npm run build` must pass (`tsc -b` is strict) and `npm run lint` clean.

Do not ask for approval between steps — build it end to end, then present a scroll-through summary with screenshots.
