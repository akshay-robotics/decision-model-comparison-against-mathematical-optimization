"""Controllers sharing the same signal-only observation and action space."""

from dataclasses import asdict, dataclass
import math
from typing import Dict, Optional, Tuple
from .benchmark.problem import CURRENT_OBJECTIVE


MODEL_HORIZON = 15
GROUP_SERVICE_CAPACITY = CURRENT_OBJECTIVE.green_capacity
YELLOW_SERVICE_CAPACITY = CURRENT_OBJECTIVE.yellow_capacity
SWITCH_PENALTY = CURRENT_OBJECTIVE.switch_penalty
TERMINAL_QUEUE_PENALTY = CURRENT_OBJECTIVE.terminal_queue_penalty


@dataclass(frozen=True)
class Observation:
    time: float
    phase: str
    pending: Optional[str]
    phase_elapsed: float
    clearance_remaining: float
    min_green: float
    yellow: float
    clearance: float
    queues: Dict[str, int]
    approaching: Dict[str, int]
    arrivals: Tuple[Tuple[int, int], ...]
    legal_actions: Tuple[str, ...]


@dataclass(frozen=True)
class MatchedObservation:
    """Exactly the aggregate state shared by the MILP and decision model."""

    planning_horizon_seconds: int
    simulation_time_seconds: float
    current_phase: str
    pending_phase: Optional[str]
    phase_elapsed_seconds: float
    clearance_remaining_seconds: float
    min_green_seconds: float
    yellow_seconds: float
    switch_clearance_seconds: float
    queue_totals: Dict[str, int]
    arrivals_forecast_NS_EW: Tuple[Tuple[int, int], ...]
    legal_actions: Tuple[str, ...]

    def record(self) -> dict:
        return asdict(self)


def matched_observation(observation: Observation) -> MatchedObservation:
    """Project the SUMO observation without approach-level information."""
    return MatchedObservation(
        planning_horizon_seconds=len(observation.arrivals),
        simulation_time_seconds=observation.time,
        current_phase=observation.phase,
        pending_phase=observation.pending,
        phase_elapsed_seconds=observation.phase_elapsed,
        clearance_remaining_seconds=observation.clearance_remaining,
        min_green_seconds=observation.min_green,
        yellow_seconds=observation.yellow,
        switch_clearance_seconds=observation.clearance,
        queue_totals={
            "NS": observation.queues["N"] + observation.queues["S"],
            "EW": observation.queues["E"] + observation.queues["W"],
        },
        arrivals_forecast_NS_EW=observation.arrivals,
        legal_actions=observation.legal_actions,
    )


class FixedTime:
    name = "fixed"

    def __init__(self, green_seconds: float = 20.0) -> None:
        self.green_seconds = green_seconds

    def decide(self, observation: Observation) -> str:
        desired = "NS" if int(observation.time / self.green_seconds) % 2 == 0 else "EW"
        return desired if desired in observation.legal_actions else observation.phase


class GapAdaptive:
    name = "adaptive"

    def decide(self, observation: Observation) -> str:
        current = observation.phase
        other = "EW" if current == "NS" else "NS"
        if other not in observation.legal_actions:
            return current
        pressure = {
            "NS": sum(observation.queues[a] + 0.5 * observation.approaching[a] for a in ("N", "S")),
            "EW": sum(observation.queues[a] + 0.5 * observation.approaching[a] for a in ("E", "W")),
        }
        return other if pressure[other] > pressure[current] + 1 else current


class GurobiSignalMILP:
    """Aggregate queue MILP with dwell and clearance automaton.

    This is a deliberately simplified signal-only pilot, not the paper's joint
    vehicle-and-signal MILP. Future arrivals are inferred only from vehicles in
    the public observation; hidden demand is not supplied to the optimizer.
    """

    name = "gurobi"

    def __init__(self, horizon: int = MODEL_HORIZON, time_limit: float = 0.8) -> None:
        try:
            import gurobipy as gp
        except ImportError as exc:
            raise RuntimeError("Gurobi controller requires gurobipy; install the optional 'gurobi' extra") from exc
        if type(horizon) is not int or horizon < 1:
            raise ValueError("horizon must be a positive integer")
        self.gp = gp
        self.environment = gp.Env(empty=True)
        self.environment.setParam("OutputFlag", 0)
        self.environment.start()
        self.horizon = horizon
        self.time_limit = time_limit
        self.last_status = None
        self.last_gap = None

    def decide(self, obs: Observation) -> str:
        if len(obs.arrivals) != self.horizon:
            raise ValueError("controller horizon and forecast length differ; no zero padding is allowed")
        matched = matched_observation(obs)
        if len(matched.legal_actions) == 1:
            self.last_status = "forced"
            self.last_gap = None
            return matched.legal_actions[0]
        from .benchmark.problem import Instance, Objective
        from .benchmark.reference import ReferenceSolver
        instance = Instance(
            case_id="sumo-observation", family="closed-loop", seed=0, horizon=self.horizon,
            queues=(matched.queue_totals['NS'], matched.queue_totals['EW']),
            arrivals=matched.arrivals_forecast_NS_EW, phase=matched.current_phase,
            age=int(matched.phase_elapsed_seconds + 1e-9), pending=matched.pending_phase,
            remaining=math.ceil(matched.clearance_remaining_seconds),
            min_green=max(1, math.ceil(matched.min_green_seconds)),
            yellow=max(1, math.ceil(matched.yellow_seconds)),
            all_red=max(1, math.ceil(matched.switch_clearance_seconds - matched.yellow_seconds)),
            objective=Objective(green_capacity=GROUP_SERVICE_CAPACITY,
                                yellow_capacity=YELLOW_SERVICE_CAPACITY, switch_penalty=SWITCH_PENALTY,
                                version=CURRENT_OBJECTIVE.version, terminal_queue_penalty=TERMINAL_QUEUE_PENALTY))
        self.last_reference = ReferenceSolver(self.time_limit, self.environment).solve(instance)
        self.last_status = self.last_reference['status']
        self.last_gap = self.last_reference['gap']
        if self.last_reference['plan'] is None:
            return matched.current_phase
        return self.last_reference['plan'][0]


def make_controller(name: str, horizon: int = MODEL_HORIZON):
    if name == "fixed":
        return FixedTime()
    if name == "adaptive":
        return GapAdaptive()
    if name == "gurobi":
        return GurobiSignalMILP(horizon=horizon)
    if name in ("microsoft", "jev", "luna"):
        from .openrouter import OpenRouterDecisions
        return OpenRouterDecisions(name=name, horizon=horizon)
    if name == "sol-medium":
        from .sol import SolMediumReasoning
        return SolMediumReasoning(horizon=horizon)
    if name == "microsoft-rich":
        from .openrouter import MicrosoftDecisions
        return MicrosoftDecisions(information_mode="rich", horizon=horizon)
    raise ValueError("controller must be fixed, adaptive, gurobi, microsoft, jev, luna, sol-medium, or microsoft-rich")
