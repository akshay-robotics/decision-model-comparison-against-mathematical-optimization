"""Independent exhaustive checks of planning, timing, forecasts, and regret."""

from dataclasses import replace
import importlib.util
import random
import unittest

from trafficlab.benchmark.problem import Instance, Objective, CURRENT_OBJECTIVE, fingerprint, enumerate_optimum, validate_plan
from trafficlab.benchmark.reference import ReferenceSolver, first_action_score
from trafficlab.benchmark.instances import FAMILIES, generate_instance, physical_identity
from trafficlab.benchmark.adapters import payload_for, request_model
from trafficlab.controllers import GurobiSignalMILP
from trafficlab.openrouter import DECISION_MODELS, matched_payload, prompt_sha256
from trafficlab.scenario import Config
from trafficlab.sol import sol_payload
from trafficlab.web import cache_path


class PlanTests(unittest.TestCase):
    def instance(self, h=6, **kwargs):
        return Instance('tiny', 'unit', 0, h, (4, 5), ((0, 0),) * h,
                        min_green=2, yellow=2, all_red=1, age=2, **kwargs)

    def test_immediate_yellow_clearance_and_minimum_green(self):
        i = self.instance()
        scored = validate_plan(i, ['EW', 'NS', 'NS', 'EW', 'EW', 'NS'])
        self.assertTrue(scored['feasible'])
        self.assertEqual([r['queues'] for r in scored['trace']],
                         [[3, 5], [2, 5], [2, 5], [2, 3], [2, 1], [2, 0]])
        self.assertEqual(scored['queue_cost'], 32)
        self.assertEqual(scored['terminal_cost'], 20)
        self.assertEqual(scored['objective'], 53)
        self.assertEqual(scored['switches'], 2)
        self.assertFalse(validate_plan(i, ['EW', 'EW', 'NS', 'EW', 'EW', 'NS'])['feasible'])
        self.assertFalse(validate_plan(i, ['EW', 'NS', 'NS', 'EW', 'NS', 'NS'])['feasible'])

    def test_invalid_truncated_and_extra_plans_are_not_repaired(self):
        i = self.instance()
        for plan in (['NS'] * 5, ['NS'] * 7, ['NS'] * 5 + ['RED'], 'NS', None):
            self.assertFalse(validate_plan(i, plan)['feasible'])

    def test_terminal_penalty_is_applied_once_and_legacy_instances_keep_their_identity(self):
        i = self.instance(h=2)
        scored = validate_plan(i, ['NS', 'NS'])
        self.assertEqual(scored['queue_cost'], 12)
        self.assertEqual(scored['terminal_cost'], 50)
        self.assertEqual(scored['objective'], 62)
        old = replace(i, objective=Objective())
        self.assertEqual(validate_plan(old, ['NS', 'NS'])['objective'], 12)
        record = old.record()
        self.assertNotIn('terminal_queue_penalty', record['objective'])
        restored = Instance(**dict(record, objective=Objective(**record['objective'])))
        self.assertEqual(old.identity, restored.identity)
        self.assertEqual(old.identity, fingerprint({'protocol': 'frozen-queue-v1', 'instance': record}))

    def test_all_remote_models_receive_the_same_terminal_objective(self):
        import json
        i = self.instance()
        texts = []
        for name in (*DECISION_MODELS, 'sol-medium'):
            _, payload = payload_for(i, name, 'first-action')
            question = (json.loads(payload['messages'][0]['content'])['questions']['signal']
                        if 'messages' in payload else payload['questions']['signal'])
            texts.append(question)
            self.assertIn('10.0*(q_NS[6]+q_EW[6])', question['instructions'])
        self.assertTrue(all(text == texts[0] for text in texts))

    def test_full_forecast_is_required_and_fingerprinted(self):
        i = self.instance()
        with self.assertRaises(ValueError):
            replace(i, horizon=7)
        with self.assertRaises(ValueError):
            replace(i, arrivals=((0, -1),) * 6)
        self.assertNotEqual(i.identity, i.prefix(5).identity)
        self.assertNotEqual(i.identity, replace(i, objective=Objective(switch_penalty=1)).identity)

    def test_regret_ties_and_uncertified_bounds(self):
        tied = {'certified': True, 'objective': 5, 'best_bound': 5, 'optimal_actions': ['NS', 'EW'],
                'actions': {a: {'objective': 5, 'best_bound': 5} for a in ('NS', 'EW')}}
        self.assertEqual(first_action_score(tied, 'EW')['regret'], 0)
        self.assertTrue(first_action_score(tied, 'EW')['optimal_action'])
        uncertain = {'certified': False, 'objective': 8, 'best_bound': 4, 'optimal_actions': [],
                     'actions': {'NS': {'objective': 8, 'best_bound': 4},
                                 'EW': {'objective': 10, 'best_bound': 6}}}
        score = first_action_score(uncertain, 'EW')
        self.assertIsNone(score['regret'])
        self.assertEqual((score['regret_lower'], score['regret_upper']), (0, 6))

    def test_horizon_changes_all_payloads_and_cache_identity(self):
        for h in (15, 30, 60, 120):
            i = Instance('payload', 'unit', 0, h, (3, 8), ((1, 0),) * h)
            bodies = [matched_payload(i.observation(), model) for model in DECISION_MODELS.values()]
            for body in bodies:
                self.assertEqual(len(body['state']['arrivals_forecast_NS_EW']), h)
                self.assertEqual(body['state']['planning_horizon_seconds'], h)
                self.assertIn(f'{h}-step plan', body['questions']['signal']['instructions'])
            import json
            sol = json.loads(sol_payload(i.observation())['messages'][0]['content'])
            self.assertEqual(sol, json.loads(json.dumps({k: bodies[0][k] for k in ('state', 'questions')})))
        self.assertEqual(len({prompt_sha256(h) for h in (15, 30, 60, 120)}), 4)
        self.assertNotEqual(cache_path('luna', Config(planning_horizon=15)),
                            cache_path('luna', Config(planning_horizon=30)))

    def test_arrival_realizations_are_identical_prefixes_for_every_family(self):
        for family in FAMILIES:
            long = generate_instance(family, 7, 120)
            for h in (15, 30, 60):
                short = generate_instance(family, 7, h)
                self.assertEqual(short.identity, long.prefix(h).identity)
        self.assertEqual(physical_identity(generate_instance('lookahead', 7, 15)),
                         physical_identity(generate_instance('lookahead', 8, 15)))

    def test_full_plan_schema_does_not_mutate_first_action_schema(self):
        i = self.instance()
        _, full = payload_for(i, 'sol-medium', 'full-plan')
        self.assertIn('actions', full['response_format']['json_schema']['schema']['properties'])
        _, first = payload_for(i, 'sol-medium', 'first-action')
        self.assertIn('choice', first['response_format']['json_schema']['schema']['properties'])
        for name in DECISION_MODELS:
            with self.assertRaises(ValueError):
                payload_for(i, name, 'full-plan')

    def test_failed_outputs_preserve_usage_and_raw_responses(self):
        import json
        i = self.instance()
        for reason, content in [('length', '{"choice":"NS"}'), ('stop', '{"choice":"RED"}'),
                                ('stop', 'not json')]:
            saved = {}
            response = {'choices': [{'finish_reason': reason, 'message': {'content': content}}],
                        'usage': {'prompt_tokens': 12, 'completion_tokens': 3, 'cost': .01}}
            result = request_model(i, 'sol-medium', 'first-action', transport=lambda _: response,
                                   save_raw=lambda key, value: saved.update({key: value}))
            self.assertFalse(result['valid'])
            self.assertEqual(result['cost_usd'], .01)
            self.assertEqual(result['input_tokens'], 12)
            self.assertEqual(json.loads(saved['response']), response)
            self.assertNotIn('Authorization', saved['request'])

    def test_full_plan_output_is_scored_mechanically(self):
        from experiments.horizon_benchmark import score_output
        i = self.instance()
        ref = {'certified': False, 'objective': 40, 'best_bound': 20}
        result = score_output(i, ref, 'full-plan', {'valid': True, 'plan': ['NS'] * 5, 'status': 'returned'})
        self.assertFalse(result['valid'])
        self.assertEqual(result['status'], 'invalid')
        valid = score_output(i, ref, 'full-plan', {'valid': True, 'plan': ['NS'] * 6, 'status': 'returned'})
        self.assertTrue(valid['valid'])
        self.assertIsNone(valid['objective_gap'])


