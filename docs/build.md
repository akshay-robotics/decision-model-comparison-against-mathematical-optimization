# Run the SUMO intersection pilot

The first build uses **Eclipse SUMO 1.28.0** for vehicle movement and traffic-signal behavior. Python controls the signals through TraCI, generates seeded routes, records metrics, and renders an interactive replay of actual SUMO vehicle positions in a local browser. The native SUMO-GUI is also supported where an X display is available. This is a one-junction, straight-route, signal-only pilot with Gurobi, three OpenRouter Decisions models, and GPT-6.1 Sol medium reasoning. The paper's joint signal and CAV control and second connected junction remain future work.

## Environment

Use Python 3.9 or newer. From the repository root:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -e .
.venv/bin/python -m pip install gurobipy
.venv/bin/python -m unittest discover -s tests -v
```

The last package is needed only for the Gurobi controller; use a Python environment with access to your existing Gurobi license. In this workspace, `.venv` has SUMO, TraCI, and `gurobipy`, and the pilot MILP solved successfully. The official [SUMO installation guide](https://sumo.dlr.de/docs/Installing/) also documents system installations and the `SUMO_HOME` setting.

## Run and inspect

```sh
.venv/bin/python scripts/build_network.py
.venv/bin/python -m trafficlab --controller all --duration 300 --seeds 7 8 9 --output results/pilot.jsonl
.venv/bin/python -m trafficlab --web --port 8765
```

Open `http://127.0.0.1:8765/` for the browser replay. The page starts a SUMO/TraCI episode on load and plays its recorded positions automatically. The **Signal controller** dropdown selects fixed time, gap adaptive, Gurobi, Microsoft-Decision-1, Jev 1.13, GPT-6 Luna Decisions, or GPT-6.1 Sol medium reasoning. Selecting a controller runs it once for the current parameters, then switching back loads its saved replay without rerunning SUMO. Runs are cached in the page and under ignored `results/web-cache/`, so a page refresh also reuses them. Editing seed, inflow, or CAV share requires a new run for each selected controller; press **Run SUMO**. The metrics identify the controller and seed that produced them. Play, step, and scrub inspect the saved trajectory. If the page reports that the local server is unavailable, run the `--web` command above again and refresh the tab. The browser replay uses actual SUMO output; it does not simulate vehicle movement in JavaScript. The preview is limited to 120 simulated seconds so controller changes respond quickly. Batch runs can use longer durations.

To use the remote controllers, create an OpenRouter API key with available credits. Set `OPENROUTER_API_KEY` in the server environment, or copy `.env.example` to a project-root `.env` and put the key there. The `.env` file is ignored by Git. For the environment-variable approach:

```sh
export OPENROUTER_API_KEY="your-key"
.venv/bin/python -m trafficlab --web --port 8765
```

Check a configured key without making a billable model request:

```sh
.venv/bin/python scripts/check_openrouter_key.py
```

