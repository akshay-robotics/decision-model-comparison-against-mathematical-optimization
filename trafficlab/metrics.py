"""Fixed-horizon accounting that includes unfinished and uninserted demand."""

from pathlib import Path
import defusedxml.ElementTree as ET

from .scenario import APPROACHES, ROOT


def evaluate_demand(route_file: Path, tripinfo_file: Path, horizon: float) -> dict:
    """Integrate each scheduled vehicle's time until arrival or the cutoff.

    Entry delay is included. This is observed time in the system, not an
    estimate of eventual trip duration or stopped waiting time. Completed-only
    tripinfo files suffice: all other scheduled vehicles accrue time to cutoff.
    """
    demand = {node.attrib["id"]: float(node.attrib["depart"])
              for node in ET.parse(route_file).getroot().iter("vehicle")}
    arrivals = {node.attrib["id"]: float(node.attrib["arrival"])
                for node in ET.parse(tripinfo_file).getroot().iter("tripinfo")
                if 0 <= float(node.attrib["arrival"]) <= horizon}
    if not arrivals.keys() <= demand.keys():
        raise ValueError("tripinfo contains vehicles outside the scheduled demand")
    approaches = {name: {"generated": 0, "completed": 0, "unfinished": 0}
                  for name in APPROACHES}
    total = 0.0
    for vehicle_id, scheduled in demand.items():
        total += max(0.0, arrivals.get(vehicle_id, horizon) - scheduled)
        counts = approaches[vehicle_id.split("_", 1)[0]]
        counts["generated"] += 1
        counts["completed"] += int(vehicle_id in arrivals)
        counts["unfinished"] += int(vehicle_id not in arrivals)
    return {
        "version": 1,
        "horizon_seconds": horizon,
        "completion_percent": round(100 * len(arrivals) / len(demand), 3) if demand else None,
        "unfinished": len(demand) - len(arrivals),
        "total_time_in_system": round(total, 3),
        "mean_time_in_system": round(total / len(demand), 3) if demand else None,
        "by_approach": approaches,
    }


def add_evaluation(result: dict) -> dict:
    """Enrich saved results without rerunning controllers or spending API credits.

    Preserve older replays if their source artifacts are unavailable; callers
    must display unavailable metrics rather than substitute completed means.
    """
    if result.get("evaluation", {}).get("version") == 1:
        return result
    if not result.get("route_file") or not result.get("tripinfo_file"):
        return result
    route_file = ROOT / result["route_file"]
    tripinfo_file = ROOT / result["tripinfo_file"]
    if not route_file.is_file() or not tripinfo_file.is_file():
        return result
    config = result["config"]
    horizon = round(config["duration"] / config["dt"]) * config["dt"]
    evaluation = evaluate_demand(route_file, tripinfo_file, horizon)
    counts = evaluation["by_approach"].values()
    if (sum(row["generated"] for row in counts) != result["generated"]
            or sum(row["completed"] for row in counts) != result["completed"]):
        raise ValueError("evaluation artifacts do not match saved vehicle counts")
    return dict(result, evaluation=evaluation)
