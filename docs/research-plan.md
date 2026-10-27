# Research plan: optimization quality as planning horizon grows

## Frozen research question

**How does decision-model solution quality degrade with planning horizon length
and planning difficulty on identical constrained optimization instances?**

The primary experiment is a single-intersection frozen-instance horizon sweep.
The SUMO traffic replay, completed cars, observed time in system, and starvation
metrics are a **secondary closed-loop evaluation**. Different controllers' later
SUMO observations diverge; those later decisions are not identical optimization
problems and cannot establish optimization regret.

The [original traffic coordination plan](research-plan-traffic-pilot.md) and
[earlier pilot](matched-pilot.md) remain historical context. Connected
intersections, joint CAV control, different objectives, and new network geometry
are deferred until the optimization scoring machinery is validated.

## Objective and timing contract

The original frozen benchmark retains the aggregate queue objective:

`J = sum(q_NS[t] + q_EW[t], t=1..H) + 0.5 * initiated_switches`.

Planning steps are one second. In each step, add that step's supplied arrivals,
then serve as much as possible up to the active group's capacity: 2 vehicles
under green, 1 under outgoing yellow, and 0 under all-red. The opposing group
receives no service. Default timing is 5 seconds minimum green, 3 yellow, and 2
all-red. Switching starts yellow immediately; a new green starts with age zero.
Only switches initiated inside the horizon incur the penalty. There is no
terminal queue penalty, drain period, fuel objective, or traffic-completion
bonus in this optimization objective.

On October 21, 2026, a separately versioned **terminal-queue objective v2** was
introduced for a new 15-second SUMO comparison:

`J_v2 = J_v1 + 10 * (q_NS[H] + q_EW[H])`.

The residual queue receives this additional penalty once, after its final
running cost. The weight is fixed before running, equivalent to ten additional
seconds of queueing per residual car; it is a starting hypothesis, not a tuned
or validated optimum. It concerns modeled queues, not completed SUMO trips or
unobserved entry backlog. Capacities, switching penalty, timing, and inference
budgets remain unchanged. All four remote models receive the same v8 objective
question and Gurobi/validator compute the same formula. Historical v1 records
retain their objective, instance identities, and results.

All four original Gurobi horizons tied on traffic outcomes; 15 seconds was
selected because it had the fastest mean decision time. The new comparison
changes only this terminal-cost term and uses the same seed-7 demand and
120-second simulation duration. See [the objective-v2 experiment](objective-v2.md).

`H` is independent of SUMO episode duration. Initial horizons are **15, 30, 60,
and 120 seconds**. Every instance supplies exactly H arrival pairs. Missing rows
raise an error; extending an optimizer never silently appends zero arrivals.
A zero in a frozen instance is an explicitly supplied value. In SUMO, forecasts
still infer arrivals from observed approaching vehicles, not hidden demand.

## Matched frozen instances

Each immutable instance contains initial NS/EW queues, outgoing/current phase,
green age, pending phase and remaining clearance, all signal timing constraints,
objective parameters, and the complete deterministic arrival sequence. All
controllers receive the same state and objective at each horizon. Horizon
variants use prefixes of the same trajectory, preserving the queues and every
already supplied arrival. Instance labels and reference solutions never enter
model prompts.

Case families include empty/easy traffic, ordinary seeded demand, delayed
bursts, competing future bursts, initial clearance, and a disclosed lookahead
fixture. The latter was found during development: at H=15, EW costs 194.5 versus
198.5 for NS; at H=30, NS costs 325 versus 334 for EW. It is a regression case,
not held-out evidence. Seeded extensions vary later demand. Physical-instance
fingerprints exclude labels/seeds so duplicate physical problems are counted
once in the report's distinct-problem count.

Compare against staying, largest-current-queue choice, a 15-second optimizer,
and the full-horizon reference. Verify horizon-dependent optimal actions and
heuristic regret before claiming that a family requires longer lookahead.
Longer descriptions alone do not establish more difficult planning.

## Explicit evaluation modes

| Mode | Required output | Primary measurement |
| --- | --- | --- |
| First action | One legal NS/EW desired-phase choice | Cost of that first action after optimizing its entire continuation |
| Full plan | Exactly H desired-phase actions, including forced steps | Mechanical feasibility and independently scored objective gap |

