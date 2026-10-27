"""Signal transition rules and safe SUMO red/yellow/green state mapping."""

from dataclasses import dataclass
from typing import Optional, Sequence

from .scenario import Config


@dataclass
class SignalMachine:
    phase: str = "NS"
    age: float = 0.0
    stage: str = "GREEN"
    remaining: float = 0.0
    pending: Optional[str] = None
    switches: int = 0
    rejected_actions: int = 0

    def legal_actions(self, config: Config):
        if self.stage != "GREEN" or self.age + 1e-9 < config.min_green:
            return (self.phase,)
        return ("NS", "EW")

    def request(self, desired: str, config: Config) -> bool:
        if desired == self.phase or desired == self.pending:
            return True
        if desired not in self.legal_actions(config):
            self.rejected_actions += 1
            return False
        self.pending = desired
        self.stage = "YELLOW"
        self.remaining = config.yellow
        self.switches += 1
        return True

    def advance(self, dt: float, config: Config) -> None:
        if self.stage == "GREEN":
            self.age += dt
            return
        self.remaining = max(0.0, self.remaining - dt)
        if self.remaining > 1e-8:
            return
        if self.stage == "YELLOW":
            self.stage = "ALL_RED"
            self.remaining = config.all_red
        else:
            self.stage = "GREEN"
            self.phase = self.pending
            self.pending = None
            self.age = 0.0

    def clearance_remaining(self, config: Config) -> float:
        if self.stage == "YELLOW":
            return self.remaining + config.all_red
        if self.stage == "ALL_RED":
            return self.remaining
        return 0.0

    def state(self, controlled_groups: Sequence[str]) -> str:
        result = []
        for group in controlled_groups:
            if self.stage == "ALL_RED" or group != self.phase:
                result.append("r")
            elif self.stage == "YELLOW":
                result.append("y")
            else:
                result.append("G")
        return "".join(result)
