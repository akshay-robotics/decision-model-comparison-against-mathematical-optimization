"""Run Gurobi and three Decisions models on identical seeded SUMO demand."""

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import statistics
import sys


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from trafficlab.controllers import (GROUP_SERVICE_CAPACITY, MODEL_HORIZON,
                                    SWITCH_PENALTY, YELLOW_SERVICE_CAPACITY, TERMINAL_QUEUE_PENALTY,
                                    make_controller)
from trafficlab.openrouter import DECISION_MODELS, PROMPT_SHA256, PROMPT_VERSION, prompt_sha256
from trafficlab.runner import run_episode
from trafficlab.metrics import add_evaluation
from trafficlab.scenario import Config, ROOT
from trafficlab.sol import SOL_MODEL


REMOTE_MODELS = {**DECISION_MODELS, "sol-medium": SOL_MODEL}
CONTROLLERS = ("gurobi", *REMOTE_MODELS)
FIELDS = (
    ("mean_travel_time", "Travel s (completed only)"),
    ("mean_waiting_time", "Wait s (completed only)"),
    ("completed", "Completed"),
    ("active", "Active"),
    ("entry_backlog", "Backlog"),
    ("switches", "Switches"),
    ("mean_decision_ms", "Mean decision ms"),
    ("p95_decision_ms", "P95 decision ms"),
    ("deadline_misses", "Missed 1 s"),
)
CHOICE_FIELDS = (
    ("choice_updates", "Choice updates"),
    ("mean_choice_ms", "Mean choice ms"),
    ("p95_choice_ms", "P95 choice ms"),
    ("max_choice_ms", "Max choice ms"),
)


def display(value):
    if value is None:
        return "—"
    if isinstance(value, float):
        return f"{value:.2f}"
    return str(value)


