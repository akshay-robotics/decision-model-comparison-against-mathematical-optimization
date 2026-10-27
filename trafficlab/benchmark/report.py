"""Failure-inclusive summaries, stratified by mode, horizon, and case family."""

from collections import defaultdict
import statistics
import math


def number(value):
    return "—" if value is None else f"{value:.3f}"


def summary_markdown(rows, manifest):
    groups = defaultdict(list)
    for row in rows:
        groups[(row['mode'], row['horizon'], row['family'], row['controller'])].append(row)
    lines = ["# Frozen-instance horizon benchmark", "",
             f"Protocol: `{manifest['protocol']}`; experiment: `{manifest['identity']}`.", "",
             "Development pilot with deterministic supplied arrivals. Reference continuation is optimized separately "
             "for each legal first action. Only certified references produce point regret or objective gaps. "
             "A time limit alone never establishes optimality. All attempts, including failures, count in validity rates.", "",
             "| Mode | Horizon s | Family | Controller | Attempts | Distinct problems | Valid % | Certified scored | Optimal action % | Mean regret / gap | SD | Mean relative plan gap | Mean latency ms | P95 ms | Known input tokens | Known output tokens | Known cost USD | Missing cost |",
             "| --- | ---: | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |"]
    for (mode, horizon, family, name), records in sorted(groups.items()):
        scores = [r.get('regret' if mode == 'first-action' else 'objective_gap') for r in records]
        scores = [x for x in scores if x is not None]
        latencies = sorted(r['latency_ms'] for r in records if r.get('latency_ms') is not None)
        costs = [r['cost_usd'] for r in records if r.get('cost_usd') is not None]
        optimal = [r['optimal_action'] for r in records if r.get('optimal_action') is not None]
        relative = [r['relative_objective_gap'] for r in records if r.get('relative_objective_gap') is not None]
        inputs = [r['input_tokens'] for r in records if r.get('input_tokens') is not None]
        outputs = [r['output_tokens'] for r in records if r.get('output_tokens') is not None]
        p95 = latencies[max(0, math.ceil(.95 * len(latencies)) - 1)] if latencies else None
        lines.append('| ' + ' | '.join(map(str, [mode, horizon, family, name, len(records),
            len({r['physical_identity'] for r in records}),
            number(100 * sum(bool(r['valid']) for r in records) / len(records)), len(scores),
            number(100 * sum(optimal) / len(optimal)) if optimal else '—',
            number(statistics.mean(scores)) if scores else '—',
            number(statistics.stdev(scores)) if len(scores) > 1 else '—',
            number(statistics.mean(relative)) if relative else '—',
            number(statistics.mean(latencies)) if latencies else '—', number(p95),
            sum(inputs) if inputs else '—', sum(outputs) if outputs else '—',
            f'{sum(costs):.6f}' if costs else '—', len(records) - len(costs)])) + ' |')
    lines.extend(['', '## Individual attempts', '',
        '| Case | H | Controller | Mode | Repeat | Status | Choice | Certified reference | Regret / gap | Regret bounds | Input tokens | Output tokens |',
        '| --- | ---: | --- | --- | ---: | --- | --- | --- | ---: | --- | ---: | ---: |'])
    for r in rows:
        score = r.get('regret' if r['mode'] == 'first-action' else 'objective_gap')
        lines.append('| ' + ' | '.join(map(str, [r['case_id'], r['horizon'], r['controller'], r['mode'],
            r['repeat'], r['status'], r.get('action') or '—', r['reference_certified'], number(score),
            f"[{number(r.get('regret_lower'))}, {number(r.get('regret_upper'))}]",
            r.get('input_tokens') if r.get('input_tokens') is not None else '—',
            r.get('output_tokens') if r.get('output_tokens') is not None else '—'])) + ' |')
    lines.extend(['', '## Interpretation', '',
        '- First-action validity means a legal NS/EW choice, not a feasible full schedule.',
        '- Full-plan validity requires exactly H actions and independently checked signal/queue dynamics.',
        '- Regret and absolute objective gaps use queue-objective units. Relative full-plan gap is saved only when the reference objective is positive.',
        '- Both actions receive zero regret when tied. The tie preference to stay is not an optimization error.',
        '- Repeated calls share instances and are not independent problems. SD summarizes attempts; no significance claim is made.',
        '- Optimal action % uses only valid choices with certified references; always read it beside valid-output rate. Relative gaps are ratios, not percentages.',
        '- Unknown usage and failed-call costs stay missing, not zero. Raw response bodies and all attempts are retained.',
        '- Lookahead is a disclosed development fixture. Longer horizon alone is not evidence of harder planning.',
        '- The SUMO completion/starvation report is a separate secondary evaluation.', ''])
    return '\n'.join(lines)
