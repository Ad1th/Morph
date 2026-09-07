# How Morph works

> From "it fails on the user's machine" to "it fails when latency exceeds 42 ms
> under 18 % loss, and nothing else matters", with the statistics that let you
> say so out loud.

Morph is a pipeline of small, separately testable steps. Each one is a module
under `morph/` and each produces a typed result the next one consumes. This
page walks the pipeline once, end to end, and explains the maths where the
maths is the point.

```
capture  ->  reproduce  ->  run  ->  sequential isolation  ->  interaction test
         ->  probabilistic bisection  ->  ddmin minimal set  ->  classification
         ->  regression export
```

## 1. Capture

`morph capture` (`morph/profiler/`) reads the conditions an application can
actually see: OS family and version, CPU architecture, cores and quota, RAM,
locale and timezone, filesystem behaviour, process limits (`ulimit -n`,
`ulimit -u`), and, when a network section is requested, latency, packet loss
and bandwidth. The result is an `EnvironmentProfile` (`morph/schema/profile.py`):
plain JSON, one `{value, status}` pair per field. `status` records provenance,
`captured` on the source machine, `requested` when a developer typed it, and
after a run `reproduced`, `approximated` or `unavailable`, so a result can
never quietly claim more than the runtime delivered.

`morph define -t high-latency` writes the same shape with a requested network
section; `profiles/` holds the ones the demo uses.

## 2. Reproduce

`morph run -p profile.json -c "<command>"` hands the profile to the
`RuntimeController` (`morph/runtime/controller.py`), which picks the adapter
for the host OS (`morph/runtime/adapters/{linux,macos,windows}.py`) and asks it
to apply each section. Network conditions use the kernel when root is
available (`tc netem` on Linux, dummynet through `pf` on macOS); otherwise the
adapter starts Morph's user-space TCP proxy (`adapters/proxy.py`) and exports
`MORPH_NET_LATENCY_MS` / `MORPH_NET_PACKET_LOSS_PCT` to the child. The proxy is a
proper delay line: `latency_ms` is a round-trip time, chunks are pipelined so
latency never caps throughput, and packet loss never corrupts bytes. A lost
chunk is delivered late after a simulated retransmission stall of
`max(200 ms, 3 x RTT)`, doubling on consecutive losses, exactly the way TCP
turns loss into delay. An application therefore fails under loss the way it
fails in production: by a deadline, not by a parse error.

Locale and timezone are exported as `LC_ALL`, `LANG` and `TZ`. Process limits
are applied with `setrlimit` in the child before `exec`. CPU quota and memory
caps are cgroups on Linux with root; on macOS and Windows they are exported as
`MORPH_CPU_QUOTA_PERCENT` / `MORPH_MEMORY_LIMIT_MB` hints and reported as
`unavailable`, never faked. Every adapter returns a per-field *fidelity* record
(`status`, `mechanism`, `detail`) saying what was actually done, and that
record travels with the result.

Native changes are dangerous to leave behind: `finally:` does not run on
SIGKILL or a pulled plug. So every `tc` rule, dummynet pipe or cgroup write is
recorded in `~/.morph/state/shaping.json` (`morph/runtime/state.py`) *before*
it is applied and removed after it is reverted; `morph doctor` finds and undoes
whatever a dead process left, and checks the interpreter, adapter, shaping
tools, sudo, proxy, config and worker up front.

## 3. Run

`morph/telemetry/collector.py` launches the command with `shell=False`,
pins a bare `python` to the interpreter Morph itself runs under, starts the
child in its own session so the whole tree can be killed on timeout, and
records exit code, bounded stdout/stderr, duration, peak RSS and CPU. Exit code
`0` is a pass and `1` a failure. Exit code `2`, plus `126`/`127` and "cannot
launch", marks the trial *invalid* (`RunResult.invalid`, with
`invalid_reason`): the app could not attempt the test at all. The engine
retries an invalid trial a few times and otherwise raises, instead of counting
it as evidence either way.

Each `RunResult` also carries provenance: the `seed` the proxy used (so a loss
pattern can be replayed), `morph_version`, a `host_fingerprint`, the
`profile_hash` of the exact conditions requested, the `adapter` that applied
them and its `fidelity` map. Two results are comparable only when those agree,
and a regression bundle records them so a replay can say whether it really
reproduced the original run.