def report_markdown(rows, config, seeds, route_hashes):
    rows = [add_evaluation(row) for row in rows]
    header = "| Seed | Controller | " + " | ".join(label for _, label in FIELDS) + " |"
    divider = "| --- | --- | " + " | ".join("---:" for _ in FIELDS) + " |"
    lines = [
        "# Matched-information SUMO comparison",
        "",
        f"Report generated (UTC): {datetime.now(timezone.utc).isoformat()}. Seeds: {', '.join(map(str, seeds))}. "
        f"Duration: {config.duration:g} simulated seconds; inflow: {config.inflow_per_approach:g} "
        f"vehicles/s/approach; CAV share: {config.cav_share:g}.",
        "",
        "The route XML is byte-identical across controllers for each seed. All five controllers "
        "use the same phase/timing, NS/EW queue totals, arrival forecast, and legal actions. "
        "After different choices, live observation values can diverge. The three Decisions "
        "requests differ only by model ID; Sol medium reasoning uses the same state and exact "
        "question text in a chat JSON envelope with a strict choice schema. The question is identical "
        f"(prompt version `{PROMPT_VERSION}`, SHA-256 `{prompt_sha256(config.planning_horizon)}`). "
        f"The {config.planning_horizon}-step objective minimizes summed end-of-step queues plus "
        f"{SWITCH_PENALTY} per switch and an additional terminal penalty of {TERMINAL_QUEUE_PENALTY:g} "
        "per vehicle remaining in the final NS/EW queues. "
        f"Service capacity is {GROUP_SERVICE_CAPACITY:g}/s "
        f"during green, {YELLOW_SERVICE_CAPACITY:g}/s for the outgoing group during yellow, "
        "and zero during all-red. These are planning assumptions; SUMO determines real flow.",
        "",
    ]
    lines.extend([
        "## All-demand outcomes through the cutoff", "",
        "Completion score is completed / generated × 100 (higher is better). Every unfinished car "
        "lowers this score, including entry backlog. Time in system counts every generated car from scheduled departure until arrival or the "
        "simulation cutoff, including entry backlog. Lower is better for identical demand and cutoff. "
        "It is observed time, not eventual travel time; also compare completion and approach coverage. "
        "Completed-trip averages below must not be used alone to rank controllers.", "",
        "| Seed | Controller | Completed / generated | Completion score % ↑ | Unfinished incl. backlog | Mean time in system s | N completed / demand | S | E | W |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ])
    for row in rows:
        evaluation = row.get("evaluation", {})
        approaches = evaluation.get("by_approach", {})
        coverage = [f"{approaches[a]['completed']}/{approaches[a]['generated']}" if a in approaches else "—"
                    for a in ("N", "S", "E", "W")]
        lines.append("| " + " | ".join([
            str(row["config"]["seed"]), row["controller"], f"{row['completed']}/{row['generated']}",
            display(100 * row["completed"] / row["generated"] if row["generated"] else None),
            str(row["generated"] - row["completed"]), display(evaluation.get("mean_time_in_system")),
            *coverage,
        ]) + " |")
    lines.extend(["", "## Completed-trip diagnostics and decision latency", "", header, divider])
    for row in rows:
        lines.append("| " + " | ".join([
            str(row["config"]["seed"]), row["controller"],
            *(display(row[field]) for field, _ in FIELDS),
        ]) + " |")
    luna_rows = [row for row in rows if row["controller"] == "luna"]
    if luna_rows and all(row["switches"] == 0 for row in luna_rows):
        lines.extend(["", "Luna never switched phase in these runs. Its completed-trip travel "
                      "and wait means exclude vehicles left active or in entry backlog and must not "
                      "be interpreted as better overall traffic performance."])
    lines.extend([
        "", "## Latency when both signal actions are legal", "",
        "| Seed | Controller | Choice updates | Mean ms | P95 ms | Max ms |",
        "| --- | --- | ---: | ---: | ---: | ---: |",
    ])
    for row in rows:
        lines.append("| " + " | ".join([
            str(row["config"]["seed"]), row["controller"],
            *(display(row[field]) for field, _ in CHOICE_FIELDS),
        ]) + " |")
    lines.extend(["", "## Mean paired differences versus Gurobi", "",
                  "| Controller | Metric | Mean difference | Pairs |",
                  "| --- | --- | ---: | ---: |"])
    for name in REMOTE_MODELS:
        for field, label in FIELDS + CHOICE_FIELDS:
            values = []
            for seed in seeds:
                pair = {row["controller"]: row for row in rows if row["config"]["seed"] == seed}
                if name in pair and "gurobi" in pair:
                    left, right = pair[name][field], pair["gurobi"][field]
                    if left is not None and right is not None:
                        values.append(left - right)
            lines.append(f"| {name} | {label} | "
                         f"{display(statistics.mean(values)) if values else '—'} | {len(values)} |")
    lines.extend(["", "## Reproducibility", "",
                  "| Seed | Route XML SHA-256 |", "| --- | --- |"])
    for seed in seeds:
        lines.append(f"| {seed} | `{route_hashes[seed]}` |")
    lines.extend(["", "| Controller | Requested model | Returned model(s) | Provider(s) | Calls | Reported cost USD |",
                  "| --- | --- | --- | --- | ---: | ---: |"])
    for name, model in REMOTE_MODELS.items():
        model_rows = [row["decision_model"] for row in rows if row["controller"] == name]
        returned = sorted({record["model"] for row in model_rows for record in row["decisions"]})
        providers = sorted({str(record["provider"]) for row in model_rows for record in row["decisions"]})
        calls = sum(row["request_count"] for row in model_rows)
        cost = sum(row["cost_usd"] for row in model_rows)
        lines.append(f"| {name} | `{model}` | {', '.join(returned)} | "
                     f"{', '.join(providers)} | {calls} | {cost:.6f} |")
    lines.extend([
        "",
        "These are pilot episodes, not a significance test. Travel and waiting means include completed trips "
        "only; active vehicles and entry backlog are reported to expose censoring. SUMO is paused while "
        "decisions are computed. All-update latency includes forced green/clearance ticks; choice latency "
        "includes only ticks when both actions are legal. A measured deadline miss does not yet represent "
        "a wall-clock advancing run. "
        "Gurobi's optimality gap certifies its simplified model solve, not optimal traffic behavior in SUMO.",
        "",
    ])
    return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seeds", type=int, nargs="+", default=[7, 8, 9])
    parser.add_argument("--duration", type=float, default=120.0)
    parser.add_argument("--horizon", type=int, default=15)
    parser.add_argument("--inflow", type=float, default=0.15)
    parser.add_argument("--cav-share", type=float, default=0.5)
    parser.add_argument("--output-dir", type=Path, default=ROOT / "results" / "matched-five-model")
    parser.add_argument("--resume", action="store_true", help="reuse existing matching replays in output-dir")
    args = parser.parse_args()
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    rows = []
    route_hashes = {}
    rows_file = output_dir / "runs.jsonl"
    rows_file.write_text("", encoding="utf-8")
    for seed in args.seeds:
        config = Config(seed=seed, duration=args.duration, planning_horizon=args.horizon,
                        inflow_per_approach=args.inflow, cav_share=args.cav_share)
        routes = []
        for name in CONTROLLERS:
            run_dir = output_dir / f"seed{seed}" / name
            replay_path = run_dir / "replay.json"
            route_path = run_dir / f"demand_seed{seed}.rou.xml"
            resumed = args.resume and replay_path.is_file() and route_path.is_file()
            if resumed:
                data = json.loads(replay_path.read_text(encoding="utf-8"))
                row = data["result"]
                if row["controller"] != name or row["config"] != config.record():
                    raise RuntimeError(f"{name} seed {seed}: saved replay does not match configuration")
                print(f"seed {seed} {name}: reused saved run", flush=True)
            else:
                run = run_episode(config, make_controller(name, horizon=config.planning_horizon), output_dir=run_dir,
                                  trace_file=replay_path)
                row = run.record()
            row["route_file"] = str(route_path.relative_to(ROOT))
            row["tripinfo_file"] = str((run_dir / f"tripinfo_{name}_seed{seed}.xml").relative_to(ROOT))
            row["trace_file"] = str(replay_path.relative_to(ROOT))
            row = add_evaluation(row)
            if resumed:
                data["result"] = row
                replay_path.write_text(json.dumps(data, separators=(",", ":")), encoding="utf-8")
            if name in REMOTE_MODELS:
                metadata = row["decision_model"]
                if metadata["information_mode"] != "matched" or metadata["prompt_sha256"] != prompt_sha256(config.planning_horizon):
                    raise RuntimeError(f"{name}: information or prompt contract changed")
                if metadata["requested_model"] != REMOTE_MODELS[name]:
                    raise RuntimeError(f"{name}: wrong requested model")
                if name == "sol-medium" and metadata.get("reasoning_effort") != "medium":
                    raise RuntimeError("Sol was not run with medium reasoning")
            rows.append(row)
            with rows_file.open("a", encoding="utf-8") as stream:
                stream.write(json.dumps(row, sort_keys=True) + "\n")
            routes.append(hashlib.sha256(route_path.read_bytes()).hexdigest())
            print(f"seed {seed} {name}: completed={row['completed']} wait={display(row['mean_waiting_time'])}s "
                  f"choice_p95={row['p95_choice_ms']:.1f}ms misses={row['deadline_misses']}", flush=True)
        if len(set(routes)) != 1:
            raise RuntimeError(f"seed {seed}: generated demand differs between controllers")
        route_hashes[seed] = routes[0]
        print(f"seed {seed}: demand files match across all five controllers", flush=True)
    report = output_dir / "report.md"
    report.write_text(report_markdown(rows, config, args.seeds, route_hashes), encoding="utf-8")
    print(f"Wrote {report} and {rows_file}", flush=True)


if __name__ == "__main__":
    main()
