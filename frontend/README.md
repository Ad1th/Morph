# Morph dashboard

The browser UI for Morph: connect a project, set a target environment, run it
once, isolate which condition causes a failure, find the threshold where it
begins, and keep the verdict as a regression.

## Run it

```sh
# backend (from the repo root)
.venv/bin/python -m uvicorn morph.api.app:app --port 8000

# frontend
cd frontend
npm install
npm run dev            # http://localhost:5173/app
```

The dev server proxies `/api/*` and `/ws/*` to the backend on port 8000. Set
`MORPH_API_PORT=8010` to point it at a backend on another port.

`npm run build` type-checks (`tsc -b`) and bundles; `npx oxlint src` lints.

## Layout

```
src/
  main.tsx              mounts <App/>; a landing page can claim "/" here later
  routes.ts             screen table + hand-rolled history router (useRoute)
  App.tsx               shell: rail, top bar (server status, run target, theme)
  theme/tokens.css      design tokens, dark-first; light under [data-theme=light]
  theme/base.css        reset, type, buttons/chips/fields/tables, reduced motion
  state/store.ts        one persisted store (localStorage) read via useStore()
  state/useRunDraft.ts  the run draft: project, command, host + target profile, presets
  hooks/useJobStream.ts WebSocket subscriber with reconnect + replay
  hooks/useGithubAuth.ts GitHub device flow; the token never touches storage
  api/client.ts         fetch wrapper; backend {"detail"} unwrapped into ApiError
  api/types.ts          mirrors morph/schema/*.py
  lib/format.ts         p-values (7.4×10⁻⁷), rates, ms, MiB/GiB
  lib/summary.ts        the one shared profile summary formatter
  components/           Rail, TargetSelect, ParameterRow, ParamGroup, ui/*, charts/*
  screens/              Projects, Run, Experiment, Threshold, Regressions, Environment
```

## Screens

- **Projects** connects a local folder, a GitHub repository (device flow or a
  pasted token, kept in memory only) or an uploaded folder, and lists what the
  server remembers (`GET /projects`).
- **Run** edits the target profile with host-resolved bounds, presets, and
  real per-field fidelity from `POST /profiles/reconcile` and
  `POST /profiles/fidelity`; runs the command once (`POST /run`) and shows the
  outcome, output, provenance and fidelity. A 422 is shown as "Morph could
  not launch the command", never as a failure.
- **Experiment** streams `POST /experiments/stream` over
  `/ws/experiment/{id}`: verdict first, then a lane per condition with trial
  ticks and a live log-scale evidence track (anytime-valid e-value against
  K/α), the 2×2 interaction matrix, the failing trial's output, and the
  comparison table. Cancel is `DELETE /experiments/{id}`; `POST /minimize`
  gives the minimal failing set.
- **Threshold** streams `POST /threshold/stream` over `/ws/threshold/{id}`
  and draws the dose-response curve with the credible band and every probe;
  it says "no boundary in range" when the search concluded that.
- **Regressions** lists, saves, replays and deletes `/regressions`, and
  exports a CI test whose numbers come from real results.
- **Environment** captures the host, compares any two profiles row by row,
  and saves/loads profiles via `/profiles`.

## Conventions

- No emoji; icons come from `components/ui/Icon.tsx`.
- Status is never colour alone: every chip carries a label or icon.
- Cards nest at most two deep. Motion is limited to the evidence track,
  verdict reveal and trial ticks, and is disabled under
  `prefers-reduced-motion`.
- All inputs are labelled; accordions carry `aria-expanded`; dialogs trap
  focus and close on Escape; the rail is arrow-key navigable.