@unittest.skipUnless(importlib.util.find_spec('gurobipy'), 'optional Gurobi binding not installed')
class ReferenceTests(unittest.TestCase):
    def test_terminal_penalty_changes_optimal_action_and_matches_independent_enumeration(self):
        i = Instance('terminal-reversal', 'regression', 0, 6, (1, 4),
                     ((1, 2), (1, 2), (0, 1), (2, 0), (2, 2), (0, 0)),
                     min_green=2, yellow=2, all_red=1, age=2)
        solver = ReferenceSolver(time_limit=10)
        try:
            old = solver.evaluate_actions(replace(i, objective=Objective()))
            new = solver.evaluate_actions(i)
            self.assertTrue(old['certified'] and new['certified'])
            self.assertEqual(old['optimal_actions'], ['NS'])
            self.assertEqual(new['optimal_actions'], ['EW'])
            for action, reference in new['actions'].items():
                self.assertEqual(reference['objective'], enumerate_optimum(i, action)['objective'])
            controller = GurobiSignalMILP(horizon=6)
            try:
                self.assertEqual(controller.decide(i.observation()), 'EW')
            finally:
                controller.environment.dispose()
        finally:
            solver.close()

    def test_long_sparse_horizon_does_not_accumulate_solver_tolerance_slack(self):
        arrivals = [(0, 0)] * 120
        for step in (2, 4, 6):
            arrivals[step] = (0, 1)
        for step in (3, 11):
            arrivals[step] = (1, 0)
        instance = Instance('sparse-120', 'regression', 7, 120, (3, 1), tuple(arrivals), phase='EW', age=12)
        solver = ReferenceSolver(time_limit=10)
        try:
            result = solver.solve(instance)
            self.assertTrue(result['certified'])
            self.assertEqual(result['objective'], 35.5)
            self.assertAlmostEqual(result['best_bound'], 35.5, places=6)
        finally:
            solver.close()

    def test_disclosed_case_requires_longer_lookahead_and_fits_license(self):
        solver = ReferenceSolver(time_limit=10)
        try:
            i = generate_instance('lookahead', 7, 120)
            short = solver.evaluate_actions(i.prefix(15))
            long = solver.evaluate_actions(i.prefix(30))
            self.assertTrue(short['certified'] and long['certified'])
            self.assertEqual(short['optimal_actions'], ['EW'])
            self.assertEqual(long['optimal_actions'], ['NS'])
            result = solver.solve(i)
            self.assertTrue(result['certified'])
            self.assertLess(result['variables'], 2000)
            self.assertLess(result['constraints'], 2000)
        finally:
            solver.close()
    def test_matches_exhaustive_enumeration_including_busy_initial_states(self):
        solver = ReferenceSolver(time_limit=10)
        rng = random.Random(54)
        try:
            for j in range(12):
                h = 6 + j % 3
                i = Instance(str(j), 'unit', j, h, (rng.randrange(5), rng.randrange(5)),
                             tuple((rng.randrange(3), rng.randrange(3)) for _ in range(h)),
                             phase='NS' if j % 2 else 'EW', age=j % 3,
                             min_green=2, yellow=2, all_red=1)
                if j % 3 == 0:
                    i = replace(i, pending='EW' if i.phase == 'NS' else 'NS', remaining=1 + j % 2)
                refs = solver.evaluate_actions(i)
                self.assertTrue(refs['certified'])
                for action, result in refs['actions'].items():
                    brute = enumerate_optimum(i, action)
                    self.assertAlmostEqual(result['objective'], brute['objective'])
                    self.assertAlmostEqual(result['best_bound'], brute['objective'])
                    self.assertTrue(validate_plan(i, result['plan'])['feasible'])
        finally:
            solver.close()

    def test_optimizer_refuses_silent_zero_padding(self):
        controller = GurobiSignalMILP(horizon=30)
        i = Instance('short', 'unit', 0, 15, (0, 1), ((0, 0),) * 15)
        try:
            with self.assertRaises(ValueError):
                controller.decide(i.observation())
        finally:
            controller.environment.dispose()


if __name__ == '__main__':
    unittest.main()
