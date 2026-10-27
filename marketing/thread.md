# Five-post X thread

Prepared copy; no posts have been published. Attachments are listed separately so filenames do not enter the post text.

## Post 1

1/5 Can decision models control traffic lights as well as an optimizer?

I compared Microsoft, Jev, Luna and Sol with Gurobi in SUMO. A key lesson: a good average can hide unfinished cars.

An early planning-horizon experiment 🧵

---

## Post 2

2/5 Same 78-car demand, seed and signal constraints. Same observation format, forecast construction and objective.

Each controller chooses NS or EW. The featured run uses a 15-second planning horizon and 120 simulated seconds. States diverge after different choices.

---

## Post 3

3/5 Completed-only travel time excludes cars that never finish.

We report completed/total, cars remaining, approach coverage and time in the system for ALL generated cars through the cutoff. Traffic outcomes and optimization quality are separate tests.

---

## Post 4

4/5 I changed one term:

queue cost + 0.5 × switches
→ add 10 × the final modeled queue.

The same revised objective went to Gurobi and every model. The penalty values queues left at the planning boundary; it does not directly reward completed SUMO trips.

---

## Post 5

5/5 Completed/78: Gurobi 64→65, Sol 64→65, Jev 66→60, Microsoft 54→53, Luna 54→58.

Changing the objective changed behavior, but did not improve every controller.

One seed; one run per condition. Next: more seeds, harder cases and a new frozen optimization benchmark.

## Attachment order

1. `media/demo.mp4`
2. `media/01-experiment-overview.png`
3. Text only
4. `media/03-objective-explained.png`
5. `media/02-before-after-results.png`

See `alt-text.md` for descriptions. Every post fits a 280-character budget; release validation accounts for the Unicode punctuation used here. Add the real repository URL after publication and recheck the post length.
