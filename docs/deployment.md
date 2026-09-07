# Deployment

Morph is local-first: the API runs arbitrary commands on the machine it is
started on, so the normal deployment is "on the developer's laptop" or "on a
worker box you own". This page covers what is committed, what lives in the
environment, and how to host a demo safely.

## What goes where

| Kind | File | Committed? | Examples |
|---|---|---|---|
| Project settings | `morph.yaml` | yes | trial defaults, adapters, worker provider, GitHub OAuth client id (public) |
| Secrets and per-machine values | `.env` | no (gitignored) | `MORPH_GITHUB_TOKEN`, `MORPH_CLOUD_HOST` / `USER` / `SSH_KEY`, `MORPH_EXTRA_ORIGINS` |
| Reference for `.env` | `.env.example` | yes | every variable Morph reads, with a comment each |

`morph` loads the nearest `.env` at startup (walking up from the working
directory to the git root), for the CLI, `morph serve` and `morph tui`.
Values already in the environment win, so a container or CI runner can
override the file. `MORPH_ENV_FILE=/path/to/.env` points at a specific file.

Setup for a new machine:

```bash
cp .env.example .env      # then fill in what you need; all of it is optional
morph doctor              # confirms what this host can shape and whether a worker is reachable
```

## Running the dashboard in one process

```bash
cd frontend && npm ci && npm run build && cd ..
morph serve                # http://127.0.0.1:8000 serves the API and the built dashboard
```

When `frontend/dist` exists (or `MORPH_DASHBOARD_DIR` points at a build),
`morph serve` serves it from the same origin as the API: one port, no CORS
configuration, and the dashboard's client-side routes survive a reload. In
development keep using `npm run dev` on port 5173, which proxies `/api` to
the backend.

## Hosting a demo on a box you own

The API has no authentication by design (it is a local tool), so:

1. Run it on a private network, or behind a reverse proxy that authenticates
   (Tailscale, Cloudflare Access, an nginx basic-auth block, an SSH tunnel).
2. `morph serve -H 0.0.0.0 -p 8000` prints a red warning for exactly this
   reason. Set `MORPH_ALLOWED_HOSTS=demo.example.com` so TrustedHost only
   accepts your hostname.
3. If the dashboard is served from a different origin than the API (a static
   host in front of the API), add that origin: `MORPH_EXTRA_ORIGINS=https://demo.example.com`.
   Serving the built dashboard from `morph serve` avoids this entirely.
4. GitHub sign-in on the hosted dashboard needs the OAuth App's client id
   (`github.client_id` in `morph.yaml` or `GITHUB_CLIENT_ID`). Because it is a
   device flow there is no callback URL to register per deployment.
5. Network shaping without root uses the user-space proxy; for `tc`/cgroup
   shaping give the service account passwordless `sudo tc` and a delegated
   cgroup (see `scripts/setup_gcp_worker.sh`).

A minimal systemd unit:

```ini
[Service]
WorkingDirectory=/opt/morph
EnvironmentFile=/opt/morph/.env
ExecStart=/opt/morph/.venv/bin/morph serve -H 127.0.0.1 -p 8000
Restart=on-failure
```

with nginx (or any authenticating proxy) in front of `127.0.0.1:8000`.

## Remote workers

A worker is any SSH-reachable machine with Morph installed
(`scripts/setup-pi.sh`, `scripts/setup_gcp_worker.sh`). Point at it from
`.env` (`MORPH_CLOUD_HOST`, `MORPH_CLOUD_USER`, `MORPH_CLOUD_SSH_KEY`), check
it with `morph cloud`, and dispatch explicitly with `morph run --cloud`.
Details in [`cloud.md`](cloud.md).

## CI

`.github/workflows/ci.yml` sets `MORPH_NO_NETWORK=1` so no test can reach a
worker, runs lint, the suite on Linux and macOS, the frontend build and the
demo-app corpus. Nothing in CI needs a secret.
