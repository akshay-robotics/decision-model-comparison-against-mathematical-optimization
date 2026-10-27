# Project plan: decision models versus traffic coordination MILP

**Primary reference:** Suriyarachchi, Quirynen, Baras, and Di Cairano, *Optimization-based Coordination and Control of Traffic Lights and Mixed Traffic in Multi-Intersection Environments*, MERL TR2023-059 / ACC 2023. [Publication](https://www.merl.com/publications/TR2023-059).

**Status:** A [runnable one-junction SUMO pilot](build.md) now includes seeded traffic, fixed-time and adaptive signals, a Gurobi signal MILP, Microsoft, Jev, and Luna Decisions adapters, GPT-6.1 Sol medium reasoning, batch runs, and cached browser replay of SUMO trajectories. The [earlier three-seed Microsoft-only pilot](matched-pilot.md) used different planning assumptions; a fresh matched five-controller comparison uses the current 15-step model. These are pilots, not a formal benchmark. The owner has a Gurobi license. The primary reference supersedes TR2024-123, which concerns individual-vehicle MIQP planning.

## What the reference actually does

The paper jointly computes traffic-signal states and connected automated vehicle (CAV) target velocities and lane changes using a receding-horizon MILP. Human-driven vehicles (HDVs) are predicted to stop at red lights, follow leading vehicles, or travel at their desired speed, subject to acceleration limits. Signal-state compatibility, switching timers, intersection occupancy, and vehicle separation enter the constraints.

Equation (21) maximizes vehicle progress over the horizon while penalizing deviation from preferred lanes, unnecessary lane changes, and constraint slack. Fuel consumption is an evaluation outcome; it is not an explicit fuel term in this objective.

Two architectures are compared: a centralized controller for the whole network and decentralized controllers for individual intersections. Each CAV is commanded by at most one intersection controller, while neighboring controllers can predict its behavior during handover.

The study uses five connected intersections, three lanes per direction, 100 m between adjacent intersection centers, a 15 m/s speed limit, and a target control frequency of 1 Hz. Implementation is Matlab/Gurobi with SUMO. Our smaller SUMO/TraCI environment is a simplified adaptation, not a direct reproduction.

## Research question and scope

How closely can zero-shot Jev, GPT-6 Luna, Microsoft-Decision-1, and GPT-6.1 Sol medium-reasoning choices match optimization-based traffic coordination under equal observations and action authority? Deadline behavior is reported separately because SUMO pauses during computation.

**Recommended sequence:** validate one four-way intersection first, then use two connected four-way intersections for the coordination benchmark. The second junction should share traffic with the first, allowing downstream queues and spillback; a separate T-junction would test geometry transfer instead. Two junctions are a proposed reduced-scale study, not the paper's five-junction setup.

Start with one lane per direction, straight routes, and two compatible movement groups per junction. Extend lane counts and turns only after validation. Build mixed traffic with configurable CAV share. Keep the two control tracks explicit:

- **Signal-only pilot:** every controller selects compatible signal states; all vehicles use the same driving rules. This isolates signal decisions and does not reproduce joint CAV control.
- **Joint-control study:** add bounded CAV speed commands while HDVs retain their behavioral model. Use a small, documented library of joint signal/speed actions shared by Jev, Luna, Microsoft-Decision-1, and the action-restricted optimizer. A full continuous-control MILP can be reported separately as a stronger reference; its performance difference also includes action-discretization effects. Candidate generation must not use hidden optimizer scores or answers.

Use fixed-time and gap-based adaptive signals as the paper-aligned baselines. Compare centralized Gurobi, decentralized Gurobi once two junctions exist, Jev, Luna, Microsoft-Decision-1, and GPT-6.1 Sol medium reasoning. Separate architecture comparisons from model comparisons so information access and command authority remain matched. Route all four remote models through OpenRouter with explicit model IDs; the first three use its Decisions API, while Sol uses chat completions with a strict choice schema. The question text, objective, legal choices, and state are shared; the API envelope differs for Sol and should be labeled in results. Log returned model/provider, request date, billed tokens, and any provider/model revision information. Microsoft says its model weights are updated continually, so record this limitation when interpreting runs across dates.

## SUMO scenario and visualization

Use SUMO's 0.1-second simulation steps and 1-second TraCI controller updates. Signal updates obey minimum dwell, yellow, and all-red clearance rules; an update does not imply a signal change. The pilot began with a 10-step optimizer horizon and now uses 15 steps; compare 5/10/15 steps explicitly with 1-second planning intervals in our adaptation.

Vehicles follow predefined SUMO routes, car-following and traffic-light rules. HDVs use a documented Krauss parameterization; CAVs currently use a lower-noise variant, with no speed commands yet. SUMO retains blocked departures, which are reported as entry backlog. Use seeded arrival schedules, initially Poisson, with balanced demand before adding asymmetric and bursty traffic. Document these vehicle choices as pilot assumptions rather than attributes of the reference paper.

Separate the SUMO scenario, TraCI controller interface, and visualization. Controllers receive the same state, prediction assumptions, legal actions, and objective description. Freeze zero-shot prompts before held-out evaluation. A shared execution layer validates actions and handles stale responses, failures, and timeouts; log interventions separately from requested decisions.

Use the native SUMO-GUI where an X display is available and provide a local browser replay of recorded SUMO vehicle positions elsewhere. The browser view has CAV/HDV colors, signal state, pause, step, speed, scrubbing, and matched-seed controller replays. Rendering speed does not affect SUMO dynamics or benchmark timing.

Validate vehicle accounting, conflicting-signal exclusion, collision counts, clearance, and deterministic demand replay before drawing performance conclusions. When the second intersection is added, test downstream blocking and spillback. Measure physical violations separately from optimizer slack and execution-layer overrides.

## Evaluation

Use the paper's Section V-B metrics as the foundation:

| Metric | Planned measurement |
| --- | --- |
| Average travel time per vehicle | Entry-to-exit duration; report unfinished trips and entry backlogs separately |
| Average waiting time at signals per vehicle | Define and freeze the stopped-speed threshold and signal-wait attribution |
| Average fuel consumption per vehicle | Include only with a documented, validated fuel model; otherwise label idle time and acceleration-based measures as proxies |
| Computation time | Mean plus p50/p95/p99/max, end-to-end API latency, and deadline misses |
| Decentralized computation | Mean over updates of the slowest intersection solve, and mean of summed solve times; also measure actual wall time and overhead |

The paper evaluates 2,000-second simulations while varying inflow (0.24/0.48/0.72 veh/s), CAV share (20/50/80%), and horizon length (5/10/15 steps). Adapt demand to our smaller lane capacity and explicitly specify whether inflow is per entry or network-wide. Its average runtime results do not establish worst-case deadline guarantees.

Add throughput, maximum wait, collisions/near-conflicts, fallback rates, and cost. Use identical arrival schedules across controllers, paired comparisons across seeds, and a declared drain period/cutoff. Start with 20 pilot episodes, then 100 held-out episodes across selected conditions; scale only as uncertainty warrants.

For frozen-state action comparisons, force each candidate first action in the same finite-horizon optimizer and reoptimize the continuation. Call the difference action regret only when the reference solves are certified to the declared tolerance; otherwise report bounds. Closed-loop performance versus Gurobi is a baseline difference, not a certificate of global optimality. Record objective, bound, solve status, and gap.

Separate paused-simulation quality tests from deadline-aware tests that advance simulation during computation. Include observation serialization, network delay, solver model updates, and action validation in latency. Log model identifiers, prompts, seeds, package versions, and solver settings.

## Milestones and suggestions

1. **One-junction pilot:** validate Gurobi access; build the SUMO network, TraCI loop, replay, fixed-time and gap-based controls; validate a simplified signal MILP. The initial build is runnable; calibration and broader evaluation remain.
2. **Decision-model comparison:** the Microsoft, Jev, Luna, and Sol medium-reasoning signal-only adapters are implemented with the same action interface; complete paired pilot quality tests and then freeze prompts and seeds for a larger study.
3. **Coordination extension:** connect a second junction, implement controller handover/downstream predictions, and add joint CAV speed decisions with matched action authority.
4. **Evaluation and report:** compare traffic efficiency, computation, failure cases, and sensitivity; publish seeds, configurations, logs, and reproduction commands.

Allow roughly two working weeks for a validated one-junction pilot, then reassess effort for joint control and the connected-junction study. Fuel-model validation and full multi-lane reproduction are separate scope additions.

Follow the [decision-model access and credit plan](jev-access-and-credits.md) while simulator work proceeds. [JevLight](https://github.com/usail-hkust/JevLight) remains related signal-control work; the intended contribution is the comparison with constrained optimization, mixed traffic, and decision deadlines. API availability and prices remain documented separately. The repository README presents the published pilot and its limitations.