The key stays server-side and is never sent to the browser. Microsoft, Jev, and Luna use OpenRouter's [Decisions API](https://openrouter.ai/docs/api/api-reference/alphadecisions/submit-a-decisions-request) with a typed NS/EW choice. Their requests share one payload builder, so only the model ID changes. GPT-6.1 Sol uses OpenRouter's [chat completions API](https://openrouter.ai/docs/api/api-reference/chat/send-chat-completion-request) with `reasoning_effort=medium` and a strict JSON choice schema; its user message contains the exact same state object and question text. The API envelope differs, so Sol is a matched-task chat comparator, not another Decisions endpoint. All five controllers consume the **same compact projection**: phase/timers, NS/EW queue totals, the same fifteen-second NS/EW arrival forecast, and legal actions. No approach-level counts are sent in this matched condition. The shared question states the simplified MILP objective: sum of end-of-step NS/EW queues over fifteen one-second steps plus 0.5 per phase switch, with modeled service capacities of two vehicles per green second, one vehicle per yellow second for the outgoing group, and zero during all-red. These capacities are pilot assumptions; SUMO determines actual vehicle movement. Controllers skip computation when only one action is legal. `--controller microsoft-rich` adds approach-level queue and approaching counts as a **separate exploratory condition**; do not mix its results with the matched comparison.

An invalid response or API failure ends the run with an error; it is never silently labeled as a model result. Each successful run records the returned model/provider, UTC request times, choices, available probabilities, token usage, and reported cost in its JSON output. OpenRouter credits are consumed only when a new remote run makes API calls; loading a cached replay does not call the model. `--controller all` remains the three local controllers to avoid accidental paid runs. To reproduce the current five-controller comparison, run:

```sh
.venv/bin/python experiments/compare_matched.py --seeds 7 8 9 --duration 120
```

The script verifies that each paired seed generated identical SUMO route files and writes detailed rows, replays, and a Markdown report to ignored `results/matched-five-model/`. The [earlier Microsoft-only pilot](matched-pilot.md) used a different 10-step, zero-yellow-service planning model; do not pool its results with the current run.

For native SUMO-GUI on macOS, install the official SUMO package and XQuartz, then run one controller and seed. `SUMO_HOME` selects the system installation instead of the Python wheel:

```sh
SUMO_HOME=/Library/Frameworks/EclipseSUMO.framework/Versions/Current/EclipseSUMO/share/sumo \
  .venv/bin/python -m trafficlab --controller gurobi --duration 120 --seeds 7 --gui --speed 2
```

The runner reads the XQuartz launchd display when `DISPLAY` is unset, which can start XQuartz on demand. If the display is unavailable immediately after installation, log out and back in as the [SUMO macOS guide](https://sumo.dlr.de/docs/Installing/) advises. The native SUMO 1.28.0 package and XQuartz 2.8.6 are installed on the development Mac; a project episode completed through SUMO-GUI and TraCI, and the intersection was opened in the native app. SUMO's headless binary and the browser replay do not need XQuartz.

## Scenario and measurements

The committed plain XML node, edge, and connection files in `scenarios/single/` produce a four-way network with one incoming and outgoing lane per arm and straight routes only. `scripts/build_network.py` regenerates the committed `.net.xml` with `netconvert`. Traffic demand is sampled once per approach from seeded exponential interarrival times and reused exactly across controllers. Inflow is specified in vehicles per second **per approach**. SUMO handles blocked departures; the summary reports generated, departed, completed, active, and entry backlog separately.

HDVs use SUMO's Krauss car-following model with `sigma=0.5`; CAVs use Krauss with `sigma=0`. Both types share vehicle length, maximum speed, acceleration, deceleration, headway, and a fixed speed factor. These are pilot assumptions, not car-following parameters claimed by TR2023-059. SUMO's [vehicle type documentation](https://sumo.dlr.de/docs/Definition_of_Vehicles%2C_Vehicle_Types%2C_and_Routes.html) describes Krauss as its default car-following model.

The signal controllers receive only visible incoming vehicles. Fixed-time changes its desired phase every 20 seconds. The adaptive controller compares incoming queue pressure. The Gurobi pilot MILP minimizes predicted aggregate queue length over fifteen 1-second steps, with minimum green and transition timing; it is **not** the paper's joint signal/CAV MILP. The remote controllers receive the same compact observation and question comparing staying against switching under the same queue objective, including yellow and all-red service. The question instructs a switch only for a strictly lower predicted objective and a stay on a tie; this does not certify that a remote model finds the MILP optimum. The execution layer enforces a 5-second minimum green, 3-second yellow, and 2-second all-red clearance for every controller.

Results in `results/` are ignored by Git. JSONL rows record the full configuration, SUMO version, demand accounting, completed-trip travel and waiting times from SUMO tripinfo, colliding-vehicle count, signal switches, end-to-end controller decision times, deadline misses, and solver status/gap summary. Travel and waiting means include **completed trips only**. SUMO tripinfo waiting time counts stopped time generally; a signal-specific attribution rule remains to be implemented for direct comparison with the paper. Fuel is omitted until a validated model and reporting protocol are chosen. Batch simulations pause while decisions are computed; deadline misses are measured, but a wall-clock advancing deadline experiment is a later milestone.

Run the live SUMO integration test with:

```sh
RUN_SUMO_INTEGRATION=1 .venv/bin/python -m unittest discover -s tests -v
```
