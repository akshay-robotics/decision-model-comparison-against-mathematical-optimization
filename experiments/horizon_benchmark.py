"""Frozen first-action/full-plan benchmark with per-attempt durable resume."""

import argparse
from datetime import datetime, timezone
import fcntl
import json
import math
import os
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from trafficlab.benchmark.adapters import REMOTE_MODELS, model_configuration, payload_for, request_model
from trafficlab.benchmark.instances import FAMILIES, GENERATOR_VERSION, generate_instance, physical_identity
from trafficlab.benchmark.problem import PROTOCOL, CURRENT_OBJECTIVE, fingerprint, validate_plan
from trafficlab.benchmark.reference import CERT_TOLERANCE, REFERENCE_VERSION, ReferenceSolver, first_action_score
from trafficlab.benchmark.report import summary_markdown
from trafficlab.openrouter import PROMPT_VERSION
from trafficlab.scenario import ROOT


BASELINES = ('gurobi', 'stay', 'max-queue', 'short15')


def atomic_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + '.tmp')
    with temporary.open('w', encoding='utf-8') as stream:
        json.dump(data, stream, sort_keys=True, indent=2, allow_nan=False)
        stream.write('\n')
        stream.flush()
        os.fsync(stream.fileno())
    temporary.replace(path)


def choose(reference, phase):
    if reference['certified']:
        return phase if phase in reference['optimal_actions'] else reference['optimal_actions'][0]
    available = {a: r['objective'] for a, r in reference['actions'].items() if r['objective'] is not None}
    if not available:
        raise RuntimeError('no feasible reference incumbent')
    return min(available, key=lambda a: (available[a], a != phase))


def baseline(instance, name, mode, reference, solver):
    began = time.perf_counter()
    if name == 'gurobi':
        action = choose(reference, instance.phase)
    elif name == 'short15':
        action = choose(solver.evaluate_actions(instance.prefix(min(15, instance.horizon))), instance.phase)
    elif name == 'max-queue':
        action = max(instance.legal_actions, key=lambda a: (instance.queues[0 if a == 'NS' else 1], a == instance.phase))
    else:
        action = instance.phase
    if mode == 'full-plan' and name != 'gurobi':
        raise ValueError('full-plan baselines currently support Gurobi only')
    return {'status': 'returned', 'valid': True, 'action': action,
            'plan': reference['actions'][action]['plan'] if mode == 'full-plan' else None,
            # Reference solves are offline and amortized across contenders.
            # Do not report reference lookup latency as optimization runtime.
            'latency_ms': sum(r['wall_seconds'] for r in reference['actions'].values()) * 1000
                          if name == 'gurobi' else (time.perf_counter() - began) * 1000,
            'cost_usd': 0.0, 'input_tokens': 0, 'output_tokens': 0}


def score_output(instance, reference, mode, output):
    result = dict(output, reference_certified=reference['certified'])
    if not output['valid']:
        return result
    if mode == 'first-action':
        result.update(first_action_score(reference, output['action']))
        return result
    scored = validate_plan(instance, output['plan'])
    result.update(valid=scored['feasible'], validation=scored)
    if not scored['feasible']:
        result.update(status='invalid', error=scored['error'])
        return result
    result['objective'] = scored['objective']
    if reference['certified']:
        gap = scored['objective'] - reference['objective']
        if gap < -CERT_TOLERANCE:
            raise RuntimeError('validated plan beats certified reference: evaluator inconsistency')
        result['objective_gap'] = max(0.0, gap)
        result['relative_objective_gap'] = gap / reference['objective'] if reference['objective'] > 0 else None
    else:
        result['objective_gap'] = None
        result['objective_gap_lower'] = max(0.0, scored['objective'] - reference['objective']) if reference['objective'] is not None else None
        result['objective_gap_upper'] = max(0.0, scored['objective'] - reference['best_bound']) if reference['best_bound'] is not None else None
    return result


def source_identity():
    paths = [*sorted((ROOT / 'trafficlab' / 'benchmark').glob('*.py')),
             ROOT / 'trafficlab' / 'openrouter.py', ROOT / 'trafficlab' / 'sol.py',
             ROOT / 'trafficlab' / 'security.py',
             ROOT / 'trafficlab' / 'controllers.py', Path(__file__)]
    return fingerprint({str(p.relative_to(ROOT)): fingerprint(p.read_text()) for p in paths})


