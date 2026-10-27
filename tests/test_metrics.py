"""Regression coverage for completed-trip selection bias."""

import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from trafficlab.metrics import evaluate_demand
from trafficlab.benchmark.problem import CURRENT_OBJECTIVE
from trafficlab.scenario import Config
from trafficlab.web import cached_episode


class DemandMetricsTests(unittest.TestCase):
    def test_starving_cross_street_cannot_hide_unfinished_or_entry_delay(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            routes, trips = root / "routes.xml", root / "trips.xml"
            routes.write_text('<routes><vehicle id="N_0" depart="0"/>'
                              '<vehicle id="E_0" depart="0"/>'
                              '<vehicle id="W_0" depart="20"/></routes>')
            # Only the fast northbound trip arrives. East is still on-road;
            # west never enters. Neither has a completed tripinfo entry.
            trips.write_text('<tripinfos><tripinfo id="N_0" depart="2" '
                             'arrival="10" duration="8"/></tripinfos>')
            starving = evaluate_demand(routes, trips, 100)
            self.assertEqual(starving["total_time_in_system"], 190)
            self.assertEqual(starving["unfinished"], 2)
            self.assertEqual(starving["by_approach"]["E"]["completed"], 0)
            self.assertEqual(starving["by_approach"]["W"]["unfinished"], 1)
            # All three trips are slower individually, yet the network serves
            # everyone and incurs far less total elapsed time.
            trips.write_text('<tripinfos><tripinfo id="N_0" arrival="30"/>'
                             '<tripinfo id="E_0" arrival="30"/>'
                             '<tripinfo id="W_0" arrival="50"/></tripinfos>')
            served = evaluate_demand(routes, trips, 100)
            self.assertEqual(served["total_time_in_system"], 90)
            self.assertLess(served["mean_time_in_system"], starving["mean_time_in_system"])
            self.assertEqual(served["completion_percent"], 100)

    def test_no_completed_trips_and_empty_demand(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            routes, trips = root / "routes.xml", root / "trips.xml"
            routes.write_text('<routes><vehicle id="E_0" depart="10"/></routes>')
            trips.write_text('<tripinfos><tripinfo id="E_0" arrival="-1"/></tripinfos>')
            result = evaluate_demand(routes, trips, 100)
            self.assertEqual(result["mean_time_in_system"], 90)
            self.assertEqual(result["completion_percent"], 0)
            routes.write_text('<routes/>')
            trips.write_text('<tripinfos/>')
            result = evaluate_demand(routes, trips, 100)
            self.assertIsNone(result["mean_time_in_system"])
            self.assertIsNone(result["completion_percent"])
            self.assertEqual(result["total_time_in_system"], 0)

    def test_old_cache_gets_metrics_without_rerunning_model(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            routes, trips, replay = root / "routes.xml", root / "trips.xml", root / "replay.json"
            routes.write_text('<routes><vehicle id="E_0" depart="10"/></routes>')
            trips.write_text('<tripinfos/>')
            config = Config(duration=100.0)
            replay.write_text(json.dumps({"result": {
                "controller": "luna", "config": config.record(), "generated": 1, "completed": 0,
                "planning_objective": CURRENT_OBJECTIVE.__dict__,
                "route_file": str(routes), "tripinfo_file": str(trips)}, "frames": []}))
            with patch("trafficlab.web.cache_path", return_value=replay), \
                    patch("trafficlab.web.make_controller") as make:
                data = cached_episode("luna", config)
                make.assert_not_called()
            self.assertTrue(data["cache_hit"])
            self.assertEqual(data["result"]["evaluation"]["mean_time_in_system"], 90)


if __name__ == "__main__":
    unittest.main()
