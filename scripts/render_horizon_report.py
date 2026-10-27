#!/usr/bin/env python3
"""Render saved first-action results as a standalone, dependency-free HTML report."""

import argparse
from collections import defaultdict
from html import escape
import json
import math
from pathlib import Path
import statistics
from urllib.parse import urlencode


NAMES = {'gurobi': 'Gurobi reference', 'stay': 'Stay', 'max-queue': 'Largest queue',
         'short15': '15-second optimizer', 'microsoft': 'Microsoft', 'jev': 'Jev 1.13',
         'luna': 'Luna', 'sol-medium': 'Sol · medium'}
REMOTE = ('microsoft', 'jev', 'luna', 'sol-medium')


def read_rows(path):
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def fmt(value, places=2):
    return '—' if value is None else f'{value:,.{places}f}'


def mean(rows, key):
    values = [r[key] for r in rows if r.get(key) is not None]
    return statistics.mean(values) if values else None


def p95(rows):
    values = sorted(r['latency_ms'] for r in rows if r.get('latency_ms') is not None)
    return values[math.ceil(.95 * len(values)) - 1] / 1000 if values else None


def known_total(rows, key, places=0):
    values = [r[key] for r in rows if r.get(key) is not None]
    suffix = f' ({len(rows) - len(values)} unknown)' if len(values) < len(rows) else ''
    return fmt(sum(values) if values else None, places) + suffix


def table(headers, rows, caption):
    return ('<div class="table-wrap"><table><caption>' + escape(caption) + '</caption><thead><tr>'
            + ''.join('<th scope="col">' + escape(h) + '</th>' for h in headers)
            + '</tr></thead><tbody>' + ''.join('<tr>' + ''.join(
                '<th scope="row">' + cell + '</th>' if i == 0 else '<td>' + cell + '</td>'
                for i, cell in enumerate(row)) + '</tr>' for row in rows)
            + '</tbody></table></div>')