The Decisions models remain on their existing Decisions endpoint. Their
published interfaces provide typed choices/scores rather than arbitrary JSON
plan generation. Full-plan generation is **not verified** for these endpoints;
it is disabled in the runner. Multiple simultaneous choice questions or
sequential replanning would be separately specified experiments, not an implicit
replacement for joint full-plan generation. No Decisions model is silently
replaced with a chat model.

Sol retains its existing chat model and medium reasoning. A separate full-plan
JSON-array adapter is implemented and tested with mock responses. Its live
full-plan capability must be checked before a paid full-plan study; the initial
paid pilot is first-action only. See [the benchmark protocol](horizon-benchmark.md)
for capability sources and commands.

## Gurobi reference and independent scorer

Use a generous **120-second offline budget per forced-action solve**, one thread,
a fixed solver seed, zero relative MIP tolerance, and 1e-6 absolute certification
tolerance. This budget is independent of the 0.8-second closed-loop controller
budget. A separate experiment directory/configuration is required for
latency-limited optimizer comparisons.

Solve each legal first action with its continuation optimized. Save every
complete incumbent plan, independently scored objective, best bound, solver
status/version, solve and wall time, variable/constraint counts, and gap. Mark a
reference certified only when every legal first-action subproblem has an
optimal solver status, an incumbent, agreement with the independent scorer,
and matching bound within tolerance. A time-limited incumbent is not optimal.

First-action regret is `Q(action) - min_a Q(a)` only for certified references.
Both tied actions receive zero regret, regardless of the prompt's preference to
stay. Uncertified references report intervals from lower and upper bounds,
without a point regret or a claimed optimal action. Full-plan gaps use the
mechanically scored plan and certified reference; relative gap is undefined
when the reference objective is zero.

The plan validator implements explicit timers independently of the optimizer's
compact switch-event constraints. It checks transitions, dwell, yellow/all-red,
queue recurrence, and objective. Illegal actions, wrong length, refusals,
truncated output, and failed calls are recorded as failures without repairs.
Exhaustively enumerate all action sequences on tiny instances and cross-check
both forced-action objectives, including busy initial states and ties.

## Reporting and experiment discipline

Report by horizon, family, model, and mode:

- Valid-output rate over all attempts; distinguish legal first actions from
  feasible complete plans.
- Certified first-action regret, optimal-action frequency, ties, and regret
  intervals for uncertified references.
- Full-plan feasibility, absolute objective gap, and relative gap where defined.
- Latency, reported input/output tokens, reported cost, and missing-usage counts,
  retaining failures in denominators.
- Variation across distinct physical instances and repeated calls. Repetitions
  are not independent instances; report their counts separately and retain all
  individual results. Pilot standard deviations are descriptive, not inference.

Freeze prompt/model/objective versions before held-out evaluation. Fingerprint
instances, objective, horizon, prompts, endpoint/model configuration, solver
settings, generator, and source code. Record returned model/provider and call
dates. Persist every attempt, including raw credential-free request/response
bodies and failures. Resume only under an identical manifest. Interrupted
attempts are retained rather than silently billed again. Older 15-second SUMO
runs remain in their original output directories and retain old prompt hashes.

## Milestones

1. **Completed development milestone:** validated single-junction frozen-instance sweep with
   certified first-action regret; deterministic baselines and a small paid
   first-action pilot across Microsoft, Jev, Luna, and Sol. See the
   [pilot results and limitations](horizon-pilot-results.md).
2. Add live full-plan evaluation only where the exact endpoint supports it;
   keep these results separate from the common first-action comparison.
3. Freeze development choices and a held-out set with more independent
   instances, paired comparisons, and repeated calls. Add uncertainty estimates
   at the instance level once sample sizes support them.
4. Extend to connected intersections only after the scoring machinery is
   validated. Change one experimental dimension at a time.

The existing [SUMO evaluation](evaluation.md) remains available for throughput,
all-demand time, completed-only travel/wait, and approach starvation. Its traffic
outcomes complement the optimization study; they do not replace it.
