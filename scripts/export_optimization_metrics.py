"""Publish a read-only snapshot of completed optimization benchmarks in the replay UI.

No simulations, solver calls, or model calls. Run again after new benchmarks
finish. The snapshot is embedded in HTML so existing replay servers can serve
it without restarting or interrupting other work.
"""

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from trafficlab.benchmark.problem import Instance, Objective, validate_plan
from trafficlab.scenario import ROOT

START = '<script id="optimization-data" type="application/json">'
END = '</script><!-- optimization-data -->'


def display_attempt(directory, row):
    """Re-evaluate full plans; never label a first-action result as a plan score."""
    result = {key: row.get(key) for key in (
        'identity', 'case_id', 'controller', 'horizon', 'seed', 'mode', 'repeat',
        'status', 'valid', 'reference_certified')}
    result.update(score=None, objective_gap=None, error=None)
    if row['mode'] == 'full-plan':
        raw = json.loads((directory / 'instances' / f"{row['instance']}.json").read_text())
        instance = Instance(**dict(raw, objective=Objective(**raw['objective'])))
        if instance.identity != row['instance'] or instance.horizon != row['horizon']:
            raise ValueError('saved instance does not match benchmark attempt')
        if not row['valid']:
            result['error'] = 'The benchmark attempt did not return a valid plan.'
            return result
        checked = validate_plan(instance, row.get('plan'))
        result['valid'] = checked['feasible']
        if not checked['feasible']:
            result['error'] = checked['error']
            return result
        result['score'] = checked['objective']
        reference = json.loads((directory / 'references' / f"{row['instance']}.json").read_text())
        result['reference_certified'] = reference['certified']
        if reference['certified'] and reference.get('objective') is not None:
            gap = checked['objective'] - reference['objective']
            if gap < -1e-6:
                raise ValueError('plan score is below certified reference')
            result['objective_gap'] = max(0.0, gap)
    elif row['mode'] == 'first-action':
        # This is a saved reference-based action evaluation, not a full plan.
        if row['valid'] and row['reference_certified']:
            result['score'] = row.get('regret')
    else:
        raise ValueError('unknown benchmark mode')
    return result


def catalog(results):
    datasets = []
    for manifest_file in sorted(results.glob('*/manifest.json')):
        directory = manifest_file.parent
        manifest = json.loads(manifest_file.read_text())
        if manifest.get('mode') not in ('first-action', 'full-plan'):
            continue
        status_file = directory / 'status.json'
        if not status_file.is_file() or json.loads(status_file.read_text()).get('status') != 'complete':
            continue
        rows = [json.loads(line) for line in (directory / 'runs.jsonl').read_text().splitlines() if line.strip()]
        datasets.append({'name': directory.name, 'identity': manifest['identity'],
                         'mode': manifest['mode'], 'protocol': manifest['protocol'],
                         'objective': manifest.get('objective'),
                         'attempts': [display_attempt(directory, row) for row in rows]})
    return {'exported_at': datetime.now(timezone.utc).isoformat(), 'datasets': datasets}


def publish(page, data):
    html = page.read_text()
    if html.count(START) != 1 or html.count(END) != 1:
        raise ValueError('expected one optimization-data placeholder in replay HTML')
    before, rest = html.split(START, 1)
    _, after = rest.split(END, 1)
    payload = json.dumps(data, separators=(',', ':'), allow_nan=False).replace('<', '\\u003c')
    page.write_text(before + START + payload + END + after)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--results', type=Path, default=ROOT / 'results')
    parser.add_argument('--page', type=Path, default=ROOT / 'trafficlab/static/replay.html')
    args = parser.parse_args()
    data = catalog(args.results)
    publish(args.page, data)
    print(f"Published {len(data['datasets'])} completed benchmark datasets; no runs or API calls.")


if __name__ == '__main__':
    main()