def render(root, sumo=None, replay_base_url=None):
    rows = read_rows(root / 'runs.jsonl')
    manifest = json.loads((root / 'manifest.json').read_text())
    status = json.loads((root / 'status.json').read_text())
    if manifest['mode'] != 'first-action':
        raise ValueError('This presentation is for first-action experiments only')
    remote = [r for r in rows if r['controller'] in REMOTE]
    parts = ['<header><p class="eyebrow">DECISION MODEL LAB / DEVELOPMENT PILOT</p>',
             '<h1>How far ahead<br>can the models plan?</h1>',
             '<p class="intro">Identical frozen traffic problems. Certified optimal continuations. '
             'First-action regret across four planning horizons.</p>',
             '<nav><a href="#regret">Horizon comparison</a><a href="#usage">Latency &amp; cost</a>'
             '<a href="#details">All statistics</a>' + ('<a href="#sumo">Traffic outcomes</a>' if sumo else '')
             + '</nav></header><main><div class="cards">']
    for label, value, note in [
        ('Frozen problems', len({r['instance'] for r in rows}), 'Horizon variants share trajectories'),
        ('Model requests', len(remote), 'All attempts retained'),
        ('Legal responses', f"{sum(r['valid'] for r in remote)}/{len(remote)}", 'Failures remain in the denominator'),
        ('Reported API cost', '$' + known_total(remote, 'cost_usd', 4), 'Includes billed failed responses')]:
        parts.append(f'<article><span>{escape(label)}</span><strong>{escape(str(value))}</strong><small>{escape(note)}</small></article>')
    parts.append('</div><p class="notice">Development evidence only: repeated calls and nested horizons are not '
                 'independent problems. This pilot does not establish a general or monotonic degradation trend.</p>')
    parts.append('<section id="regret"><p class="eyebrow">01 / OPTIMIZATION QUALITY</p><h2>First-action regret</h2>'
                 '<p>Lower is better. Zero means an optimal first action. Each cell is the mean over certified, '
                 'valid responses; the small count shows valid attempts / total attempts. A failure is never scored as zero.</p>')
    for family in manifest['families']:
        body = []
        for name in manifest['models']:
            cells = [escape(NAMES.get(name, name))]
            for horizon in manifest['horizons']:
                group = [r for r in rows if r['family'] == family and r['controller'] == name and r['horizon'] == horizon]
                regret = mean(group, 'regret')
                color = 'neutral' if regret is None else ('good' if regret == 0 else 'costly')
                valid = sum(r['valid'] for r in group)
                cells.append(f'<span class="score {color}">{fmt(regret, 1)}</span><small>{valid}/{len(group)} valid</small>')
            body.append(cells)
        parts.append(table(['Controller'] + [f'{h} seconds' for h in manifest['horizons']], body, family.replace('_', ' ').title()))
    parts.append('<p class="footnote">Regret = cost of the chosen first action with an optimal continuation − '
                 'the best achievable cost. Units: summed end-of-step queues + 0.5 per switch. '
                 'First-action validity does not establish feasibility of a full plan.</p></section>')
    parts.append('<section id="usage"><p class="eyebrow">02 / REQUEST PERFORMANCE</p><h2>Latency, usage &amp; reliability</h2>'
                 '<p>Aggregated across all pilot cases and horizons. Latency and usage include failed calls.</p>')
    body = []
    for name in REMOTE:
        group = [r for r in remote if r['controller'] == name]
        if not group:
            continue
        body.append([escape(NAMES[name]), str(len(group)), f"{sum(r['valid'] for r in group)}/{len(group)}",
                     f"{sum(r.get('optimal_action') is True for r in group)}/{len(group)}",
                     fmt(mean(group, 'latency_ms') / 1000) if mean(group, 'latency_ms') is not None else '—', fmt(p95(group)),
                     known_total(group, 'input_tokens'), known_total(group, 'output_tokens'),
                     '$' + known_total(group, 'cost_usd', 6)])
    parts.append(table(['Model', 'Calls', 'Legal', 'Optimal / all', 'Mean s', 'P95 s', 'Input tokens', 'Output tokens', 'Cost USD'], body, 'Remote model requests'))
    failures = [r for r in remote if not r['valid']]
    if failures:
        parts.append('<div class="notice"><strong>Recorded failures</strong><ul>' + ''.join(
            '<li>' + escape(f"{NAMES[r['controller']]} · {r['family']} · {r['horizon']} s · repeat {r['repeat'] + 1}: {r.get('error', r['status'])}")
            + '</li>' for r in failures) + '</ul></div>')
    parts.append('</section><section id="details"><p class="eyebrow">03 / STRATIFIED RESULTS</p><h2>All benchmark statistics</h2>'
                 '<p>Per family, horizon, and controller. Standard deviation describes attempts, not population uncertainty. '
                 'Gurobi latency includes both offline forced-action solves under a generous budget.</p>')
    groups = defaultdict(list)
    for row in rows:
        groups[(row['family'], row['horizon'], row['controller'])].append(row)
    for family in manifest['families']:
        body = []
        for horizon in manifest['horizons']:
            for name in manifest['models']:
                group = groups[(family, horizon, name)]
                scores = [r['regret'] for r in group if r.get('regret') is not None]
                if not group:
                    continue
                body.append([escape(NAMES.get(name, name)), str(horizon), str(len(group)),
                    str(len({r['physical_identity'] for r in group})), fmt(100 * sum(r['valid'] for r in group) / len(group), 1) + '%',
                    str(len(scores)), fmt(mean(group, 'regret')), fmt(statistics.stdev(scores) if len(scores) > 1 else None),
                    fmt(100 * sum(r.get('optimal_action') is True for r in group) / len(scores), 1) + '%' if scores else '—',
                    fmt(mean(group, 'latency_ms') / 1000) if mean(group, 'latency_ms') is not None else '—', fmt(p95(group)),
                    known_total(group, 'input_tokens'), known_total(group, 'output_tokens'), '$' + known_total(group, 'cost_usd', 6)])
        parts.append('<details><summary>' + escape(family.replace('_', ' ').title()) + '</summary>' + table(
            ['Controller', 'H (s)', 'Attempts', 'Distinct problems', 'Legal %', 'Scored', 'Mean regret', 'SD', 'Optimal / scored',
             'Mean s', 'P95 s', 'Input tokens', 'Output tokens', 'Cost USD'], body, family.title() + ' · detailed results') + '</details>')
    parts.append('</section>')
    if sumo:
        traffic = read_rows(sumo / 'runs.jsonl')
        fresh = all('planning_horizon' in row['config'] for row in traffic)
        horizon_text = ', '.join(str(h) for h in sorted({row['config'].get('planning_horizon', 15) for row in traffic}))
        terminal = (traffic[0].get('planning_objective') or {}).get('terminal_queue_penalty', 0) if traffic else 0
        description = (f'Fresh SUMO replays generated October 21, 2026: planning horizon(s) {horizon_text} seconds. '
                       'Each episode runs for 120 simulated seconds on identical seed-7 demand. '
                       f'The traffic objective includes an additional final-queue penalty of {terminal:g} per queued car. '
                       'These traffic runs use their own recorded objective version, separately from the frozen benchmark above. '
                       'The v7 prompt protocol is used. Select a controller link to watch its saved replay.' if fresh else
                       'Historical 120-second SUMO pilot, seed 7, 15-second planning horizon, v6 prompt protocol. '
                       'Gurobi ran October 19; the four remote controllers ran October 21, 2026.')
        parts.append('<section id="sumo"><p class="eyebrow">04 / SECONDARY EVALUATION</p><h2>Traffic outcomes</h2><p>'
                     + description + ' These are separate closed-loop episodes; later observations diverge after different choices.</p>')
        def traffic_name(row):
            name = escape(NAMES.get(row['controller'], row['controller']))
            if replay_base_url:
                url = replay_base_url + '?' + urlencode({'models': 5, 'saved': 1, 'controller': row['controller'],
                                                         'horizon': row['config'].get('planning_horizon', 15)})
                return '<a href="' + escape(url, quote=True) + '">' + name + '</a>'
            return name
        body = []
        for r in traffic:
            ev = r['evaluation']
            body.append([traffic_name(r), str(r['config'].get('planning_horizon', 15)), f"{r['completed']}/{r['generated']}",
                fmt(ev['completion_percent']) + '%', str(ev['unfinished']), fmt(ev['mean_time_in_system']),
                fmt(r['mean_travel_time']), fmt(r['mean_waiting_time']), str(r['active']), str(r['entry_backlog']), str(r['switches'])])
        parts.append(table(['Controller', 'Horizon s', 'Completed / demand', 'Completion', 'Unfinished', 'Mean system s · all demand',
            'Travel s · completed', 'Wait s · completed', 'Active', 'Entry backlog', 'Switches'], body, 'Completion and time accounting'))
        body = []
        for r in traffic:
            approaches = r['evaluation']['by_approach']
            body.append([traffic_name(r), str(r['config'].get('planning_horizon', 15))] + [
                f"{approaches[a]['completed']}/{approaches[a]['generated']}" for a in ('N', 'S', 'E', 'W')] + [
                fmt(r['mean_decision_ms']), fmt(r['p95_decision_ms']), fmt(r['mean_choice_ms']),
                fmt(r['p95_choice_ms']), fmt(r['max_choice_ms']), str(r['deadline_misses'])])
        parts.append(table(['Controller', 'Horizon s', 'North', 'South', 'East', 'West', 'Mean update ms', 'P95 update ms',
            'Mean choice ms', 'P95 choice ms', 'Max choice ms', 'Over 1 s'], body, 'Approach completions and decision latency'))
        parts.append('<p class="notice">Completed-only travel and waiting means exclude unfinished cars. '
                     'Judge those diagnostics alongside completion and approach coverage. All-demand time in system '
                     'is observed through the cutoff, not eventual trip duration.</p></section>')
    parts.append('<footer><p>Run status: ' + escape(status['status']) + ' · Protocol: ' + escape(manifest['protocol'])
                 + '</p><p class="hash">Experiment ' + escape(manifest['identity']) + '</p>'
                 '<p><a href="report.md">Full Markdown report</a> · <a href="runs.jsonl">Individual attempt data</a> · '
                 '<a href="manifest.json">Frozen configuration</a></p></footer></main>')
    css = """
    :root{color-scheme:light;--ink:#152922;--muted:#5c6d64;--line:#dae3d9;--green:#23583d}
    *{box-sizing:border-box}html{scroll-behavior:smooth}body{margin:0;background:#f6f7f1;color:var(--ink);font:15px/1.6 -apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif}
    header,main{max-width:1320px;margin:auto;padding:54px 48px 0}header{padding-top:70px}.eyebrow{font-size:11px;font-weight:750;letter-spacing:.18em;color:var(--green)}
    h1{font-family:Georgia,serif;font-size:clamp(42px,5vw,68px);font-weight:500;letter-spacing:-.045em;line-height:1.06;margin:22px 0}h2{font:500 34px/1.15 Georgia,serif;margin:12px 0 16px}
    .intro{font-size:18px;max-width:690px;color:var(--muted)}nav{display:flex;gap:24px;flex-wrap:wrap;margin-top:30px}a{color:var(--green);text-underline-offset:5px}
    .cards{display:grid;grid-template-columns:repeat(4,1fr);gap:16px}.cards article{border:1px solid var(--line);border-radius:12px;padding:23px;background:#fff}
    .cards span,small{display:block;color:var(--muted);font-size:12px}.cards strong{display:block;font-size:34px;letter-spacing:-.04em;margin:8px 0}.notice{background:#edf1e5;border-left:3px solid #8b9e6e;padding:18px 22px;margin:26px 0;border-radius:0 8px 8px 0}
    section{padding-top:46px;margin-top:32px;border-top:1px solid var(--line)}section>p{max-width:920px;color:var(--muted)}.table-wrap{overflow-x:auto;border:1px solid var(--line);border-radius:12px;background:white;margin:24px 0}
    table{width:100%;border-collapse:collapse;font-size:13px;font-variant-numeric:tabular-nums;white-space:nowrap}caption{text-align:left;font-size:16px;font-weight:650;padding:19px 22px;border-bottom:1px solid var(--line)}
    th,td{padding:14px 20px;text-align:right;border-bottom:1px solid #edf0e9}thead th{background:#f0f3eb;font-size:11px;color:var(--muted)}th:first-child{text-align:left}tbody th{font-weight:550}
    tbody tr:last-child>*{border-bottom:0}tbody tr:hover{background:#f9faf6}.score{display:inline-block;min-width:68px;padding:4px 14px;border-radius:6px;font-size:20px;font-weight:650}.good{background:#e8f3ec;color:#23583d}.costly{background:#fff0df;color:#96501e}.neutral{background:#edf0ed;color:#69756d}
    td small{font-size:10px;margin-top:5px}.footnote,footer{font-size:12px;color:var(--muted)}details{margin:14px 0;border:1px solid var(--line);border-radius:10px;background:#fff}summary{cursor:pointer;padding:16px 22px;font-weight:600}details .table-wrap{margin:0;border:0;border-top:1px solid var(--line);border-radius:0 0 10px 10px}
    footer{margin-top:60px;padding:24px 0 40px;border-top:1px solid var(--line)}.hash{overflow-wrap:anywhere}ul{padding-left:20px}li{margin:6px 0}
    @media(max-width:760px){header,main{padding:30px 20px 0}.cards{grid-template-columns:repeat(2,1fr)}nav{gap:14px}.cards article{padding:16px}.cards strong{font-size:28px}th,td{padding:12px 15px}}
    @media print{body{background:white}header,main{padding:18px}nav{display:none}.table-wrap{overflow:visible}table{white-space:normal;font-size:9px}th,td{padding:6px}.cards{grid-template-columns:repeat(4,1fr)}section{break-inside:avoid}}
    """
    return '<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Planning horizon · comparison report</title><style>' + css + '</style><body>' + ''.join(parts) + '</body></html>'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_dir', type=Path)
    parser.add_argument('--sumo-dir', type=Path)
    parser.add_argument('--replay-base-url', help='Local replay server URL for saved-run links')
    args = parser.parse_args()
    output = args.run_dir / 'report.html'
    output.write_text(render(args.run_dir, args.sumo_dir, args.replay_base_url), encoding='utf-8')
    print(output.resolve())


if __name__ == '__main__':
    main()
