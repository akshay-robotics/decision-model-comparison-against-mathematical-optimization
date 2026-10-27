"""Generate fresh SUMO replays at multiple horizons with durable per-run records."""

import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import datetime, timezone
import hashlib
import fcntl
import json
import os
from pathlib import Path
import shutil
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from experiments.compare_matched import CONTROLLERS, report_markdown
from trafficlab.benchmark.problem import CURRENT_OBJECTIVE, fingerprint
from trafficlab.controllers import make_controller
from trafficlab.openrouter import PROMPT_VERSION
from trafficlab.runner import run_episode
from trafficlab.scenario import Config, ROOT
from trafficlab.web import cache_path


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + '.tmp')
    with temporary.open('w') as stream:
        json.dump(value, stream, indent=2, allow_nan=False)
        stream.flush()
        os.fsync(stream.fileno())
    temporary.replace(path)


def run_one(root, name, horizon):
    config = Config(seed=7, duration=120, planning_horizon=horizon)
    directory = root / f'h{horizon}' / 'seed7' / name
    directory.mkdir(parents=True, exist_ok=True)
    record = {'controller': name, 'horizon': horizon, 'status': 'running',
              'started_utc': datetime.now(timezone.utc).isoformat(), 'config': config.record()}
    state_path = directory / 'status.json'
    save(state_path, record)
    controller = None
    try:
        controller = make_controller(name, horizon=horizon)
        key = getattr(controller, 'api_key', None)

        def journal(value):
            text = json.dumps(value, allow_nan=False)
            if key:
                text = text.replace(key, '[REDACTED]')
            with (directory / 'calls.jsonl').open('a') as stream:
                stream.write(text + '\n')
                stream.flush()
                os.fsync(stream.fileno())

        if hasattr(controller, 'transport'):
            transport = controller.transport

            def recorded_transport(payload):
                began = time.perf_counter()
                journal({'event': 'request', 'utc': datetime.now(timezone.utc).isoformat(), 'payload': payload})
                try:
                    response = transport(payload)
                except Exception as exc:
                    journal({'event': 'error', 'error': str(exc), 'latency_ms': 1000 * (time.perf_counter() - began)})
                    raise
                journal({'event': 'response', 'body': response, 'latency_ms': 1000 * (time.perf_counter() - began)})
                if name == 'sol-medium' and response.get('choices', [{}])[0].get('finish_reason') != 'stop':
                    raise RuntimeError('Sol response incomplete; saved as a failure without substituting an action')
                return response

            controller.transport = recorded_transport
        decide = controller.decide

        def progress(observation):
            record['simulation_seconds'] = observation.time
            save(state_path, record)
            return decide(observation)

        controller.decide = progress
        replay = directory / 'replay.json'
        result = run_episode(config, controller, output_dir=directory, trace_file=replay).record()
        record.update(status='complete', result=result, completed_utc=datetime.now(timezone.utc).isoformat(),
                      route_sha256=hashlib.sha256((directory / 'demand_seed7.rou.xml').read_bytes()).hexdigest())
        target = cache_path(name, config)
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_suffix('.tmp')
        shutil.copyfile(replay, temporary)
        temporary.replace(target)
    except Exception as exc:
        message = f'{type(exc).__name__}: {exc}'
        key = getattr(controller, 'api_key', None)
        record.update(status='failed', error=message.replace(key, '[REDACTED]') if key else message)
    finally:
        if controller is not None and hasattr(controller, 'environment'):
            controller.environment.dispose()
    save(state_path, record)
    return record


def summarize(root, records, horizons, controllers=CONTROLLERS):
    save(root / 'status.json', {'complete': sum(r['status'] == 'complete' for r in records),
                              'failed': sum(r['status'] != 'complete' for r in records),
                              'finished': len(records), 'expected': len(horizons) * len(controllers)})
    rows = [r['result'] for r in records if r['status'] == 'complete']
    rows.sort(key=lambda r: (r['config']['planning_horizon'], CONTROLLERS.index(r['controller'])))
    (root / 'runs.jsonl').write_text(''.join(json.dumps(r) + '\n' for r in rows))
    for horizon in horizons:
        selected = [r for r in rows if r['config']['planning_horizon'] == horizon]
        if not selected:
            continue
        hashes = {r['route_sha256'] for r in records if r['horizon'] == horizon and r['status'] == 'complete'}
        if len(hashes) != 1:
            raise RuntimeError('Traffic demand differs across controllers')
        directory = root / f'h{horizon}'
        (directory / 'runs.jsonl').write_text(''.join(json.dumps(r) + '\n' for r in selected))
        (directory / 'report.md').write_text(report_markdown(selected, Config(**selected[0]['config']), [7], {7: next(iter(hashes))}))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--horizons', type=int, nargs='+', default=[15, 30, 60, 120])
    parser.add_argument('--workers', type=int, default=4)
    parser.add_argument('--controllers', nargs='+', choices=CONTROLLERS, default=list(CONTROLLERS))
    parser.add_argument('--output-dir', type=Path, required=True)
    parser.add_argument('--resume', action='store_true')
    args = parser.parse_args()
    if not 1 <= args.workers <= 4 or len(set(args.horizons)) != len(args.horizons) or len(set(args.controllers)) != len(args.controllers):
        parser.error('use 1–4 workers and unique horizons')
    for horizon in args.horizons:
        Config(planning_horizon=horizon)
    root = args.output_dir.resolve()
    root.mkdir(parents=True, exist_ok=True)
    lock = (root / '.run.lock').open('a')
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    paths = list((ROOT / 'trafficlab').glob('*.py')) + list((ROOT / 'trafficlab' / 'benchmark').glob('*.py')) + [Path(__file__).resolve()]
    manifest = {'protocol': PROMPT_VERSION, 'horizons': args.horizons, 'controllers': args.controllers,
                'seed': 7, 'duration': 120, 'workers': args.workers,
                'objective': CURRENT_OBJECTIVE.__dict__,
                'source_sha256': fingerprint({str(p.relative_to(ROOT)): p.read_text() for p in paths})}
    if (root / 'manifest.json').exists():
        if not args.resume or json.loads((root / 'manifest.json').read_text()) != manifest:
            raise ValueError('Existing experiment requires --resume with the identical configuration and source')
    else:
        save(root / 'manifest.json', manifest)
        for path in paths:
            target = root / 'source' / path.relative_to(ROOT)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, target)
    records = []
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        futures = []
        for name in args.controllers:
            for horizon in args.horizons:
                prior = root / f'h{horizon}' / 'seed7' / name / 'status.json'
                if prior.exists():
                    record = json.loads(prior.read_text())
                    if record['status'] == 'running':
                        record.update(status='interrupted', error='No automatic retry of potentially billed calls')
                        save(prior, record)
                    records.append(record)
                else:
                    futures.append(pool.submit(run_one, root, name, horizon))
        for future in as_completed(futures):
            record = future.result()
            records.append(record)
            summarize(root, records, args.horizons, args.controllers)
            print(f"H={record['horizon']} {record['controller']}: {record['status']} "
                  f"completed={record.get('result', {}).get('completed', '—')}", flush=True)
    summarize(root, records, args.horizons, args.controllers)
    lock.close()


if __name__ == '__main__':
    main()
