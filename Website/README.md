# Morph — website

The public marketing landing page. This is a **standalone** Vite + React +
TypeScript site — it does not share code, routing, or a build with
`frontend/` (the product app). Nothing here touches, imports from, or is
imported by `frontend/`.

## Run it

```
cd Website
npm install
npm run dev
```

## What it is

A single continuous scroll-driven camera flight (GSAP ScrollTrigger + Lenis,
`react-three-fiber`) through two computers — see `LANDING_PAGE_PROMPT.md` in
this directory for the full storyboard spec this was built against.

- `src/landing/Landing.tsx` — page shell: the pinned journey, the scroll-progress
  wiring, the products section, the footer.
- `src/landing/Journey3D.tsx` — the procedural 3D scene (motherboard, chips,
  CPU, RAM, storage, the two monitors) and the camera keyframe path.
- `src/landing/JourneyStill.tsx` — the `prefers-reduced-motion` fallback (and
  what renders if WebGL throws): a static editorial list, no 3D/GSAP/Lenis
  loaded.
- `src/landing/scenes.ts` — the scene labels and the four annotation copy
  blocks (CPU/cgroups, memory/OOM-killer, locale, rlimits), in one place so
  timing and text stay in sync.
- `src/landing/flight.ts` — shared, non-reactive per-frame state (`progress`,
  `morph`, `glow`) so 3D meshes can ease toward it in their own `useFrame`
  without going through React state.
- `src/landing/useJourneyScroll.ts` — Lenis + ScrollTrigger + a critical-damp
  pass that turns scroll position into that one smoothed `progress` number.
  `?static` in the URL disables Lenis for deterministic automated screenshots.
- `src/landing/landing.css` — the wine/burgundy palette, Instrument Serif +
  JetBrains Mono type, and all layout.
- `public/wallpapers/` — copied from `frontend/public/wallpapers/` for the two
  on-screen OS shots (color-graded toward the palette in the 3D material, not
  used verbatim).
- `scripts/shots.mjs` — a small Playwright screenshot helper used to review
  the scroll journey during development: `node scripts/shots.mjs 0 200 400 600 800`
  (values are scroll position in vh) writes PNGs to `SHOT_DIR` (default
  `/tmp/morph-shots`).

## Verification

```
npx tsc -b        # typecheck
npm run lint       # oxlint
npm run build      # production build
```

All three are clean as of this commit.
