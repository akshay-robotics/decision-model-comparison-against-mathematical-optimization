"""Export a small, credential-free dataset from the two completed 15 s pilots."""

import argparse
import csv
import hashlib
import json
from pathlib import Path
import defusedxml.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
NAMES = ('gurobi', 'microsoft', 'jev', 'luna', 'sol-medium')


def dump(path, value):
    path.write_text(json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + '\n')


def export(original, revised, output):
    output.mkdir(parents=True, exist_ok=True)
    episodes, replays, prompts = [], [], {}
    for condition, directory in [('original', original), ('terminal', revised)]:
        rows = [json.loads(line) for line in (directory / 'runs.jsonl').read_text().splitlines()]
        rows = [r for r in rows if r['config']['planning_horizon'] == 15]
        assert len(rows) == 5
        for name in NAMES:
            r = next(r for r in rows if r['controller'] == name)
            model = r.get('decision_model') or {}
            objective = r.get('planning_objective') or {
                'version': 'end-step-queues-plus-switches-v1', 'green_capacity': 2,
                'yellow_capacity': 1, 'switch_penalty': .5, 'step_seconds': 1,
                'terminal_queue_penalty': 0}
            folder = directory / 'h15' / 'seed7' / name
            route = folder / 'demand_seed7.rou.xml'
            trip = folder / f'tripinfo_{name}_seed7.xml'
            route_hash = hashlib.sha256(route.read_bytes()).hexdigest()
            row = {'condition': condition, 'controller': name, 'seed': 7, 'planning_horizon': 15,
                   'simulation_duration': 120, 'generated': r['generated'], 'completed': r['completed'],
                   'unfinished': r['evaluation']['unfinished'], 'active': r['active'], 'entry_backlog': r['entry_backlog'],
                   'completion_percent': r['evaluation']['completion_percent'],
                   'mean_system_seconds': r['evaluation']['mean_time_in_system'],
                   'total_system_seconds': r['evaluation']['total_time_in_system'],
                   'mean_completed_travel_seconds': r['mean_travel_time'],
                   'mean_completed_wait_seconds': r['mean_waiting_time'], 'switches': r['switches'],
                   'mean_choice_ms': r['mean_choice_ms'], 'p95_choice_ms': r['p95_choice_ms'],
                   'api_calls': model.get('request_count', 0), 'reported_api_cost_usd': model.get('cost_usd', 0),
                   'input_tokens': model.get('input_tokens', 0), 'output_tokens': model.get('output_tokens', 0),
                   'objective': objective, 'config': r['config'], 'route_sha256': route_hash,
                   'by_approach': r['evaluation']['by_approach'],
                   'requested_model': model.get('requested_model'),
                   'returned_models': sorted({d['model'] for d in model.get('decisions', [])}),
                   'providers': sorted({str(d['provider']) for d in model.get('decisions', [])}),
                   'prompt_version': model.get('prompt_version'), 'prompt_sha256': model.get('prompt_sha256'),
                   'solver_status_counts': r['solver_status_counts'], 'worst_solver_gap': r['worst_solver_gap']}
            episodes.append(row)
            if name != 'gurobi':
                events = [json.loads(line) for line in (folder / 'calls.jsonl').read_text().splitlines()]
                first = next(e['payload'] for e in events if e['event'] == 'request')
                question = (json.loads(first['messages'][0]['content'])['questions']['signal']
                            if 'messages' in first else first['questions']['signal'])
                prompts.setdefault(condition, {'version': model['prompt_version'], 'question': question, 'examples': {}})
                assert prompts[condition]['question'] == question
                prompts[condition]['examples'][name] = first
            if condition == 'terminal':
                data = json.loads((folder / 'replay.json').read_text())
                arrivals = {t.attrib['id']: float(t.attrib['arrival'])
                            for t in ET.parse(trip).getroot().iter('tripinfo') if float(t.attrib['arrival']) >= 0}
                demand = [{'id': v.attrib['id'], 'depart': float(v.attrib['depart']),
                           'arrival': arrivals.get(v.attrib['id'])}
                          for v in ET.parse(route).getroot().iter('vehicle')]
                assert len(demand) == 78 and len(data['frames']) == 240
                replays.append({'controller': name, 'result': row, 'frames': data['frames'], 'demand': demand})
    assert len({r['route_sha256'] for r in episodes}) == 1
    dump(output / 'episodes.json', episodes)
    scalar_fields = [k for k, v in episodes[0].items() if not isinstance(v, (dict, list))]
    with (output / 'episodes.csv').open('w', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=scalar_fields, lineterminator='\n')
        writer.writeheader()
        writer.writerows({k: row[k] for k in scalar_fields} for row in episodes)
    dump(output / 'prompts.json', prompts)
    # Compact trajectories keep the browser demo self-contained and small.
    (output / 'replays.json').write_text(json.dumps({'episodes': replays}, separators=(',', ':'), allow_nan=False))
    dump(output / 'metadata.json', {
        'experiment_date': '2026-10-21', 'scope': 'single-junction development pilot',
        'independent_traffic_seeds': 1, 'episodes_per_condition_per_controller': 1,
        'conditions': {c: {'objective': next(r['objective'] for r in episodes if r['condition'] == c),
                          'manifest': json.loads((d / 'manifest.json').read_text())}
                       for c, d in [('original', original), ('terminal', revised)]},
        'gurobi_seconds_per_choice': .8, 'gurobi_threads': 1,
        'gurobi_original_reference_version': 'queue-switch-events-v2',
        'gurobi_revised_reference_version': 'queue-switch-events-v3-terminal',
        'sol_reasoning_effort': 'medium', 'sol_max_completion_tokens': 4096,
        'latency_semantics': 'End-to-end legal-choice latency; SUMO pauses during model calls.',
        'system_time_semantics': 'Every generated car, from scheduled departure until arrival or cutoff.',
        'completed_time_semantics': 'Travel and waiting means include completed trips only.',
        'limits': ['No revised-objective frozen optimization benchmark.', 'Model aliases and stochastic outputs can change.',
                   'No general long-horizon optimization conclusion.', 'Objective coefficient fixed before rerun.']})
    checksums = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(output.iterdir())
                 if p.is_file() and p.name != 'checksums.json'}
    dump(output / 'checksums.json', checksums)
    print(f'Exported {len(episodes)} episodes, {len(replays)} saved replays, and exact prompts to {output}')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--original', type=Path, default=ROOT / 'results/horizon-replays-final-2026-10-21')
    parser.add_argument('--revised', type=Path, default=ROOT / 'results/terminal-objective-v2-h15-2026-10-21')
    parser.add_argument('--output', type=Path, default=ROOT / 'data/published/traffic-objective-v2')
    args = parser.parse_args()
    export(args.original, args.revised, args.output)
