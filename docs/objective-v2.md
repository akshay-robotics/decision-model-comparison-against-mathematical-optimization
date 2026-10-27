# Terminal-queue objective v2

The October 21, 2026 rerun tests one objective change at a fixed **15-second
planning horizon**. Gurobi's earlier traffic outcomes tied across 15/30/60/120
seconds; its mean legal-choice latency was fastest at 15 seconds. Every fresh
episode uses the original seed-7 demand, 120 simulated seconds, and all five
controllers.

## Exact objective

```text
J = sum(q_NS[t] + q_EW[t], t=1..H)
    + 0.5 * initiated_switches
    + 10 * (q_NS[H] + q_EW[H])
```

The final queues appear in the running sum and receive an additional terminal
cost once. Ten objective units per residual car correspond to ten additional
seconds of queueing under the running-cost convention. This coefficient was
fixed before running and was not selected by searching the rerun's outcomes.
It is an initial design choice requiring validation on independent demand.

This is a residual **modeled queue** penalty. It does not directly count SUMO
trip completion, vehicles in transit, or entry backlog outside the observed
forecast. Waiting-age fairness and calibrated service rates are separate
future changes. Green/yellow capacities remain 2/1 vehicles per second;
switching penalty remains 0.5; minimum green, yellow, and all-red remain 5/3/2
seconds. Gurobi retains its 0.8-second budget and Sol retains medium reasoning
and its 4,096-token limit.

## Shared implementation and prompt

- Active objective: `end-step-queues-plus-terminal-v2`, terminal weight 10.
- Shared question: `matched-queue-v8-terminal-queue`, used verbatim for
  Microsoft, Jev, Luna, and the Sol chat envelope.
- Reference/scorer: `queue-switch-events-v3-terminal`; both add the same final
  queue cost. Exhaustive tiny-instance checks include a case where adding this
  term changes the optimal first action.
- Results and model metadata record the complete objective. Cache identities
  include its fingerprint; objective mismatches cannot trigger an automatic
  paid rerun.
- The replay's frozen-optimization panel filters by objective version, so an
  older v1 regret/certificate cannot be displayed as evidence for v2.

Historical v1 instance records deserialize with a zero terminal coefficient
and retain their original fingerprints. Historical results are preserved.

## Run and artifacts

```sh
.venv/bin/python experiments/replay_sweep.py --horizons 15 --workers 4 \
  --output-dir results/terminal-objective-v2-h15-2026-10-21
```

This runs actual SUMO episodes and paid remote calls. The directory contains a
frozen manifest and source snapshot, per-run status, raw credential-free call
journals, replay frames, route files, trip records, and failure-inclusive
statuses. `h15/report.md` summarizes completed episodes. The previous comparison
is in `results/horizon-replays-final-2026-10-21/`.

Evaluate the before/after change on completion, all-demand time in system,
completed-only travel/wait, approach coverage, and latency. A single seed cannot
establish that the coefficient improves traffic generally.

## Completed rerun

All five episodes completed. Route XML hashes match the original demand and
each other. All 219 recorded model requests use the identical revised
15-second objective question. Total reported API cost was $0.336895; there
were zero collisions and rejected actions. The test run had 38 passes and two
live SUMO tests skipped; the five fresh episodes separately
exercise live SUMO.

| Controller | Old completed /78 | New completed /78 | Old mean system s | New mean system s |
| --- | ---: | ---: | ---: | ---: |
| Gurobi | 64 | 65 | 28.27 | 27.21 |
| Microsoft | 54 | 53 | 34.85 | 35.35 |
| Jev | 66 | 60 | 24.67 | 28.38 |
| Luna | 54 | 58 | 30.31 | 30.40 |
| Sol medium | 64 | 65 | 28.27 | 27.21 |

Gurobi's 43 legal-choice solves reported optimal status with zero gap. Its
traffic metrics improved slightly; Sol matched the new traffic outcomes.
The objective change did not improve every controller. Remote outputs are
stochastic, and the experiment has one episode per condition, so these are
observations rather than a general causal claim. The coefficient was not
retuned after seeing the results.

The run directory contains `comparison.html` and `comparison.md`, including
before/after completion, system time, completed-only travel/wait, latency,
cost, and links to the new saved replays. `verification.json` records the final
checks. Historical frozen optimization scores remain separate: no new v2
frozen benchmark was billed or inferred from these traffic episodes.
