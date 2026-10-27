"""SUMO/TraCI experiment loop for the single-junction signal pilot."""

from dataclasses import asdict, dataclass
import json
import math
import os
from pathlib import Path
import shutil
import statistics
import subprocess
import sys
import time
from typing import Dict, List, Optional
import defusedxml.ElementTree as ET

from .controllers import MODEL_HORIZON, Observation, CURRENT_OBJECTIVE
from .metrics import evaluate_demand
from .scenario import APPROACHES, Config, GROUP, INCOMING, NETWORK, ROOT, generate_routes
from .signals import SignalMachine


def sumo_binary(gui: bool = False) -> str:
    name = "sumo-gui" if gui else "sumo"
    home = os.environ.get("SUMO_HOME")
    if home and (Path(home) / "bin" / name).is_file():
        return str(Path(home) / "bin" / name)
    try:
        import sumo
        candidate = Path(sumo.SUMO_HOME) / "bin" / name
        if candidate.is_file():
            return str(candidate)
    except ImportError:
        pass
    found = shutil.which(name)
    if found:
        return found
    raise RuntimeError(f"{name} is unavailable; install Eclipse SUMO or set SUMO_HOME")


def ensure_gui_display() -> None:
    if sys.platform != "darwin" or os.environ.get("DISPLAY"):
        return
    try:
        result = subprocess.run(
            ["launchctl", "print", f"gui/{os.getuid()}/org.xquartz.startx"],
            capture_output=True, text=True, check=False, timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired):
        result = None
    if result and result.returncode == 0:
        for line in result.stdout.splitlines():
            if line.strip().startswith("DISPLAY => "):
                os.environ["DISPLAY"] = line.split("=>", 1)[1].strip()
                break
    if not os.environ.get("DISPLAY"):
        raise RuntimeError("SUMO-GUI needs XQuartz on macOS; install it and log out/in, or set DISPLAY")


def controlled_groups(connection, signal_id: str) -> List[str]:
    links = connection.trafficlight.getControlledLinks(signal_id)
    groups = []
    for index, alternatives in enumerate(links):
        if not alternatives:
            raise RuntimeError(f"traffic-light link {index} has no incoming lane")
        lane = alternatives[0][0]
        approach = lane[0].upper()
        if approach not in GROUP or not lane.startswith(INCOMING[approach] + "_"):
            raise RuntimeError(f"unexpected controlled lane: {lane}")
        groups.append(GROUP[approach])
    if set(groups) != {"NS", "EW"}:
        raise RuntimeError("the network must include both signal groups")
    return groups


def observe(connection, machine: SignalMachine, config: Config, horizon: Optional[int] = None) -> Observation:
    horizon = config.planning_horizon if horizon is None else horizon
    if horizon != config.planning_horizon:
        raise ValueError("observation horizon must match scenario planning_horizon")
    queues = {approach: 0 for approach in APPROACHES}
    approaching = {approach: 0 for approach in APPROACHES}
    predicted = [[0, 0] for _ in range(horizon)]
    for approach in APPROACHES:
        for vehicle_id in connection.edge.getLastStepVehicleIDs(INCOMING[approach]):
            lane_id = connection.vehicle.getLaneID(vehicle_id)
            distance = max(0.0, connection.lane.getLength(lane_id) - connection.vehicle.getLanePosition(vehicle_id))
            speed = connection.vehicle.getSpeed(vehicle_id)
            if speed < 0.5 or distance <= 10.0:
                queues[approach] += 1
            else:
                approaching[approach] += 1
                slot = int(distance / max(speed, 3.0))
                if slot < horizon:
                    predicted[slot][0 if GROUP[approach] == "NS" else 1] += 1
    return Observation(
        time=connection.simulation.getTime(), phase=machine.phase, pending=machine.pending,
        phase_elapsed=machine.age, clearance_remaining=machine.clearance_remaining(config),
        min_green=config.min_green, yellow=config.yellow,
        clearance=config.yellow + config.all_red,
        queues=queues, approaching=approaching,
        arrivals=tuple(tuple(row) for row in predicted),
        legal_actions=machine.legal_actions(config),
    )


