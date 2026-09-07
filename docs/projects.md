# Connecting a project

Point Morph at a GitHub repo or a local directory once; run experiments against
it from the CLI, the TUI, or the dashboard.

## Auth

No setup for the common case. Morph resolves a GitHub token in this order:

1. an explicit `--token` / request field
2. `MORPH_GITHUB_TOKEN`, then `GITHUB_TOKEN`, then `GH_TOKEN`
3. `gh auth token`: whatever `gh auth login` already gave you

Only if all three miss does the dashboard fall back to the OAuth **device
flow**: "Connect through GitHub", then "Sign in with a device code". A GitHub
page opens, you type the short code it shows, and Morph picks the token up
in memory (never on disk, never in localStorage).

GitHub requires a registered OAuth App for that flow, so set it up once per
team:

1. github.com/settings/developers, "OAuth Apps", "New OAuth App". Any name,
   any homepage URL, the callback URL can be the homepage; tick
   **Enable Device Flow**. No client secret is needed.
2. Put the app's public client id under `github.client_id` in `morph.yaml`
   (or export `GITHUB_CLIENT_ID`). It is not a secret and can be committed.
3. `morph serve`, open the dashboard, Projects, "Connect through GitHub".

Without a client id the dialog explains exactly this instead of failing
silently.

## CLI

```bash
morph connect owner/repo                 # or a URL, or a local path
morph connect owner/repo --branch dev --install     # clone a branch + build a venv
morph connect ./my/app --name app --install

morph projects                          # list
morph projects --rm <id|name>           # remove
morph reinstall <id|name>               # rebuild the per-project venv / node_modules

morph run        --project <id>
morph experiment --project <id> -n 5
morph threshold  --project <id> --parameter network.latency_ms --low 0 --high 400
```

`--project` fills in the command and working directory from the registry; an
explicit `--command` still wins. `--profile` is optional on `experiment`
(defaults to the captured host plus a 120 ms / 18 % network, the flagship
operating point) and `threshold`. `morph experiment` runs in sequential mode
by default (`--mode batch` for the fixed-N design); `morph threshold` uses
probabilistic bisection by default (`--method bisect` for plain halving);
`morph minimize` finds the minimal failing condition set. See
[how-it-works.md](./how-it-works.md).

`--install` (or the API's `POST /projects/{id}/install`) creates a per-project
venv under `~/.morph/venvs/`, installs `requirements.txt` / `pyproject.toml` via
`uv` (or stdlib `venv`) or `package.json` via `npm`, and rewrites the run
command to use that venv. `morph reinstall <project>` repeats that step for an
already-connected project (after a dependency change, or a broken venv).

## TUI

Home, then **Projects** (`p`). Type a repo or path, tick *install deps*, **Connect**.
Pick a project and press **Experiment** / **Monitor** / **Threshold**: that
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
