# Connecting a project

Point Morph at a GitHub repo or a local directory once; run experiments against
it from the CLI, the TUI, or the dashboard.

## Auth

No setup for the common case. Morph resolves a GitHub token in this order:

1. an explicit `--token` / request field
2. `MORPH_GITHUB_TOKEN`, then `GITHUB_TOKEN`, then `GH_TOKEN`
3. `gh auth token` — whatever `gh auth login` already gave you

Only if all three miss do you need the OAuth **device flow** (dashboard), which
needs a `GITHUB_CLIENT_ID`.

## CLI

```bash
morph connect owner/repo                 # or a URL, or a local path
morph connect owner/repo --branch dev --install     # clone a branch + build a venv
morph connect ./my/app --name app --install

morph projects                          # list
morph projects --rm <id|name>           # remove

morph run        --project <id>
morph experiment --project <id> -n 5
morph threshold  --project <id> --parameter network.latency_ms --low 0 --high 400
```

`--project` fills in the command and working directory from the registry; an
explicit `--command` still wins. `--profile` is optional on `experiment`
(defaults to the captured host plus a 120 ms / 18 % network) and `threshold`.

`--install` (or the API's `POST /projects/{id}/install`) creates a per-project
venv under `~/.morph/venvs/`, installs `requirements.txt` / `pyproject.toml` via
`uv` (or stdlib `venv`) or `package.json` via `npm`, and rewrites the run
command to use that venv.

## TUI

Home → **Projects** (`p`). Type a repo or path, tick *install deps*, **Connect**.
Pick a project and press **Experiment** / **Monitor** / **Threshold** — that
screen opens with the command pre-filled and every trial running from the
project's directory.

## Dashboard

The desktop *connect* dialog has GitHub (device flow / PAT / **Use gh CLI**),
local directory, and folder upload. **Install dependencies after cloning** runs
the install step before you reach the parameter screen.

## Where things live

```
~/.morph/projects/<id>.json     registry entries (survive restarts)
~/.morph/checkouts/<owner-repo>/ cloned repos
~/.morph/venvs/<name>/           per-project virtualenvs
```
