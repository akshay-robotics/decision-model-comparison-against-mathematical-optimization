# Traffic outcomes at a fixed cutoff

Completed-trip travel and stopped-wait averages omit cars that never finish.
A controller that permanently holds north–south green can therefore appear
fast while starving east–west demand. These averages are diagnostic only.

The replay and matched report show completion out of generated demand,
unfinished demand including entry backlog, and completion by approach.
The headline completion score is `100 × completed / generated` (higher is
better). Every unfinished car reduces the score by `100 / generated` percentage
points, whether it is on the road or blocked from entering. With no demand,
the score is unavailable. For the same scenario, Luna scores 42.3% versus
82.1% for Gurobi; low completed-trip travel time cannot compensate for this
completion shortfall. The display shows total completed cars separately.
The primary time measure is mean observed time in system across **all generated
cars**, including those blocked from entering:

`sum(max(0, min(arrival, cutoff) - scheduled_departure)) / generated`

For a car that has not arrived, substitute the cutoff for arrival. Scheduled
departure comes from the demand XML, so insertion delay counts too. The cutoff
is the actual number of simulation steps times the step length. Total time is
measured in vehicle-seconds; dividing by generated demand gives seconds/car.
Zero-demand means are unavailable, not zero.

Compare this measure only with identical demand and cutoff. For a fixed demand
set, delaying a car's arrival cannot reduce its contribution. This prevents
unfinished cars from disappearing from the average. It remains a finite-window
measure, not eventual travel time or stopped waiting time, and must be read
alongside throughput and approach coverage. No arbitrary terminal penalty or
forced signal intervention is applied to a controller's decisions.

Saved runs can be evaluated from route XML and completed-trip arrival times;
no new model calls are needed. Older caches missing those artifacts retain
their replay and show unavailable all-demand metrics. New episodes include an
`evaluation` object in the result. Batch reports refreshed with `--resume`
include the same accounting (missing episodes will still be run).

In the saved seed-7 matched repeat (120 seconds, 78 generated cars), Luna
completed 33 cars and no east–west trips. It left 31 cars active and 14 in entry
backlog. Its completed-only mean travel was 15.1 seconds, but mean observed time
in system was 44.315 seconds/car, compared with 28.274 for Gurobi and 25.978 for
Jev. These are one episode's outcomes, not a general model ranking.
