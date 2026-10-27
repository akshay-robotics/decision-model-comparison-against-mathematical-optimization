"""Seeded SUMO demand and network locations for the single-junction pilot."""

from dataclasses import asdict, dataclass
import math
from pathlib import Path
import random
import xml.etree.ElementTree as ET


ROOT = Path(__file__).resolve().parents[1]
NETWORK = ROOT / "scenarios" / "single" / "junction.net.xml"
APPROACHES = ("N", "S", "E", "W")
INCOMING = {"N": "n_in", "S": "s_in", "E": "e_in", "W": "w_in"}
GROUP = {"N": "NS", "S": "NS", "E": "EW", "W": "EW"}
ROUTES = {"N": ("n2s", "n_in s_out"), "S": ("s2n", "s_in n_out"),
          "E": ("e2w", "e_in w_out"), "W": ("w2e", "w_in e_out")}


@dataclass(frozen=True)
class Config:
    seed: int = 7
    duration: float = 300.0
    planning_horizon: int = 15
    dt: float = 0.1
    decision_interval: float = 1.0
    inflow_per_approach: float = 0.15
    cav_share: float = 0.5
    min_green: float = 5.0
    yellow: float = 3.0
    all_red: float = 2.0

    def __post_init__(self):
        if type(self.planning_horizon) is not int or not 1 <= self.planning_horizon <= 600:
            raise ValueError("planning_horizon must be an integer from 1 to 600 seconds")
        values = (self.duration, self.dt, self.decision_interval, self.inflow_per_approach,
                  self.cav_share, self.min_green, self.yellow, self.all_red)
        if not all(math.isfinite(value) for value in values):
            raise ValueError("configuration values must be finite")
        if self.seed < 0 or min(self.duration, self.dt, self.decision_interval,
                                self.min_green, self.yellow, self.all_red) <= 0:
            raise ValueError("seed must be nonnegative and time parameters positive")
        ratio = self.decision_interval / self.dt
        if ratio < 1 or abs(ratio - round(ratio)) > 1e-8:
            raise ValueError("decision_interval must be a multiple of dt")
        if not 0 <= self.inflow_per_approach <= 2 or not 0 <= self.cav_share <= 1:
            raise ValueError("inflow or cav_share out of range")

    def record(self) -> dict:
        return asdict(self)


def generate_routes(config: Config, path: Path) -> int:
    """Write one deterministic demand realization, shared by all controllers."""
    rng = random.Random(config.seed)
    vehicles = []
    if config.inflow_per_approach:
        for approach in APPROACHES:
            at = rng.expovariate(config.inflow_per_approach)
            sequence = 0
            while at < config.duration:
                kind = "CAV" if rng.random() < config.cav_share else "HDV"
                vehicles.append((at, approach, kind, sequence))
                sequence += 1
                at += rng.expovariate(config.inflow_per_approach)
    vehicles.sort(key=lambda item: (item[0], item[1], item[3]))
    root = ET.Element("routes")
    # The same input vehicle mix is replayed for every signal controller.
    # SUMO's Krauss model represents HDV movement; sigma controls its random
    # imperfection. CAVs use zero dawdling in this signal-only pilot.
    ET.SubElement(root, "vType", id="HDV", vClass="passenger", carFollowModel="Krauss",
                  accel="2.0", decel="3.5", sigma="0.5", tau="1.1", length="4.5",
                  minGap="2.5", maxSpeed="13.0", speedFactor="1.0", speedDev="0",
                  color="70,175,250")
    ET.SubElement(root, "vType", id="CAV", vClass="passenger", carFollowModel="Krauss",
                  accel="2.0", decel="3.5", sigma="0.0", tau="1.1", length="4.5",
                  minGap="2.5", maxSpeed="13.0", speedFactor="1.0", speedDev="0",
                  color="250,175,85")
    for route_id, edges in ROUTES.values():
        ET.SubElement(root, "route", id=route_id, edges=edges)
    for at, approach, kind, sequence in vehicles:
        ET.SubElement(root, "vehicle", id=f"{approach}_{sequence:05d}", type=kind,
                      route=ROUTES[approach][0], depart=f"{at:.3f}")
    ET.indent(root, space="    ")
    path.parent.mkdir(parents=True, exist_ok=True)
    ET.ElementTree(root).write(path, encoding="utf-8", xml_declaration=True)
    return len(vehicles)
