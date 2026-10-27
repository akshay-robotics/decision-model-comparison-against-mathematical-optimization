"""Decision API contract and browser replay reuse without paid API calls."""

from dataclasses import replace
import json
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from trafficlab.controllers import Observation, matched_observation
from trafficlab.openrouter import (DECISION_MODELS, MATCHED_INSTRUCTIONS, MICROSOFT_MODEL,
                                   OpenRouterDecisions, MicrosoftDecisions, load_api_key,
                                   matched_payload)
from trafficlab.scenario import Config
from trafficlab.sol import SOL_MODEL, SolMediumReasoning, sol_payload
from trafficlab.web import cache_path, cached_episode


def observation(legal=("NS", "EW")):
    return Observation(
        time=10, phase="NS", pending=None, phase_elapsed=10,
        clearance_remaining=0, min_green=5, yellow=3, clearance=5,
        queues={"N": 0, "S": 0, "E": 5, "W": 5},
        approaching={"N": 0, "S": 0, "E": 1, "W": 1},
        arrivals=((0, 1),) * 15, legal_actions=legal,
    )


class DecisionAdapterTests(unittest.TestCase):
    def test_key_loader_prefers_environment_then_gitignored_file(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / ".env"
            path.write_text("OPENROUTER_API_KEY=from-file\n", encoding="utf-8")
            with patch("trafficlab.openrouter.ENV_FILE", path):
                with patch.dict(os.environ, {"OPENROUTER_API_KEY": ""}):
                    self.assertEqual(load_api_key(), "from-file")
                with patch.dict(os.environ, {"OPENROUTER_API_KEY": "from-env"}):
                    self.assertEqual(load_api_key(), "from-env")

    def test_microsoft_choice_uses_typed_legal_actions_and_records_usage(self):
        calls = []

        def transport(payload):
            calls.append(payload)
            return {
                "id": "gen-1", "model": MICROSOFT_MODEL, "provider": "Azure",
                "answers": {"signal": {"type": "choice", "choice": "EW",
                                       "confidence": 0.91, "probabilities": {"NS": 0.09, "EW": 0.91}}},
                "usage": {"input_tokens": 200, "output_tokens": 4, "cost": 0.0000084},
            }

        controller = MicrosoftDecisions(api_key="unit-test", transport=transport)
        self.assertEqual(controller.decide(observation()), "EW")
        self.assertEqual(calls[0]["model"], MICROSOFT_MODEL)
        self.assertEqual(set(calls[0]["questions"]["signal"]["criteria"]), {"NS", "EW"})
        self.assertEqual(calls[0]["state"], matched_observation(observation()).record())
        self.assertEqual(calls[0]["state"]["queue_totals"], {"NS": 0, "EW": 10})
        self.assertEqual(len(calls[0]["state"]["arrivals_forecast_NS_EW"]), 15)
        self.assertNotIn("queues_by_approach", calls[0]["state"])
        self.assertNotIn("approaching_by_approach", calls[0]["state"])
        self.assertIn("plus 0.5", MATCHED_INSTRUCTIONS)
        self.assertIn("15-step plan", MATCHED_INSTRUCTIONS)
        self.assertIn("steps 1 through 15", MATCHED_INSTRUCTIONS)
        self.assertIn("Compare BOTH legal first actions", MATCHED_INSTRUCTIONS)
        self.assertIn("capacity is 2.0 vehicles", MATCHED_INSTRUCTIONS)
        self.assertIn("capacity is 1.0 for the outgoing group", MATCHED_INSTRUCTIONS)
        self.assertIn("strictly lower", MATCHED_INSTRUCTIONS)
        self.assertIn("If the objectives tie, keep current_phase", MATCHED_INSTRUCTIONS)
        self.assertEqual(calls[0]["state"]["yellow_seconds"], 3)
        alternate = replace(observation(), queues={"N": 0, "S": 0, "E": 10, "W": 0},
                            approaching={"N": 3, "S": 2, "E": 0, "W": 0})
        MicrosoftDecisions(api_key="unit-test", transport=transport).decide(alternate)
        self.assertEqual(calls[0]["state"], calls[1]["state"])
        self.assertEqual(controller.decide(observation(("NS",))), "NS")
        self.assertEqual(len(calls), 2)
        metadata = controller.metadata()
        self.assertEqual(metadata["request_count"], 1)
        self.assertEqual(metadata["input_tokens"], 200)
        self.assertEqual(metadata["provider"], "Azure")
        self.assertEqual(metadata["decisions"][0]["response_id"], "gen-1")

    def test_richer_condition_is_explicitly_labeled_and_adds_approach_data(self):
        payloads = []

        def transport(payload):
            payloads.append(payload)
            return {"answers": {"signal": {"choice": "EW"}}}

        controller = MicrosoftDecisions(api_key="unit-test", transport=transport, information_mode="rich")
        self.assertEqual(controller.name, "microsoft-rich")
        controller.decide(observation())
        self.assertIn("queues_by_approach", payloads[0]["state"])
        self.assertIn("approaching_by_approach", payloads[0]["state"])
        self.assertEqual(controller.metadata()["information_mode"], "rich")

    def test_all_decision_models_receive_identical_prompt_and_observation(self):
        request_bodies = []
        for name, model in DECISION_MODELS.items():
            payload = matched_payload(observation(), model)
            request_bodies.append({key: value for key, value in payload.items() if key != "model"})
            controller = OpenRouterDecisions(name=name, api_key="unit-test",
                transport=lambda body: {"model": body["model"],
                    "answers": {"signal": {"choice": "EW"}}})
            self.assertEqual(controller.decide(observation()), "EW")
            self.assertEqual(controller.metadata()["requested_model"], model)
        self.assertEqual(request_bodies[0], request_bodies[1])
        self.assertEqual(request_bodies[1], request_bodies[2])
        self.assertEqual(request_bodies[0]["state"], matched_observation(observation()).record())

    def test_sol_medium_uses_same_question_and_state_in_chat_envelope(self):
        payload = sol_payload(observation())
        chat_input = json.loads(payload["messages"][0]["content"])
        decision_input = matched_payload(observation(), MICROSOFT_MODEL)
        self.assertEqual(chat_input, json.loads(json.dumps({"state": decision_input["state"],
                                                           "questions": decision_input["questions"]})))
        self.assertEqual(payload["model"], SOL_MODEL)
        self.assertEqual(payload["reasoning_effort"], "medium")
        self.assertEqual(payload["response_format"]["json_schema"]["schema"]["properties"]["choice"]["enum"],
                         ["NS", "EW"])
        controller = SolMediumReasoning(api_key="unit-test", transport=lambda request: {
            "model": request["model"], "choices": [{"message": {"content": '{"choice":"EW"}'}}],
            "usage": {"prompt_tokens": 100, "completion_tokens": 50, "cost": 0.0007},
        })
        self.assertEqual(controller.decide(observation()), "EW")
        self.assertEqual(controller.metadata()["request_count"], 1)
        self.assertEqual(controller.metadata()["reasoning_effort"], "medium")

    def test_illegal_or_missing_choice_fails_instead_of_masquerading_as_model_result(self):
        for response in (
            {"answers": {"signal": {"choice": "RED"}}},
            {"answers": {"signal": {}}},
        ):
            with self.subTest(response=response):
                controller = MicrosoftDecisions(api_key="unit-test", transport=lambda _: response)
                with self.assertRaises(RuntimeError):
                    controller.decide(observation())
                self.assertEqual(controller.metadata()["request_count"], 0)


class BrowserCacheTests(unittest.TestCase):
    def test_prompt_change_invalidates_decision_model_caches(self):
        config = Config()
        before = {name: cache_path(name, config) for name in ("fixed", "adaptive", "gurobi", "sol-medium", *DECISION_MODELS)}
        with patch("trafficlab.web.PROMPT_VERSION", "next-prompt"):
            after = {name: cache_path(name, config) for name in before}
        for name in (*DECISION_MODELS, "sol-medium"):
            self.assertNotEqual(before[name], after[name])
        for name in ("fixed", "adaptive", "gurobi"):
            self.assertEqual(before[name], after[name])

    def test_reuses_same_controller_and_parameters_but_runs_new_combination(self):
        runs = []

        def fake_run(config, controller, output_dir, trace_file):
            runs.append((controller.name, config.seed, config.inflow_per_approach))
            trace_file.parent.mkdir(parents=True, exist_ok=True)
            trace_file.write_text(json.dumps({
                "result": {"controller": controller.name, "config": config.record()},
                "frames": [{"time": 0, "vehicles": []}],
            }), encoding="utf-8")

        with tempfile.TemporaryDirectory() as directory:
            with patch("trafficlab.web.ROOT", Path(directory)), \
                 patch("trafficlab.web.make_controller", side_effect=lambda name, **kwargs: SimpleNamespace(name=name)), \
                 patch("trafficlab.web.run_episode", side_effect=fake_run):
                config = Config(seed=7, duration=120)
                self.assertFalse(cached_episode("fixed", config)["cache_hit"])
                self.assertTrue(cached_episode("fixed", config)["cache_hit"])
                self.assertFalse(cached_episode("adaptive", config)["cache_hit"])
                self.assertFalse(cached_episode("fixed", Config(seed=8, duration=120))["cache_hit"])
        self.assertEqual(runs, [("fixed", 7, 0.15), ("adaptive", 7, 0.15), ("fixed", 8, 0.15)])

    def test_saved_replay_mode_never_starts_a_model_or_simulation_on_cache_miss(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch("trafficlab.web.ROOT", Path(directory)), \
                 patch("trafficlab.web.make_controller") as make, \
                 patch("trafficlab.web.run_episode") as run:
                with self.assertRaisesRegex(ValueError, "No new simulation"):
                    cached_episode("sol-medium", Config(planning_horizon=120), saved_only=True)
                make.assert_not_called()
                run.assert_not_called()

    def test_equivalent_integer_and_float_parameters_share_a_replay(self):
        self.assertEqual(cache_path("gurobi", Config(duration=120, cav_share=1)),
                         cache_path("gurobi", Config(duration=120.0, cav_share=1.0)))

    def test_different_objective_cache_is_rejected_without_paid_rerun(self):
        with tempfile.TemporaryDirectory() as directory:
            config = Config(duration=120)
            replay = Path(directory) / 'replay.json'
            replay.write_text(json.dumps({'result': {'controller': 'luna', 'config': config.record(),
                                                     'planning_objective': {'version': 'older'}}, 'frames': []}))
            with patch('trafficlab.web.cache_path', return_value=replay), patch('trafficlab.web.make_controller') as make:
                with self.assertRaisesRegex(ValueError, 'different planning objective'):
                    cached_episode('luna', config)
                make.assert_not_called()


if __name__ == "__main__":
    unittest.main()
