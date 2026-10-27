"""Reproducibility, signal safety, and optional live SUMO integration."""

import importlib.util
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET

from trafficlab.controllers import FixedTime, GapAdaptive, GurobiSignalMILP, Observation
from trafficlab.runner import observe, run_episode
from trafficlab.scenario import Config, INCOMING, generate_routes
from trafficlab.signals import SignalMachine


class SumoPilotTests(unittest.TestCase):
    def test_seeded_routes_replay_exactly_and_include_both_vehicle_types(self):
        config = Config(seed=7, duration=120)
        with tempfile.TemporaryDirectory() as directory:
            first, second = Path(directory) / "first.xml", Path(directory) / "second.xml"
            count = generate_routes(config, first)
            self.assertEqual(count, generate_routes(config, second))
            self.assertEqual(first.read_bytes(), second.read_bytes())
            root = ET.parse(first).getroot()
            vehicles = root.findall("vehicle")
            self.assertEqual(len(vehicles), count)
            self.assertEqual({vehicle.attrib["type"] for vehicle in vehicles}, {"HDV", "CAV"})
            self.assertEqual(len({vehicle.attrib["id"] for vehicle in vehicles}), count)
            self.assertEqual([float(vehicle.attrib["depart"]) for vehicle in vehicles],
                             sorted(float(vehicle.attrib["depart"]) for vehicle in vehicles))

    def test_signal_minimum_green_yellow_and_all_red(self):
        config = Config(inflow_per_approach=0)
        machine = SignalMachine()
        groups = ("NS", "EW", "NS", "EW")
        self.assertFalse(machine.request("EW", config))
        for _ in range(50):
            machine.advance(0.1, config)
        self.assertTrue(machine.request("EW", config))
        self.assertEqual(machine.state(groups), "yryr")
        for _ in range(30):
            machine.advance(0.1, config)
        self.assertEqual(machine.state(groups), "rrrr")
        for _ in range(20):
            machine.advance(0.1, config)
        self.assertEqual(machine.state(groups), "rGrG")
        self.assertEqual(machine.switches, 1)

    def test_observation_forecasts_arrivals_through_second_fifteen(self):
        connection = SimpleNamespace(
            edge=SimpleNamespace(getLastStepVehicleIDs=lambda edge: ("vehicle",) if edge == INCOMING["N"] else ()),
            vehicle=SimpleNamespace(getLaneID=lambda _: "n_in_0", getLanePosition=lambda _: 58.0,
                                    getSpeed=lambda _: 1.0),
            lane=SimpleNamespace(getLength=lambda _: 100.0),
            simulation=SimpleNamespace(getTime=lambda: 0.0),
        )
        obs = observe(connection, SignalMachine(), Config())
        self.assertEqual(len(obs.arrivals), 15)
        self.assertEqual(obs.arrivals[14], (1, 0))

    def test_adaptive_choice_responds_to_cross_street_queue(self):
        obs = Observation(
            time=10, phase="NS", pending=None, phase_elapsed=10,
            clearance_remaining=0, min_green=5, yellow=3, clearance=5,
            queues={"N": 0, "S": 0, "E": 5, "W": 5},
            approaching={"N": 0, "S": 0, "E": 0, "W": 0},
            arrivals=((0, 0),) * 15, legal_actions=("NS", "EW"),
        )
        self.assertEqual(GapAdaptive().decide(obs), "EW")

    @unittest.skipUnless(importlib.util.find_spec("gurobipy"), "optional Gurobi binding not installed")
    def test_gurobi_choice_responds_to_cross_street_queue(self):
        obs = Observation(
            time=10, phase="NS", pending=None, phase_elapsed=10,
            clearance_remaining=0, min_green=5, yellow=3, clearance=5,
            queues={"N": 0, "S": 0, "E": 5, "W": 5},
            approaching={"N": 0, "S": 0, "E": 0, "W": 0},
            arrivals=((0, 0),) * 15, legal_actions=("NS", "EW"),
        )
        controller = GurobiSignalMILP()
        self.assertEqual(controller.decide(obs), "EW")
        self.assertEqual(controller.last_status, "optimal")

    @unittest.skipUnless(importlib.util.find_spec("gurobipy"), "optional Gurobi binding not installed")
    def test_yellow_service_can_change_the_optimal_first_action(self):
        obs = Observation(
            time=10, phase="NS", pending=None, phase_elapsed=10,
            clearance_remaining=0, min_green=5, yellow=3, clearance=5,
            queues={"N": 1, "S": 0, "E": 5, "W": 0},
            approaching={"N": 0, "S": 0, "E": 0, "W": 0},
            arrivals=((0, 0),) * 15, legal_actions=("NS", "EW"),
        )
        controller = GurobiSignalMILP()
        with patch("trafficlab.controllers.YELLOW_SERVICE_CAPACITY", 0.0):
            self.assertEqual(controller.decide(obs), "NS")
        self.assertEqual(controller.decide(obs), "EW")

    @unittest.skipUnless(importlib.util.find_spec("gurobipy"), "optional Gurobi binding not installed")
    def test_gurobi_skips_optimization_when_only_one_action_is_legal(self):
        obs = Observation(
            time=0, phase="NS", pending=None, phase_elapsed=0,
            clearance_remaining=0, min_green=5, yellow=3, clearance=5,
            queues={"N": 0, "S": 0, "E": 5, "W": 5},
            approaching={"N": 0, "S": 0, "E": 0, "W": 0},
            arrivals=((0, 0),) * 15, legal_actions=("NS",),
        )
        controller = GurobiSignalMILP()
        self.assertEqual(controller.decide(obs), "NS")
        self.assertEqual(controller.last_status, "forced")

    @unittest.skipUnless(os.environ.get("RUN_SUMO_INTEGRATION") == "1", "set RUN_SUMO_INTEGRATION=1 for live SUMO")
    def test_live_sumo_matched_demand_and_vehicle_accounting(self):
        config = Config(seed=8, duration=40)
        with tempfile.TemporaryDirectory() as directory:
            fixed = run_episode(config, FixedTime(), Path(directory))
            adaptive = run_episode(config, GapAdaptive(), Path(directory))
        self.assertEqual(fixed.generated, adaptive.generated)
        for result in (fixed, adaptive):
            self.assertEqual(result.generated, result.departed + result.entry_backlog)
            self.assertEqual(result.departed, result.completed + result.active)
            self.assertEqual(result.colliding_vehicles, 0)
            self.assertGreater(result.completed, 0)
            self.assertEqual(result.evaluation["unfinished"], result.active + result.entry_backlog)
            self.assertGreater(result.evaluation["total_time_in_system"], 0)
            self.assertEqual(sum(row["completed"] for row in result.evaluation["by_approach"].values()),
                             result.completed)

    @unittest.skipUnless(os.environ.get("RUN_SUMO_INTEGRATION") == "1", "set RUN_SUMO_INTEGRATION=1 for live SUMO")
    def test_live_never_switch_controller_exposes_starved_approaches(self):
        controller = SimpleNamespace(name="never-switch", decide=lambda observation: "NS")
        with tempfile.TemporaryDirectory() as directory:
            result = run_episode(Config(seed=7, duration=120.0), controller, Path(directory))
        self.assertEqual(result.switches, 0)
        self.assertEqual(result.completed, 33)
        self.assertEqual(result.evaluation["unfinished"], 45)
        for approach in ("E", "W"):
            self.assertEqual(result.evaluation["by_approach"][approach]["completed"], 0)
        self.assertGreater(result.evaluation["mean_time_in_system"], 40)


if __name__ == "__main__":
    unittest.main()
