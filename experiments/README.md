# Experiment records

The primary experiment is now the [frozen-instance horizon benchmark](../docs/horizon-benchmark.md),
implemented in [horizon_benchmark.py](horizon_benchmark.py). It compares certified
first-action regret across 15/30/60/120-second horizons, with independently
validated full-plan evaluation kept separate. SUMO traffic scores remain a
secondary closed-loop evaluation; historical results retain their original
prompt versions. See the [research plan](../docs/research-plan.md).

The runnable matched-observation SUMO pilot is [compare_matched.py](compare_matched.py). It compares Gurobi, Microsoft Decisions, Jev, Luna Decisions, and GPT-6.1 Sol medium reasoning on identical seeded route files. The three Decisions models receive identical request bodies except for model ID; Sol receives the exact same state and question text in a chat JSON envelope. Run outputs are ignored under `results/matched-five-model/`; the current pilot and its limitations are documented in `docs/`.

Every study should contain a README and version-controlled configuration sufficient to identify:

| Field | Required information |
| --- | --- |
| Research question | Hypothesis and comparison being tested |
| Code | Git commit and any uncommitted modifications |
| Models | Method names, parameters, and baseline definitions |
| Scenarios | Initial states, traffic behavior, dynamics, and constraints |
| Randomness | Seeds and number of independent trials |
| Environment | Runtime, dependency and solver versions, OS, CPU/GPU, and thread count |
| Solver policy | Time limits, tolerances, warm starts, and fallback behavior |
| Execution | Exact commands from a clean checkout |
| Data | Provenance, license, retrieval location, and checksums |
| Evaluation | Metric definitions, units, aggregation, and failure handling |
| Outputs | Artifact locations, checksums, and analysis commands |
| Limitations | Exclusions, deviations from the protocol, and known issues |

Store generated output under the ignored root `results/` directory during development. Keep compact, intentionally curated summaries and figures with the study when ready for review. Provide a durable retrieval location for large artifacts before claiming reproducibility.
