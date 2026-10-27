"""Crash-safe bookkeeping without model calls or a Gurobi license."""

import contextlib
import io
import json
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch

from experiments.horizon_benchmark import run
from trafficlab.benchmark.problem import enumerate_optimum


class TinyReference:
    def __init__(self, **kwargs):
        pass

    def close(self):
        pass

    def evaluate_actions(self, instance):
        actions = {}
        for a in instance.legal_actions:
            result = enumerate_optimum(instance, a)
            actions[a] = dict(result, best_bound=result['objective'], certified=True, wall_seconds=0.0)
        best = min(r['objective'] for r in actions.values())
        return {'actions': actions, 'objective': best, 'best_bound': best, 'certified': True,
                'optimal_actions': [a for a, r in actions.items() if r['objective'] == best]}


class ResumeTests(unittest.TestCase):
    def test_success_failure_and_interrupted_attempts_are_not_resubmitted(self):
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory)
            args = SimpleNamespace(output_dir=out, resume=False, horizons=[6], families=['ordinary'],
                seeds=[7], models=['luna'], mode='first-action', repeats=2, reference_seconds=1, request_timeout=10)
            returned = {'valid': True, 'status': 'returned', 'action': 'NS', 'plan': None,
                        'latency_ms': 10, 'cost_usd': .01, 'input_tokens': 20, 'output_tokens': 0}
            failed = dict(returned, valid=False, status='failed', action=None, error='timeout', cost_usd=None)
            with patch('experiments.horizon_benchmark.ReferenceSolver', TinyReference), \
                 patch('experiments.horizon_benchmark.request_model', side_effect=[returned, failed]) as request, \
                 contextlib.redirect_stdout(io.StringIO()):
                run(args)
                self.assertEqual(request.call_count, 2)
                args.resume = True
                run(args)
                self.assertEqual(request.call_count, 2)
                rows = [json.loads(line) for line in (out / 'runs.jsonl').read_text().splitlines()]
                self.assertEqual(len(rows), 2)
                self.assertEqual(sum(r['valid'] for r in rows), 1)
                self.assertIn('50.000', (out / 'report.md').read_text())
                # Emulate a process dying after request start, before final save.
                (out / 'attempts' / rows[0]['identity'] / 'result.json').unlink()
                run(args)
                self.assertEqual(request.call_count, 2)
                rows = [json.loads(line) for line in (out / 'runs.jsonl').read_text().splitlines()]
                self.assertEqual(rows[0]['status'], 'interrupted')
                self.assertIsNone(rows[0]['cost_usd'])
                args.request_timeout = 11
                with self.assertRaisesRegex(ValueError, 'manifest changed'):
                    run(args)


if __name__ == '__main__':
    unittest.main()
