# Matched-information pilot: Gurobi versus Microsoft Decisions

On October 11, 2026, both controllers ran the same one-junction SUMO scenario for demand seeds 7, 8, and 9. Each episode lasted 120 simulated seconds with 0.15 vehicles/s per approach, 50% CAVs, 0.1-second SUMO steps, and one-second controller updates. The paired route files were byte-identical for every seed. This is a small pilot, not the paper's five-intersection or joint signal/CAV experiment.

This report records the earlier 10-step, zero-service-during-yellow planning assumptions. Current code uses a 15-step horizon and reduced modeled service during yellow; its results should be evaluated as a separate run, not compared as if the models were unchanged.

Both controllers used the same projected observation: current phase and timing, NS/EW queue totals, the same ten-step NS/EW arrival forecast, and legal signal actions. The objective was the sum of both queues at the ends of steps 1–10 plus 0.5 for every initiated switch. A green group could serve up to two vehicles per second; switching started a five-second no-service yellow/all-red clearance immediately, and minimum green was five seconds. Gurobi solved the aggregate queue MILP; Microsoft-Decision-1 selected a typed action from a question stating that model. No approach-level queues or approaching counts were sent to Microsoft. The optional `microsoft-rich` controller adds those counts for a separately labeled information-ablation experiment and was **not** included here.

| Seed | Controller | Travel time (s) | Waiting time (s) | Completed | Active | Entry backlog | Switches | Choice p95 (ms) | Missed 1 s deadlines |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 7 | Gurobi | 24.53 | 2.89 | 64 | 14 | 0 | 6 | 5.82 | 0 |
| 7 | Microsoft | 40.54 | 9.46 | 52 | 26 | 0 | 12 | 699.45 | 0 |
| 8 | Gurobi | 25.39 | 3.70 | 57 | 18 | 0 | 8 | 6.04 | 0 |
| 8 | Microsoft | 27.10 | 5.12 | 50 | 25 | 0 | 9 | 468.57 | 0 |
| 9 | Gurobi | 25.86 | 2.99 | 54 | 22 | 2 | 9 | 6.15 | 0 |
| 9 | Microsoft | 32.55 | 6.85 | 44 | 31 | 3 | 11 | 1698.50 | 1 |

Across the three matched seeds, the unweighted mean paired difference (Microsoft minus Gurobi) was **+8.14 s travel time, +3.95 s waiting time, −9.67 completed trips, +0.33 entry backlog, and +3 switches**. Microsoft missed one measured one-second decision deadline; Gurobi missed none. Choice p95 includes only updates where both actions were legal, avoiding dilution by forced green/clearance ticks. The Microsoft run made 72 paid decisions, with $0.001258 reported API cost. OpenRouter returned model `microsoft/microsoft-decision-1-20261009` through Azure. Gurobi reported optimal solves with worst model gap 0.0; that certifies this simplified MILP, **not** optimal traffic behavior in SUMO.

Travel and waiting means are for **completed trips only**. The differing active-vehicle counts can bias those means, so completed trips, active vehicles, and entry backlog should be read together. The simulation pauses during controller computation; deadline misses record decision latency but do not yet measure the effect of a late action in a wall-clock advancing simulation. Three seeds cannot support a general performance claim, and Microsoft responses can vary across repeated calls. The primary research comparison still needs more seeds and a frozen protocol.

Reproduce this pilot with:

```sh
.venv/bin/python experiments/compare_matched.py --seeds 7 8 9 --duration 120
```

The generated `results/paired-matched/report.md`, `runs.jsonl`, SUMO route files, tripinfo, and replay JSON files are local artifacts ignored by Git. The script checks byte-identical demand between each Gurobi/Microsoft pair.