def percentile(values: List[float], share: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, math.ceil(share * len(ordered)) - 1)]


def display_path(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


@dataclass
class RunResult:
    controller: str
    config: dict
    sumo_version: str
    generated: int
    departed: int
    completed: int
    active: int
    entry_backlog: int
    colliding_vehicles: int
    mean_travel_time: Optional[float]
    mean_waiting_time: Optional[float]
    switches: int
    rejected_actions: int
    mean_decision_ms: float
    p95_decision_ms: float
    max_decision_ms: float
    choice_updates: int
    mean_choice_ms: float
    p95_choice_ms: float
    max_choice_ms: float
    deadline_misses: int
    solver_status_counts: Dict[str, int]
    worst_solver_gap: Optional[float]
    decision_model: Optional[dict]
    route_file: str
    tripinfo_file: str
    trace_file: Optional[str]
    evaluation: dict
    planning_objective: Optional[dict] = None

    def record(self) -> dict:
        return asdict(self)


def run_episode(config: Config, controller, output_dir: Path = ROOT / "results" / "single",
                gui: bool = False, playback_speed: float = 1.0,
                trace_file: Optional[Path] = None) -> RunResult:
    if getattr(controller, "horizon", config.planning_horizon) != config.planning_horizon:
        raise ValueError("controller horizon must match the scenario planning_horizon")
    try:
        import traci
    except ImportError as exc:
        raise RuntimeError("TraCI is unavailable; install the 'sumo' project extra") from exc
    if gui and playback_speed <= 0:
        raise ValueError("playback_speed must be positive")
    if gui:
        ensure_gui_display()
    if not NETWORK.is_file():
        raise RuntimeError("SUMO network is missing; rebuild it with scripts/build_network.py")
    output_dir.mkdir(parents=True, exist_ok=True)
    route_file = output_dir / f"demand_seed{config.seed}.rou.xml"
    tripinfo_file = output_dir / f"tripinfo_{controller.name}_seed{config.seed}.xml"
    generated = generate_routes(config, route_file)
    command = [
        sumo_binary(gui), "-n", str(NETWORK), "-r", str(route_file),
        "--step-length", str(config.dt), "--seed", str(config.seed),
        "--tripinfo-output", str(tripinfo_file),
        "--no-step-log", "true", "--duration-log.disable", "true",
        "--time-to-teleport", "-1", "--collision.action", "warn",
    ]
    if gui:
        command.extend(["--start", "true"])
    label = f"{controller.name}-{config.seed}-{time.time_ns()}"
    traci.start(command, label=label)
    connection = traci.getConnection(label)
    machine = SignalMachine()
    timings: List[float] = []
    choice_timings: List[float] = []
    solver_status: Dict[str, int] = {}
    solver_gaps: List[float] = []
    departed = set()
    arrived = set()
    collided = set()
    deadline_misses = 0
    active = 0
    frames = []
    version = connection.getVersion()[1]
    try:
        signal_ids = connection.trafficlight.getIDList()
        if signal_ids != ("C",) and list(signal_ids) != ["C"]:
            raise RuntimeError(f"expected one C traffic light, found {signal_ids}")
        link_groups = controlled_groups(connection, "C")
        current_state = None
        step_count = round(config.duration / config.dt)
        decision_every = round(config.decision_interval / config.dt)
        for step in range(step_count):
            if step % decision_every == 0:
                began = time.perf_counter()
                observation = observe(connection, machine, config)
                action = controller.decide(observation)
                machine.request(action, config)
                requested_state = machine.state(link_groups)
                if requested_state != current_state:
                    connection.trafficlight.setRedYellowGreenState("C", requested_state)
                    current_state = requested_state
                elapsed = (time.perf_counter() - began) * 1000
                timings.append(elapsed)
                if len(observation.legal_actions) > 1:
                    choice_timings.append(elapsed)
                deadline_misses += int(elapsed > 1000 * config.decision_interval)
                status = getattr(controller, "last_status", None)
                if status is not None:
                    solver_status[status] = solver_status.get(status, 0) + 1
                gap = getattr(controller, "last_gap", None)
                if gap is not None:
                    solver_gaps.append(gap)
            requested_state = machine.state(link_groups)
            if requested_state != current_state:
                connection.trafficlight.setRedYellowGreenState("C", requested_state)
                current_state = requested_state
            connection.simulationStep()
            departed.update(connection.simulation.getDepartedIDList())
            arrived.update(connection.simulation.getArrivedIDList())
            collided.update(connection.simulation.getCollidingVehiclesIDList())
            applied_signal = machine.stage if machine.stage != "GREEN" else machine.phase
            machine.advance(config.dt, config)
            if trace_file is not None and step % max(1, round(0.5 / config.dt)) == 0:
                vehicles = []
                for vehicle_id in sorted(connection.vehicle.getIDList()):
                    x, y = connection.vehicle.getPosition(vehicle_id)
                    vehicles.append({"x": round(x, 2), "y": round(y, 2),
                                     "kind": connection.vehicle.getTypeID(vehicle_id)})
                frames.append({
                    "time": round(connection.simulation.getTime(), 2),
                    "signal": applied_signal,
                    "vehicles": vehicles, "completed": len(arrived),
                    "entry_backlog": generated - len(departed),
                })
            if gui:
                time.sleep(config.dt / playback_speed)
        active = connection.vehicle.getIDCount()
    finally:
        connection.close()
    tripinfos = [node for node in ET.parse(tripinfo_file).getroot().iter("tripinfo")]
    travel = [float(node.attrib["duration"]) for node in tripinfos]
    wait = [float(node.attrib["waitingTime"]) for node in tripinfos]
    result = RunResult(
        controller=controller.name, config=config.record(), sumo_version=version,
        generated=generated, departed=len(departed), completed=len(arrived), active=active,
        entry_backlog=generated - len(departed), colliding_vehicles=len(collided),
        mean_travel_time=round(statistics.mean(travel), 3) if travel else None,
        mean_waiting_time=round(statistics.mean(wait), 3) if wait else None,
        switches=machine.switches, rejected_actions=machine.rejected_actions,
        mean_decision_ms=round(statistics.mean(timings), 3) if timings else 0.0,
        p95_decision_ms=round(percentile(timings, 0.95), 3),
        max_decision_ms=round(max(timings), 3) if timings else 0.0,
        choice_updates=len(choice_timings),
        mean_choice_ms=round(statistics.mean(choice_timings), 3) if choice_timings else 0.0,
        p95_choice_ms=round(percentile(choice_timings, 0.95), 3),
        max_choice_ms=round(max(choice_timings), 3) if choice_timings else 0.0,
        deadline_misses=deadline_misses, solver_status_counts=solver_status,
        worst_solver_gap=max(solver_gaps) if solver_gaps else None,
        decision_model=controller.metadata() if hasattr(controller, "metadata") else None,
        route_file=display_path(route_file),
        tripinfo_file=display_path(tripinfo_file),
        trace_file=display_path(trace_file) if trace_file is not None else None,
        evaluation=evaluate_demand(route_file, tripinfo_file, step_count * config.dt),
        planning_objective=asdict(CURRENT_OBJECTIVE) if controller.name not in ('fixed', 'adaptive') else None,
    )
    if trace_file is not None:
        trace_file.parent.mkdir(parents=True, exist_ok=True)
        trace_file.write_text(json.dumps({"result": result.record(), "frames": frames}), encoding="utf-8")
    return result
