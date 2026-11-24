"""Summarize pre-registered paired comparisons at the graph-cluster level."""
import csv
import json
from pathlib import Path
import statistics

import numpy as np

HERE = Path(__file__).resolve().parent


def mean(values):
    return statistics.mean(values) if values else None


def compare(rows, left, right, size=None, budget=None):
    selected = [r for r in rows if (size is None or r['n'] == size)
                and (budget is None or r['budget_percent'] == budget)]
    by_key = {(r['name'], r['method']): r for r in selected}
    names = sorted({r['name'] for r in selected})
    pairs = []
    for name in names:
        a, b = by_key[name, left], by_key[name, right]
        assert a['case_id'] == b['case_id']
        jointly_completed = a['status'] == b['status'] == 'completed'
        pair = {'name': name, 'n': a['n'], 'graph': f"n{a['n']}-seed{a['seed']}",
                'budget_percent': a['budget_percent'], 'jointly_completed': jointly_completed,
                'win': None, 'connected_pp': None, 'delivery_pp': None, 'time_diff_seconds': None}
        if jointly_completed:
            score_a, score_b = (a['connected_pairs'], a['delivery_units']), (b['connected_pairs'], b['delivery_units'])
            pair.update(win=int(score_a > score_b) - int(score_a < score_b),
                        connected_pp=100 * (a['connected_ratio'] - b['connected_ratio']),
                        delivery_pp=((a['delivery_units'] - b['delivery_units']) / 10000
                                     if a['connected_pairs'] == b['connected_pairs'] else None),
                        time_diff_seconds=a['search_seconds'] - b['search_seconds'])
        pairs.append(pair)
    completed = [p for p in pairs if p['jointly_completed']]
    values = lambda key: [p[key] for p in completed if p[key] is not None]
    return pairs, {
        'left': left, 'right': right, 'n': size, 'budget_percent': budget,
        'paired_cases': len(pairs), 'jointly_completed': len(completed),
        'wins': values('win').count(1), 'ties': values('win').count(0), 'losses': values('win').count(-1),
        'mean_connected_pp': mean(values('connected_pp')),
        'equal_connected_pairs': len(values('delivery_pp')),
        'mean_delivery_pp_if_equal': mean(values('delivery_pp')),
        'mean_time_diff_seconds': mean(values('time_diff_seconds')),
        'net_win_fraction': mean(values('win')),
    }


def interval(pairs, key, seed, reps):
    rng = np.random.default_rng(seed)
    numerators = np.zeros(reps)
    denominators = np.zeros(reps)
    for n in sorted({p['n'] for p in pairs}):
        graphs = sorted({p['graph'] for p in pairs if p['n'] == n})
        totals = []
        for graph in graphs:
            group = [p for p in pairs if p['graph'] == graph]
            assert len(group) == 2 and {p['budget_percent'] for p in group} == {20, 40}
            values = [p[key] for p in group if p[key] is not None]
            totals.append((sum(values), len(values)))
        totals = np.asarray(totals, dtype=float)
        sampled = rng.integers(0, len(graphs), size=(reps, len(graphs)))
        numerators += totals[sampled, 0].sum(axis=1)
        denominators += totals[sampled, 1].sum(axis=1)
    valid = denominators > 0
    return np.quantile(numerators[valid] / denominators[valid], [0.025, 0.975]).tolist() if valid.any() else None


def write_csv(path, rows):
    with path.open('w', newline='', encoding='utf-8') as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]), lineterminator='\n')
        writer.writeheader()
        writer.writerows(rows)


def main():
    protocol = json.loads((HERE / 'protocol.json').read_text())
    rows = [json.loads(line) for line in (HERE / 'runs.jsonl').read_text().splitlines()]
    expected = {(c['name'], m['method']) for c in protocol['cases'] for m in protocol['methods']}
    assert {(r['name'], r['method']) for r in rows} == expected
    assert len(rows) == len(expected)
    main_rows = [r for r in rows if r['n'] in protocol['analysis']['primary_sizes']]
    exploratory_rows = [r for r in rows if r['n'] in protocol['analysis']['exploratory_sizes']]
    contrasts, detailed = [], []
    summary = {}
    for method in protocol['methods']:
        name = method['method']
        records = [r for r in main_rows if r['method'] == name]
        ok = [r for r in records if r['status'] == 'completed']
        summary[name] = {
            'attempted': len(records), 'completed': len(ok), 'failed': len(records)-len(ok),
            'matched_reference_score': sum((r['connected_pairs'], r['delivery_units']) ==
                                           (r['reference_pairs'], r['reference_delivery_units']) for r in ok),
            'matched_reference_edges': sum(r['chosen_edges'] == r['reference_edges'] for r in ok),
            'matched_reference_connectivity': sum(r['connected_pairs'] == r['reference_pairs'] for r in ok),
            'mean_connected_ratio': mean([r['connected_ratio'] for r in ok]),
            'median_submission_seconds': statistics.median(r['search_seconds'] for r in ok) if ok else None,
            'median_evaluation_seconds': statistics.median(r['evaluation_seconds'] for r in ok) if ok else None,
        }
    for left, right in protocol['predefined_contrasts']:
        pairs, result = compare(main_rows, left, right)
        for key in ('win', 'connected_pp', 'delivery_pp'):
            result[f'{key}_95pct_cluster_interval'] = interval(
                pairs, key, protocol['analysis']['bootstrap_seed'], protocol['analysis']['bootstrap_replicates'])
        contrasts.append(result)
        for n in protocol['analysis']['primary_sizes'] + protocol['analysis']['exploratory_sizes']:
            for percent in (20,40):
                _, record = compare(rows, left, right, size=n, budget=percent)
                detailed.append(record)
    report = {
        'primary': {'n6_graphs':25, 'n8_graphs':15, 'n10_graphs':5,
                    'graphs':45, 'cases':90, 'methods':summary, 'contrasts':contrasts},
        'exploratory_n12': {'graphs':1, 'cases':len({r['name'] for r in exploratory_rows}),
                            'note':'한 그래프만 있어 별도 기술'},
        'notes':protocol['restrictions'] + [
            'Graph-cluster 95% intervals are descriptive and preserve both budgets.',
            'Delivery pp differences are conditional on equal connected pairs.',
            'No adjusted hypothesis testing or ranking by unplanned comparisons.',
            'Local process time differs from cgroup web timing.',
        ],
    }
    (HERE / 'summary.json').write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + '\n')
    write_csv(HERE / 'method_summary.csv', [dict(method=k, **v) for k,v in summary.items()])
    write_csv(HERE / 'contrasts_by_size_budget.csv', detailed)
    print(json.dumps(report['primary'], ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
