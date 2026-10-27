# Frozen-instance horizon benchmark

The first development pilot is complete; see [results and limitations](horizon-pilot-results.md).

## Run and resume

Install the project with the optional Gurobi binding and a usable license as
outlined in [build.md](build.md). SUMO is not launched by this benchmark.

Offline reference and heuristic sweep (no API calls):

```sh
.venv/bin/python -u experiments/horizon_benchmark.py \
  --horizons 15 30 60 120 --families empty ordinary delayed_burst competing_bursts lookahead clearance \
  --seeds 7 --models gurobi stay max-queue short15 \
  --reference-seconds 120 --output-dir results/horizon-offline
```

Small paid first-action pilot: 2 families × 4 horizons × 2 repetitions × 4
remote models = **64 requests**, plus 32 deterministic baseline evaluations.
Every remote request sees the identical frozen state for its instance. Prompts
are frozen before this development pilot; they must not be tuned on held-out
results. The lookahead fixture is explicitly development data.

```sh
.venv/bin/python -u experiments/horizon_benchmark.py \
  --horizons 15 30 60 120 --families ordinary lookahead --seeds 7 \
  --models gurobi stay max-queue short15 microsoft jev luna sol-medium \
  --repeats 2 --reference-seconds 120 --output-dir results/horizon-pilot
```

Add `--resume` with exactly the same arguments and source code to resume. A
filesystem lock prevents duplicate processes. Existing successes and failures
are reused, not erased. If a previous process died after recording a started
attempt but before recording its result, resume records an interrupted failure
and never automatically resends it. It may already have incurred provider
charges. To deliberately retry, create a separate experiment directory and
retain the original attempt in analysis.

`manifest.json` pins source, protocol, objective, generator, horizons, model
selection, repetitions, and time budgets. `instances/` holds complete frozen
problems; `references/` holds both forced-action solves and full plans.
`attempts/` stores each configuration, start timestamp, raw request/response
text without authorization headers, and an atomic result. Summaries are
regenerated in `runs.jsonl` and `report.md` after every result. Unknown provider
usage stays null rather than becoming zero. A transport failure is one failed
attempt; automatic retries are intentionally disabled.

## Metrics

First-action regret compares the optimal continuations after each legal first
action. With optimal values Q(NS), Q(EW), regret is Q(chosen) − min Q. Both tied
choices are correct. An illegal response has no regret and reduces valid-output
rate; it never receives a fabricated score.

If some reference solve is unproven, let L(a) and U(a) be its lower bound and
feasible incumbent cost. Regret bounds are
`[max(0, L(chosen) - min U), max(0, U(chosen) - min L)]` when those endpoints are
available. No uncertified result is labeled optimal. Complete-plan costs are
recomputed by the timer-based validator. Their gap is relative to the certified
best objective, with relative gap omitted when that objective is zero.

All snapshots use the same objective as the earlier pilot: sum of end-of-step
queues plus 0.5 per initiated switch. Frozen instances use deterministic supplied
arrivals, isolating planning from prediction error. The compact reference uses
binary switch events and clearance windows; it fits the installed size-limited
license at 120 steps without changing the feasible schedules or objective.

## Endpoint capabilities checked October 21, 2026

| Endpoint/model | First action | Full-plan status |
| --- | --- | --- |
| Microsoft Decisions | Existing typed choice | Arbitrary plan generation unverified; disabled |
| Jev 1.13 Decisions | Existing typed choice | Arbitrary plan generation unverified; disabled |
| Luna Decisions | Existing typed choice | Arbitrary plan generation unverified; disabled |
| Sol medium chat | Existing strict choice JSON | Strict action-array adapter implemented; live validation pending |
| Gurobi | Forced-action reference | Complete incumbent plan independently validated |

The published [Microsoft model page](https://openrouter.ai/microsoft/microsoft-decision-1),
[Jev 1.13 page](https://openrouter.ai/typesafe/jev-1.13), and
[Luna Decisions page](https://openrouter.ai/openai/gpt-6-luna-decisions) describe
fixed typed decisions. That does not verify support for arbitrary joint action
schedules. Multiple choice questions should not be assumed to produce a
consistent full plan. OpenRouter documents [JSON-schema outputs for compatible
chat models](https://openrouter.ai/docs/guides/features/structured-outputs);
provider compatibility and successful live plan output remain separate checks.

The full-plan command accepts only `--models gurobi sol-medium --mode full-plan`.
It does not change a Decisions model into a chat model. Run a separate output
directory and verify live capability before drawing full-plan conclusions.

## Secondary SUMO configuration

The simulation CLI and matched batch accept `--horizon 30` independently of
`--duration 120`. Browser requests accept `horizon`; the replay form exposes it.
Config, observations, Gurobi, remote prompts, metadata, and cache identities
share this value. Exactly H forecast rows are mandatory. The default remains
15 seconds, but the new prompt protocol is versioned separately, so old v6
results cannot be mistaken for new v7 experiments. Historical replay files
remain untouched; they are not silently upgraded or rerun by this benchmark.

Validation:

```sh
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python scripts/check_repository.py
```

For a standalone visual comparison of a saved first-action run:

```sh
.venv/bin/python scripts/render_horizon_report.py results/horizon-pilot-v1
```

The optional `--sumo-dir results/matched-rerun-2026-10-19` appends the historical
October traffic pilot with its separate protocol and provenance. Rendering
reads saved results and makes no model calls.

## Fresh traffic replays

Generate the five-controller, four-horizon sweep on identical seed-7 demand:

```sh
.venv/bin/python experiments/replay_sweep.py \
  --output-dir results/horizon-replays-new --workers 4
```

This runs 20 actual SUMO episodes and makes paid remote-model calls. Each
episode lasts 120 simulated seconds. Completed recordings are copied into the
browser cache. Requests and responses are journaled without authorization
headers; individual run status and the source snapshot are preserved. Resume
requires an identical manifest and reuses failures/interrupted attempts rather
than resending potentially billed calls. `--controllers gurobi` runs only the
local baseline. A filesystem lock prevents duplicate sweeps in one directory.

The completed October 21 sweep is consolidated in
`results/horizon-replays-final-2026-10-21/`: 20 replays, 1,112 remote calls,
$1.363365 reported cost, zero collisions, and zero rejected actions. Four local
Gurobi runs were regenerated with `queue-switch-events-v2`: feasibility and
integrality tolerances of 1e-9 prevent accumulated numerical slack from
exceeding the independent scorer's 1e-6 certification threshold. The objective,
constraints, and 0.8-second controller budget are unchanged. Original attempts
and source snapshots remain in the two source-run directories named by the
consolidated manifest. Earlier frozen benchmark outputs keep their original
v1 references and source fingerprints.

Open `http://127.0.0.1:8765/?models=5&saved=1&controller=gurobi&horizon=120`
after starting the replay server. Saved mode never starts a simulation or model
call on a missing recording. Select another controller or horizon to compare.
The cache treats equivalent integer/float parameters as the same scenario.

To append the new replay statistics and watch links to the comparison report:

```sh
.venv/bin/python scripts/render_horizon_report.py results/horizon-pilot-v1 \
  --sumo-dir results/horizon-replays-final-2026-10-21 \
  --replay-base-url http://127.0.0.1:8765/
```