## 4. Sequential isolation

This is the step the rest of the pipeline exists for. Given a target profile
that deviates from the host in several fields, Morph builds one *candidate*
condition per deviating variable plus the full target (`morph/engine/runners.py`)
and asks, for each candidate, whether it makes the application fail more often
than the unconstrained baseline.

The obvious design, N baseline runs then N runs per candidate then one
Fisher test, has a flaw when the result is being watched live: a p-value that
is checked after every trial and acted on when it first dips below 0.05 is no
longer a 5 % false-positive rate. That is optional stopping, and the console
*is* a live view. So the default mode (`morph/engine/sequential.py`) is a
paired, round-robin design with an anytime-valid statistic.

**Pairing.** Each round runs one baseline trial and one trial per candidate,
rotating the order so no candidate always follows the baseline. Slow drift on
the host (thermal throttling, a backup starting) hits both arms of every pair
equally.

**The e-process** (`morph/engine/anytime.py`). Under the null hypothesis that a
candidate and the baseline fail with the same probability, a *discordant*
pair, one where exactly one arm failed, is equally likely to be either way
round. So the sequence "which arm failed" is a fair-coin stream; concordant
pairs carry no information and are skipped. Against that fair coin Morph runs
Robbins' Beta-mixture likelihood ratio: with `k` treatment-failed pairs among
`m` discordant ones and a Beta(a, b) prior on the alternative
`q = P(treatment is the failing arm)`,

```
E_m  =  2^m * B(a + k, b + m - k) / B(a, b)
```

restricted to the one-sided alternative `q >= 1/2` ("treatment is worse").
`E_m` is a non-negative supermartingale with expectation 1 under the null, so
by Ville's inequality

```
P_H0( E_t >= 1/alpha  for some t )  <=  alpha
```

Rejecting the moment the running e-value reaches `1/alpha` controls the
type-I error at *every* stopping time, whether you stop at round 3 or round
30, and `min(1, 1/E)` is a p-value that stays valid however long you watch it.
With `K` candidates sharing one budget the bar is `K/alpha` (a Bonferroni
split), which keeps the family-wise error at `alpha`. Reading the number:
`E = 20` means the data are twenty times more likely under "this condition
fails more" than under "no difference". The flagship latency-and-loss fault
decides in about seven pairs.

`morph experiment --mode batch` keeps the fixed-N design for readers who want
the familiar Fisher table; it uses the one-sided exact test (the hypothesis is
directional) with Holm's step-down correction across the `K` candidates, and
reports a Newcombe risk-difference interval alongside each p-value. Its
p-values are only honest if nobody stopped early.

## 5. Interaction test

A single-variable sweep can miss the failures Morph most wants to find: the
ones where latency alone passes, loss alone passes, and only the pair fails.
`detect_interaction` (`morph/engine/experiment.py`) runs the four cells of the
2x2 design, `neither`, `A`, `B`, `A+B`, and confirms an interaction only when
`A` and `B` each show no significant effect while `A+B` does. That is the
claim the `apps/pool_retry` fixture exists to make, and the reason the demo
profile turns two knobs at once.

## 6. Probabilistic bisection

Once a continuous parameter is implicated, Morph asks where along it failures
begin. Plain bisection (`morph/engine/threshold.py`, `--method bisect`) halves
an interval and takes a majority vote at each probe. With a flaky oracle, an
application that fails 70 % of the time at 200 ms and 5 % of the time at
100 ms, one unlucky vote sends it into the wrong half for good, and it then
reports that wrong answer to a decimal place.

The default (`morph/engine/boundary.py`, `--method bayes`) is Horstein's
probabilistic bisection (1963), whose geometric convergence under a noisy
oracle was proved by Waeber, Frazier and Henderson (2013). It keeps a
posterior over the boundary location `theta` on a grid and probes at the
posterior median. The response model is the logistic dose-response curve of
QUEST (Watson and Pelli, 1983):

```
P(fail | x)  =  floor + (ceiling - floor) * sigmoid((x - theta) / scale)
```

