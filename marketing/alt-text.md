# Accessible attachment descriptions

## Video — post 1

A 42-second silent browser recording. After a four-second question card, five
saved SUMO traffic replays appear together: Gurobi, Microsoft, Jev 1.13, Luna,
and Sol medium. One simulation clock advances from zero to 120 seconds at four
times speed. Each panel shows completed cars out of 78, remaining total demand,
and mean time in system for cars scheduled so far. A sixth tile explains the
shared revised objective. The final eight seconds show the paired results
chart. The experiment uses one seed, a 15-second planning horizon, and one
episode per model/condition. Playback does not represent model decision latency.

## Experiment overview — post 2

Five controllers share an observation format: NS/EW queues, arrival forecasts,
phase/timers, and legal actions. They choose NS or EW using the same objective
and signal constraints. The featured case has 78 cars, seed 7, 15-second
planning, and 120 simulated seconds. Signal timing is 5 seconds minimum green,
3 yellow, 2 all-red. Actual observations diverge after actions. Traffic outcomes
and optimization quality are separate evaluations; no revised-objective frozen
optimization benchmark has been run.

## Objective explained — post 4

Three terms make up the revised planning cost: the sum of end-of-second NS/EW
queues; 0.5 per initiated signal switch; and 10 per car in the final modeled
queue. The final queue is in the running sum and gets the extra penalty once.
For illustration, three cars left at the planning boundary add 30 cost units.
The weight was fixed before rerunning. This is a modeled-queue penalty, not a
direct count of completed SUMO trips.

## Before/after results — post 5

Paired bars compare original and revised objectives on identical demand.
Completed cars out of 78: Gurobi 64 to 65; Microsoft 54 to 53; Jev 66 to 60;
Luna 54 to 58; Sol 64 to 65. Mean system times in seconds: Gurobi 28.27 to 27.21;
Microsoft 34.85 to 35.35; Jev 24.67 to 28.38; Luna 30.31 to 30.40; Sol 28.27
to 27.21. More completed cars and less system time are desirable. The objective
change did not improve every controller. One seed and one episode per condition
are insufficient for a general or causal performance claim.
