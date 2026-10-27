# Frozen-horizon development pilot: October 21, 2026

The first milestone is implemented and the small paid first-action pilot is
complete. The experiment compares identical frozen queue problems at 15, 30,
60, and 120 seconds using the unchanged queue objective and switch penalty.
See the [research plan](research-plan.md) and [protocol](horizon-benchmark.md).

## Scope and evidence

- Offline sweep: six families, one seed, four horizons; **24 certified
  references** and 96 deterministic baseline evaluations.
- Paid pilot: ordinary and lookahead families, seed 7, four horizons; eight
  frozen problems, two calls per model per problem, **64 remote requests** and
  32 baseline evaluations.
- All eight paid-pilot references are certified. All saved reference plans were
  independently rescored and agree with their recorded objectives.
- 61/64 remote responses are valid; three Sol responses ended at the 4,096
  output-token cap. They remain failures, with billed usage retained.
- Total reported API cost: **$0.30102444**. Usage was present for every call.
- Complete-plan reference check: four lookahead horizons, four feasible Gurobi
  plans, all with zero independently computed objective gap. No paid full-plan
  model experiment was run.

## First-action regret on the lookahead fixture

Lower is better; zero denotes a certified optimal first action. Numbers are
means over valid, certified attempts. Every deterministic baseline has one
evaluation. Every remote cell has two calls unless explicitly noted.

| Controller | 15 s | 30 s | 60 s | 120 s |
| --- | ---: | ---: | ---: | ---: |
| Gurobi reference | 0 | 0 | 0 | 0 |
| Stay | 4 | 0 | 0 | 0 |
| Largest current queue | 0 | 9 | 30.5 | 6 |
| 15-second optimizer | 0 | 9 | 30.5 | 6 |
| Microsoft | 4 | 9 | 30.5 | 6 |
| Jev 1.13 | 4 | 0 | 0 | 0 |
| Luna | 4 | 0 | 0 | 6 |
| Sol medium | 0 | 0 (1/2 valid) | 30.5 (1/2 valid) | 0 (1/2 valid) |

All four models were valid and optimal on every ordinary-case call. The
lookahead fixture has optimal first action EW at 15 seconds and NS at all three
longer horizons. It is disclosed development data, selected to expose a
short-horizon error; it is not held-out evidence.

## Request performance across all eight pilot problems

Latency includes failed calls. Optimal/all uses all 16 attempts as its
denominator, while the detailed reports also show optimal/scored. This prevents
the surviving successful calls from concealing failures.

| Model | Valid / calls | Optimal / all | Mean latency s | Reported cost USD |
| --- | ---: | ---: | ---: | ---: |
| Microsoft | 16/16 | 8/16 | 0.644 | 0.000484 |
| Jev 1.13 | 16/16 | 14/16 | 0.317 | 0.000777 |
| Luna | 16/16 | 12/16 | 0.437 | 0.001274 |
| Sol medium | 13/16 | 12/16 | 41.785 | 0.298490 |

These are sequential end-to-end request times, including transport and provider
processing. The methods have different fixed output formats and inference
budgets. Sol's medium-reasoning setting and token cap are retained as part of
the frozen configuration. Raising its cap would require a separate experiment;
these failures must not disappear from the present results.

## Interpretation

This pilot demonstrates that the scoring machinery detects costly choices and
that the curated fixture distinguishes a full-horizon reference from a
15-second optimizer. It does **not** establish a general model ranking or
monotonic degradation with horizon. Longer-horizon regrets need not increase,
and their absolute objective scale changes with the horizon. Most offline
families at this seed are easy for the baseline heuristics.

There are only two underlying demand trajectories in the paid pilot. Their
horizon variants are nested, and repeated model calls share the same frozen
instance. A larger, frozen held-out set with independent trajectories is the
next research step before making population-level claims.

The earlier SUMO completion and starvation results remain secondary. They use
the older v6 prompt protocol and must not be pooled with the new v7 frozen
benchmark. In that historical traffic run, Luna completed 33/78 cars and zero
east/west trips despite low completed-only travel and waiting times.

## Saved artifacts and verification

Local output directories (ignored by Git):

- `results/horizon-pilot-v1/`: manifest, eight frozen instances, reference
  certificates, 64 raw request/response pairs, 96 attempt records, Markdown
  report, and a standalone HTML comparison. Its secondary traffic tables now
  include the fresh four-horizon SUMO replay sweep.
- `results/horizon-offline-v1/`: the 24-instance offline sweep.
- `results/horizon-full-plan-reference-v1/`: the four full-plan checks.
- `results/horizon-sumo-integration-v1/`: a fresh 40-second SUMO episode with a
  30-second planning horizon, zero rejected actions, and optimal status for all
  17 non-forced decisions.

All 33 tests passed with live SUMO integration enabled, including independent
exhaustive checks on tiny instances. Resuming the completed paid pilot made
zero requests and left every saved attempt file unchanged. Saved artifacts
were checked for the current API key; none contained it.

Regenerate the standalone comparison without making model calls:

```sh
.venv/bin/python scripts/render_horizon_report.py results/horizon-pilot-v1 \
  --sumo-dir results/horizon-replays-final-2026-10-21 \
  --replay-base-url http://127.0.0.1:8765/
```

The fresh replay sweep completed all 20 episodes on October 21, 2026. It is a
separate closed-loop evaluation: 1,112 model calls, $1.363365 reported API cost,
and identical demand across every controller/horizon. See the
[replay protocol and numerical-tolerance correction](horizon-benchmark.md#fresh-traffic-replays).