`floor` is the failure rate far below the boundary (flakiness that has nothing
to do with the parameter) and `ceiling` the rate far above it (a fault that
bites 80 % of the time is still a fault). Rather than guess them, the posterior
ranges over a small grid of `(theta, floor, ceiling)` triples and `theta` is
marginalised out, so "how flaky is this app" is learned from the same trials.
Two extra hypotheses, "never fails in this range" and "always fails in this
range", guard against fabricated boundaries: if either wins, no threshold is
reported. The result is a credible interval (`credible_low`, `credible_high`,
90 % mass by default) and a posterior median, plus the whole posterior and
dose-response curve for a UI to draw. The search stops when the interval is
narrower than the requested precision or the trial budget runs out.

## 7. Minimal condition set

A target profile can deviate from the host in five fields when only two
matter. `morph minimize` (`morph/engine/minimize.py`) applies delta debugging,
`ddmin` (Zeller and Hildebrandt, 2002), over the set of deviating conditions:
it repeatedly tries to remove subsets while the application still fails, and
returns a *1-minimal* set, one from which removing any single condition makes
the failure go away. For a flaky target the oracle is a small batch under each
subset with a failure-rate threshold, so one lucky pass cannot derail the
search. Results are memoised, and `oracle_calls` reports how many distinct
subsets were actually run.

## 8. Classification

`morph/engine/classifier.py` turns the strongest comparison into one of four
verdicts:

| verdict | meaning |
|---|---|
| `application_internal` | the baseline already fails often (the lower bound of a 95 % Wilson interval on its rate is above 10 %); the environment is not the story |
| `environment_caused` | the baseline never failed and the treatment is significantly worse |
| `environment_exposed` | the baseline fails a little and the treatment amplifies it: the bug is in the application, the condition only makes it visible (the `apps/race` story) |
| `no_effect` | the treatment did not significantly raise the failure rate |

The Wilson bound is what stops one bad baseline run (1 of 5, rate 0.20,
interval 0.01 to 0.62) from being called an application bug.

## 9. Regression export

`morph save` freezes the profile, command and expected outcome as a regression
bundle; `morph replay` runs it again, under the same conditions, and reports
`COMPLIANT` or `VIOLATION`; `morph export` writes a standalone
`test_morph_invariant.py` a CI job can run without Morph's engine, embedding
the discovered safe envelope. The condition that broke the app becomes the
test that proves the fix, and stays.

## Why the statistics are not decoration

Every number Morph shows live is safe to act on the moment it appears: the
e-value by construction, the credible interval because it is a posterior, the
Wilson bound because it is an interval rather than a point. The numbers that
are *not* safe to watch (a fixed-N Fisher p-value) are computed once, at the
end, and labelled as such. That is the difference between "we ran it a few
times and it looked significant" and a verdict you can put in a bug report.

## References

- Ramdas, A., Grünwald, P., Vovk, V. and Shafer, G. (2023). *Game-theoretic
  statistics and safe anytime-valid inference.* Statistical Science 38(4).
- Turner, R. J., Ly, A. and Grünwald, P. D. (2024). *Safe tests and
  always-valid confidence intervals for contingency tables and beyond.*
  Journal of Statistical Planning and Inference.
- Holm, S. (1979). *A simple sequentially rejective multiple test procedure.*
  Scandinavian Journal of Statistics 6(2), 65-70.
- Horstein, M. (1963). *Sequential transmission using noiseless feedback.*
  IEEE Transactions on Information Theory 9(3).
- Waeber, R., Frazier, P. I. and Henderson, S. G. (2013). *Bisection search
  with noisy responses.* SIAM Journal on Control and Optimization 51(3).
- Watson, A. B. and Pelli, D. G. (1983). *QUEST: a Bayesian adaptive
  psychometric method.* Perception and Psychophysics 33(2).
- Zeller, A. and Hildebrandt, R. (2002). *Simplifying and isolating
  failure-inducing input.* IEEE Transactions on Software Engineering 28(2).
- Newcombe, R. G. (1998). *Interval estimation for the difference between
  independent proportions.* Statistics in Medicine 17, 873-890.
