"""Versioned queue objective and independent, executable plan specification."""

from dataclasses import asdict, dataclass, replace
import hashlib
import itertools
import json
import math


PROTOCOL = "frozen-queue-v1"
PHASES = ("NS", "EW")


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                     allow_nan=False).encode()).hexdigest()


@dataclass(frozen=True)
class Objective:
    version: str = "end-step-queues-plus-switches-v1"
    green_capacity: float = 2.0
    yellow_capacity: float = 1.0
    switch_penalty: float = 0.5
    step_seconds: int = 1
    # Defaults retain compatibility with historical v1 instance records.
    terminal_queue_penalty: float = 0.0

    def __post_init__(self):
        if self.step_seconds != 1 or any(not math.isfinite(x) or x < 0 for x in
                (self.green_capacity, self.yellow_capacity, self.switch_penalty, self.terminal_queue_penalty)):
            raise ValueError("objective requires one-second steps and finite nonnegative parameters")


CURRENT_OBJECTIVE = Objective(version="end-step-queues-plus-terminal-v2", terminal_queue_penalty=10.0)


@dataclass(frozen=True)
class Instance:
    case_id: str
    family: str
    seed: int
    horizon: int
    queues: tuple
    arrivals: tuple
    phase: str = "NS"
    age: int = 5
    pending: str = None
    remaining: int = 0
    min_green: int = 5
    yellow: int = 3
    all_red: int = 2
    objective: Objective = CURRENT_OBJECTIVE

    def __post_init__(self):
        if any(type(x) is not int or x < 1 for x in
               (self.horizon, self.min_green, self.yellow, self.all_red)):
            raise ValueError("horizon and signal durations must be positive integer seconds")
        if self.phase not in PHASES or type(self.age) is not int or self.age < 0:
            raise ValueError("invalid initial phase or age")
        if type(self.remaining) is not int or not 0 <= self.remaining <= self.yellow + self.all_red:
            raise ValueError("invalid remaining clearance")
        if bool(self.pending) != bool(self.remaining) or (self.pending and self.pending not in PHASES):
            raise ValueError("pending phase and remaining clearance must agree")
        if self.pending == self.phase:
            raise ValueError("pending phase must differ from outgoing phase")
        if len(self.arrivals) != self.horizon:
            raise ValueError("forecast must supply exactly one arrival row for every horizon step")
        for row in (self.queues, *self.arrivals):
            if len(row) != 2 or any(isinstance(x, bool) or not isinstance(x, (int, float))
                                  or not math.isfinite(x) or x < 0 for x in row):
                raise ValueError("queues and arrivals must be finite nonnegative NS/EW pairs")
        object.__setattr__(self, "queues", tuple(self.queues))
        object.__setattr__(self, "arrivals", tuple(tuple(row) for row in self.arrivals))

    def record(self):
        data = asdict(self)
        if self.objective.version == "end-step-queues-plus-switches-v1" and self.objective.terminal_queue_penalty == 0:
            del data['objective']['terminal_queue_penalty']
        return data

    @property
    def identity(self):
        return fingerprint({"protocol": PROTOCOL, "instance": self.record()})

    @property
    def legal_actions(self):
        return (self.phase,) if self.pending or self.age < self.min_green else PHASES

    def prefix(self, horizon):
        if not 1 <= horizon <= self.horizon:
            raise ValueError("prefix exceeds supplied forecast")
        return replace(self, horizon=horizon, arrivals=self.arrivals[:horizon])

    def observation(self):
        from ..controllers import Observation
        return Observation(time=0, phase=self.phase, pending=self.pending, phase_elapsed=self.age,
            clearance_remaining=self.remaining, min_green=self.min_green, yellow=self.yellow,
            clearance=self.yellow + self.all_red,
            queues={"N": self.queues[0], "S": 0, "E": self.queues[1], "W": 0},
            approaching={a: 0 for a in ("N", "S", "E", "W")},
            arrivals=self.arrivals, legal_actions=self.legal_actions)


def validate_plan(instance, plan):
    """Score a complete schedule with explicit timers, independent of MILP flow.

    One desired phase per second. During clearance the only accepted token is
    the outgoing current phase (a no-op); no repairs or implicit truncation.
    """
    if not isinstance(plan, (list, tuple)) or len(plan) != instance.horizon:
        return {"feasible": False, "error": "plan must contain exactly horizon actions"}
    phase, age = instance.phase, instance.age
    pending, remaining = instance.pending, instance.remaining
    queues = list(instance.queues)
    trace, cost, switches = [], 0.0, 0
    for t, action in enumerate(plan):
        legal = (phase,) if pending or age < instance.min_green else PHASES
        if action not in legal:
            return {"feasible": False, "error": f"illegal action at step {t}: {action!r}", "step": t}
        if action != phase:
            pending, remaining = action, instance.yellow + instance.all_red
            switches += 1
        capacity = (instance.objective.yellow_capacity if remaining > instance.all_red else 0.0
                    ) if pending else instance.objective.green_capacity
        for g, name in enumerate(PHASES):
            available = queues[g] + instance.arrivals[t][g]
            queues[g] = max(0.0, available - (capacity if name == phase else 0.0))
        cost += sum(queues)
        trace.append({"step": t, "phase": phase, "pending": pending,
                      "remaining": remaining, "age": age, "queues": list(queues)})
        if pending:
            remaining -= 1
            if remaining == 0:
                phase, pending, age = pending, None, 0
        else:
            age += 1
    terminal_cost = instance.objective.terminal_queue_penalty * sum(queues)
    return {"feasible": True, "objective": cost + instance.objective.switch_penalty * switches + terminal_cost,
            "queue_cost": cost, "terminal_cost": terminal_cost, "terminal_queues": list(queues),
            "switches": switches, "trace": trace}


def enumerate_optimum(instance, forced_first=None):
    """Exhaustive test oracle only; refuses combinatorial production instances."""
    if instance.horizon > 12:
        raise ValueError("exhaustive enumeration is limited to 12 steps")
    best = None
    for plan in itertools.product(PHASES, repeat=instance.horizon):
        if forced_first is not None and plan[0] != forced_first:
            continue
        scored = validate_plan(instance, plan)
        if scored["feasible"] and (best is None or scored["objective"] < best["objective"]):
            best = dict(scored, plan=list(plan))
    return best
