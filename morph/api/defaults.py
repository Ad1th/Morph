"""One place for every default the CLI and the API share.

The `morph experiment` / `morph threshold` commands and the `/experiments` /
`/threshold` routes used to carry their own copies of these numbers (the audit
found a threshold search that bisected nine times from the CLI and six from the
API on identical input). Both entry points now import from here, so the same
request means the same experiment however it arrives.

Nothing in this module imports FastAPI or Typer: it is safe to import from a
CLI that must start fast and from a worker process that has neither installed.
"""

from __future__ import annotations

# --- experiments ----------------------------------------------------------- #

#: Trials per condition in batch mode (`--mode batch`, `"mode": "batch"`).
TRIALS = 5

#: Round budget in sequential mode (`--mode sequential`, the default). Each
#: round is one baseline trial plus one trial per still-active condition.
SEQUENTIAL_MAX_ROUNDS = 12

#: Family-wise false-positive rate for the sequential e-value stopping rule.
ALPHA = 0.05

#: Minimum rounds before a sequential condition may be declared decisive.
SEQUENTIAL_MIN_ROUNDS = 3

#: Experiment modes accepted by `--mode` / `"mode"`.
EXPERIMENT_MODES = ("sequential", "batch")
DEFAULT_EXPERIMENT_MODE = "sequential"

# --- threshold search ------------------------------------------------------ #

#: Trials per probe in bisection mode (`--method bisect`).
THRESHOLD_TRIALS = 3

#: Trial budget for the Bayesian search (`--method bayes`, the default).
THRESHOLD_MAX_TRIALS = 30

#: Default precision as a fraction of ``high - low``: the search stops once
#: the bracket (bisect) or the credible interval (bayes) is narrower than this.
THRESHOLD_PRECISION_FRACTION = 0.02

#: Posterior mass reported as the credible interval in bayes mode.
THRESHOLD_CREDIBLE_MASS = 0.9

THRESHOLD_METHODS = ("bayes", "bisect")
DEFAULT_THRESHOLD_METHOD = "bayes"

THRESHOLD_LOW = 0.0
THRESHOLD_HIGH = 500.0

# --- runs ------------------------------------------------------------------ #

#: Per-trial timeout in seconds.
TIMEOUT_SEC = 30.0

# --- demo / default target ------------------------------------------------- #

#: Validated operating point for the flagship interaction fixture
#: (apps/pool_retry): neither condition alone moves the failure rate, the pair
#: drives it to ~100 %. See apps/README.md.
DEMO_LATENCY_MS = 120.0
DEMO_PACKET_LOSS_PERCENT = 18.0
DEMO_COMMAND = "python3 -m apps.pool_retry test"

# --- server ---------------------------------------------------------------- #

SERVE_HOST = "127.0.0.1"
SERVE_PORT = 8000
#: Origins the browser dashboard is served from in development (Vite).
DEV_ORIGINS = ("http://localhost:5173", "http://127.0.0.1:5173")

# --- bounded stores -------------------------------------------------------- #

#: Experiments (and threshold searches) kept in memory for `GET /experiments/{id}`
#: and WebSocket replay. Oldest are evicted first.
MAX_CACHED_EXPERIMENTS = 50

#: Longest stdout/stderr tail kept per trial event in the replay log.
EVENT_TAIL_CHARS = 2048


def default_precision(low: float, high: float) -> float:
    """Precision for a threshold search over ``[low, high]``: 2 % of the range."""
    return (high - low) * THRESHOLD_PRECISION_FRACTION