def run(args):
    out = args.output_dir.resolve()
    out.mkdir(parents=True, exist_ok=True)
    with (out / '.run.lock').open('a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise RuntimeError('this output directory already has a running benchmark') from exc
        run_locked(args, out)


def run_locked(args, out):
    identities = {'protocol': PROTOCOL, 'generator': GENERATOR_VERSION, 'source_sha256': source_identity(),
                  'prompt_version': PROMPT_VERSION, 'objective': CURRENT_OBJECTIVE.__dict__,
                  'horizons': args.horizons, 'families': args.families, 'seeds': args.seeds,
                  'models': args.models, 'mode': args.mode, 'repeats': args.repeats,
                  'reference_version': REFERENCE_VERSION, 'reference_seconds': args.reference_seconds,
                  'certification_tolerance': CERT_TOLERANCE, 'request_timeout': args.request_timeout}
    manifest = dict(identities, identity=fingerprint(identities))
    manifest_path = out / 'manifest.json'
    if manifest_path.exists():
        if not args.resume:
            raise ValueError('output already exists; use --resume or a new output directory')
        if json.loads(manifest_path.read_text()) != manifest:
            raise ValueError('manifest changed; preserve this run and choose a new output directory')
    else:
        atomic_json(manifest_path, manifest)
    solver = ReferenceSolver(time_limit=args.reference_seconds)
    rows = []
    atomic_json(out / 'status.json', {'status': 'running', 'experiment': manifest['identity']})
    try:
        for family in args.families:
            for seed in args.seeds:
                for horizon in args.horizons:
                    instance = generate_instance(family, seed, horizon)
                    instance_id = instance.identity
                    atomic_json(out / 'instances' / f'{instance_id}.json', instance.record())
                    reference_file = out / 'references' / f'{instance_id}.json'
                    if reference_file.exists():
                        reference = json.loads(reference_file.read_text())
                    else:
                        reference = solver.evaluate_actions(instance)
                        atomic_json(reference_file, reference)
                    print(f'{family} seed={seed} H={horizon}: reference certified={reference["certified"]} '
                          f'objective={reference["objective"]} optimal={reference["optimal_actions"]}', flush=True)
                    for name in args.models:
                        model_config = model_configuration(instance, name, args.mode, args.request_timeout) if name in REMOTE_MODELS else {
                            'name': name, 'mode': args.mode, 'reference_seconds': args.reference_seconds,
                            'short_horizon': min(15, horizon) if name == 'short15' else None}
                        # Baselines are deterministic; repeating them would only inflate N.
                        for repeat in range(args.repeats if name in REMOTE_MODELS else 1):
                            identity = {'instance': instance_id, 'objective': fingerprint(instance.objective.__dict__),
                                        'experiment': manifest['identity'], 'model_configuration': model_config, 'repeat': repeat}
                            job_id = fingerprint(identity)
                            directory = out / 'attempts' / job_id
                            result_file = directory / 'result.json'
                            meta = {'identity': job_id, 'case_id': instance.case_id, 'instance': instance_id,
                                    'physical_identity': physical_identity(instance), 'family': family,
                                    'horizon': horizon, 'seed': seed, 'controller': name, 'mode': args.mode,
                                    'repeat': repeat, 'model_configuration': model_config,
                                    'reference_certified': reference['certified']}
                            if result_file.exists():
                                row = json.loads(result_file.read_text())
                            elif (directory / 'started.json').exists():
                                # A crash may occur after the provider billed a call. Preserve it as
                                # interrupted instead of silently paying again or dropping a failure.
                                row = dict(meta, status='interrupted', valid=False, latency_ms=None,
                                           cost_usd=None, input_tokens=None, output_tokens=None,
                                           error='prior attempt interrupted; no automatic retry')
                                atomic_json(result_file, row)
                            else:
                                atomic_json(directory / 'started.json', dict(identity, started_utc=datetime.now(timezone.utc).isoformat()))
                                if name in REMOTE_MODELS:
                                    def save_raw(label, text):
                                        (directory / f'{label}.txt').write_text(text, encoding='utf-8')
                                    output = request_model(instance, name, args.mode, args.request_timeout, save_raw=save_raw)
                                else:
                                    output = baseline(instance, name, args.mode, reference, solver)
                                row = dict(meta, **score_output(instance, reference, args.mode, output))
                                atomic_json(result_file, row)
                            rows.append(row)
                            # All attempts are recoverable from per-job files; regenerate the view after each one.
                            (out / 'runs.jsonl').write_text(''.join(json.dumps(r, sort_keys=True) + '\n' for r in rows))
                            (out / 'report.md').write_text(summary_markdown(rows, manifest))
                            print(f'  {name} repeat={repeat}: {row["status"]} valid={row["valid"]} '
                                  f'regret={row.get("regret")} gap={row.get("objective_gap")}', flush=True)
        atomic_json(out / 'status.json', {'status': 'complete', 'attempts': len(rows),
                    'valid': sum(bool(r['valid']) for r in rows),
                    'certified_references': len({r['instance'] for r in rows if r['reference_certified']}),
                    'known_cost_usd': sum(r.get('cost_usd') or 0 for r in rows),
                    'missing_cost': sum(r.get('cost_usd') is None for r in rows)})
    except BaseException:
        atomic_json(out / 'status.json', {'status': 'interrupted', 'saved_attempts_this_pass': len(rows),
                                         'experiment': manifest['identity']})
        raise
    finally:
        solver.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--horizons', type=int, nargs='+', default=[15, 30, 60, 120])
    parser.add_argument('--families', choices=FAMILIES, nargs='+', default=list(FAMILIES))
    parser.add_argument('--seeds', type=int, nargs='+', default=[7])
    parser.add_argument('--models', choices=(*BASELINES, *REMOTE_MODELS), nargs='+', default=list(BASELINES))
    parser.add_argument('--mode', choices=('first-action', 'full-plan'), default='first-action')
    parser.add_argument('--repeats', type=int, default=2)
    parser.add_argument('--reference-seconds', type=float, default=120)
    parser.add_argument('--request-timeout', type=float, default=120)
    parser.add_argument('--output-dir', type=Path, required=True)
    parser.add_argument('--resume', action='store_true')
    args = parser.parse_args()
    if args.repeats < 1 or any(h < 1 or h > 600 for h in args.horizons) or any(s < 0 for s in args.seeds):
        parser.error('invalid horizons, seeds, or repeats')
    if not all(math.isfinite(x) and x > 0 for x in (args.reference_seconds, args.request_timeout)):
        parser.error('timeouts must be finite and positive')
    for values in (args.horizons, args.families, args.seeds, args.models):
        if len(set(values)) != len(values):
            parser.error('duplicate horizons, families, seeds, or models are not allowed')
    if args.mode == 'full-plan' and any(name not in ('gurobi', 'sol-medium') for name in args.models):
        parser.error('full-plan mode currently supports gurobi and sol-medium only; Decisions capability is unverified')
    run(args)


if __name__ == '__main__':
    main()
