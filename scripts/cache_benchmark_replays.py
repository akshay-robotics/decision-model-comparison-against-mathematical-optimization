"""Copy completed benchmark replays into the browser's parameter-aware cache."""

import argparse
import json
from pathlib import Path
import shutil
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from trafficlab.openrouter import DECISION_MODELS, prompt_sha256
from trafficlab.scenario import Config
from trafficlab.sol import SOL_MODEL
from trafficlab.web import cache_path
from trafficlab.benchmark.problem import CURRENT_OBJECTIVE


MODELS = {**DECISION_MODELS, "sol-medium": SOL_MODEL}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path, help="directory containing runs.jsonl and seed replays")
    args = parser.parse_args()
    count = 0
    for line in (args.source / "runs.jsonl").read_text(encoding="utf-8").splitlines():
        row = json.loads(line)
        name = row["controller"]
        config = Config(**row["config"])
        source = args.source / f"seed{config.seed}" / name / "replay.json"
        data = json.loads(source.read_text(encoding="utf-8"))
        if data["result"]["controller"] != name or data["result"]["config"] != config.record():
            raise RuntimeError(f"{source}: replay metadata does not match the run")
        if name in {'gurobi', *MODELS} and data['result'].get('planning_objective') != CURRENT_OBJECTIVE.__dict__:
            raise RuntimeError(f"{source}: planning objective does not match the current browser")
        if name in MODELS:
            metadata = data["result"]["decision_model"]
            if metadata["prompt_sha256"] != prompt_sha256(config.planning_horizon) or metadata["requested_model"] != MODELS[name]:
                raise RuntimeError(f"{source}: remote-model protocol does not match current browser")
        target = cache_path(name, config)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        count += 1
    print(f"Cached {count} completed replay(s) for the browser")


if __name__ == "__main__":
    main()
