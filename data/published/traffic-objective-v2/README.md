# Published pilot data

Ten episodes: five controllers under each of two objectives. Experiment date:
October 21, 2026. Every episode has identical seed-7 demand (78 cars), 120
simulated seconds, a 15-second planning horizon, and the same signal timings.
There is one episode per condition/model and one independent demand seed.

- `episodes.csv`: scalar results for plotting and comparison.
- `episodes.json`: full selected summaries, objective/configuration, model IDs,
  provider labels, approach coverage, and solver status summaries.
- `replays.json`: five revised-objective position traces and scheduled-departure/
  arrival times used for browser counters. Synthetic vehicle IDs carry no personal data.
- `prompts.json`: exact original v7 and revised v8 questions plus actual first
  request bodies for each remote model. No authorization headers are included.
- `metadata.json`: source-run manifests, settings, budgets, and metric definitions.
- `checksums.json`: SHA-256 values for the files in this directory.
- `source-snapshots.json`: manifest-verified core fingerprints for the archives below.

Original: sum of end-of-step queues + 0.5 per switch. Revised: add 10 times
the final modeled NS/EW queue, once. The coefficient was fixed before rerunning.
Queue discharge and SUMO trip completion are different quantities.

System time includes every generated vehicle from scheduled departure until
arrival or cutoff. Travel/wait means include completed trips only. All-demand
system time is observed through a finite cutoff, not eventual journey time.
SUMO pauses during model computation; latency is not added to traffic delay.
Reported costs are provider usage values, not estimates of future pricing.

## Historical code snapshots

The three ZIP archives contain the exact experimental core Python files,
verified against their original run-manifest source fingerprints. Added
packaging files include network XML, dependency metadata, license, and a small
standalone `reproduce.py` driver. `snapshot.json` distinguishes these additions
from the fingerprinted files.

Packaging was reviewed before publication: local paths in the network's
generated comment were removed, and packaging requires Python 3.11+ with
patched build tools. These changes do not alter the experimental core or
network geometry. The archives preserve historical code, including older web
handlers; use only their standalone reproduction driver in an isolated local
environment. Use the current repository for browser serving and current
credential protections.

- `source-original-remote.zip`: original v7 remote-controller experiment core.
- `source-original-gurobi.zip`: original Gurobi core with the v2 numerical
  tolerances used for the published baseline.
- `source-terminal.zip`: revised objective and v8 question, exactly as run.

For example, extract the revised snapshot, install its dependencies, and run
the local baseline without any API calls:

```sh
python3 -m zipfile -e data/published/traffic-objective-v2/source-terminal.zip /tmp/traffic-terminal
cd /tmp/traffic-terminal
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -e '.[gurobi]'
.venv/bin/python reproduce.py --controllers gurobi --output-dir new-local-results
```

Gurobi requires a usable license. Explicitly selecting remote controllers makes
paid calls and requires `OPENROUTER_API_KEY` in that extracted project's
environment or `.env`. The driver defaults to Gurobi only and refuses an
existing output directory. To reproduce original conditions, use the matching
original archive and controller selection. Model aliases and stochastic
responses can change; exact remote result repetition is not guaranteed.

No revised-objective frozen optimization benchmark is included or claimed.
The raw local result directories, credentials, third-party papers, model
weights, and dependency binaries are excluded. Original exported project data
and source use the root MIT license; dependencies retain their own licenses.
