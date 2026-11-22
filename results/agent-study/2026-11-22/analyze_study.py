"""Reproduce descriptive comparisons from audited, saved web results only.

No web requests, source execution, reference search or parameter tuning.
Paired contrasts use official integer scores. Both budgets remain together
when resampling graphs within each size stratum. Intervals are descriptive,
not multiplicity-adjusted tests or evidence of population-wide superiority.
"""
import csv
import json
from pathlib import Path
import statistics

import numpy as np

HERE = Path(__file__).resolve().parent
CONTRASTS = [
    ('betweenness', 'degree'),
    ('demand_bundle', 'degree'),
    ('local_search', 'connectivity_greedy'),
    ('demand_bundle', 'demand_single'),
]


def read_rows():
    rows = list(csv.DictReader((HERE / 'verified_rows.csv').open(newline='')))
    for row in rows:
        for key in ('n', 'seed', 'budget_percent', 'connected_pairs', 'delivery_units',
                    'optimal_connected_pairs', 'optimal_delivery_units'):
            row[key] = int(row[key]) if row[key] else None
        for key in ('seconds', 'peak_mb', 'connected_ratio', 'delivery_ratio'):
            row[key] = float(row[key]) if row[key] else None
        for key in ('optimal_score_match', 'canonical_optimum_match'):
            row[key] = row[key] == 'True' if row[key] else None
    assert len({(r['stage'], r['method'], r['scenario']) for r in rows}) == len(rows)
    return rows


def method_summary(rows):
    ok = [r for r in rows if r['status'] == 'completed']
    return {
        'runs': len(rows), 'graphs': len({r['graph'] for r in rows}),
        'completed': len(ok), 'failed': len(rows) - len(ok),
        'optimal_score_matches': sum(r['optimal_score_match'] for r in ok),
        'canonical_optimum_matches': sum(r['canonical_optimum_match'] for r in ok),
        'optimal_connectivity_matches': sum(r['connected_pairs'] == r['optimal_connected_pairs'] for r in ok),
        'mean_connected_ratio': statistics.mean(r['connected_ratio'] for r in ok) if ok else None,
        'median_seconds': statistics.median(r['seconds'] for r in ok) if ok else None,
        'max_seconds': max((r['seconds'] for r in ok), default=None),
        'max_peak_mb': max((r['peak_mb'] for r in rows), default=None),
    }


def paired_rows(rows, left, right):
    a = {r['scenario']: r for r in rows if r['method'] == left}
    b = {r['scenario']: r for r in rows if r['method'] == right}
    assert a.keys() == b.keys()
    output = []
    for key in sorted(a):
        x, y = a[key], b[key]
        assert x['case_id'] == y['case_id']
        valid = x['status'] == y['status'] == 'completed'
        item = dict(scenario=key, graph=x['graph'], n=x['n'], budget_percent=x['budget_percent'],
                    jointly_successful=valid, result=None, connected_pp=None, delivery_pp_if_equal=None,
                    seconds_difference=None)
        if valid:
            xs, ys = (x['connected_pairs'], x['delivery_units']), (y['connected_pairs'], y['delivery_units'])
            item.update(result=int(xs > ys) - int(xs < ys),
                        connected_pp=100 * (x['connected_ratio'] - y['connected_ratio']),
                        delivery_pp_if_equal=(x['delivery_units'] - y['delivery_units']) / 10000 if xs[0] == ys[0] else None,
                        seconds_difference=x['seconds'] - y['seconds'])
        output.append(item)
    return output


def cluster_interval(pairs, key):
    """Ratio-of-sums bootstrap preserves conditional denominators and failures."""
    rng = np.random.default_rng(20261122)
    sampled_num = np.zeros(10000)
    sampled_den = np.zeros(10000)
    for n in sorted({p['n'] for p in pairs}):
        graphs = sorted({p['graph'] for p in pairs if p['n'] == n})
        totals = []
        for graph in graphs:
            group = [p for p in pairs if p['graph'] == graph]
            assert len(group) == 2 and {p['budget_percent'] for p in group} == {20, 40}
            values = [p[key] for p in group if p[key] is not None]
            totals.append((sum(values), len(values)))
        totals = np.array(totals, dtype=float)
        sampled = rng.integers(0, len(graphs), size=(10000, len(graphs)))
        sampled_num += totals[sampled, 0].sum(axis=1)
        sampled_den += totals[sampled, 1].sum(axis=1)
    valid = sampled_den > 0
    if not valid.any():
        return None
    return np.quantile(sampled_num[valid] / sampled_den[valid], [.025, .975]).tolist()


def compare(pairs, intervals=False):
    valid = [p for p in pairs if p['jointly_successful']]
    values = lambda key: [p[key] for p in valid if p[key] is not None]
    mean = lambda key: statistics.mean(values(key)) if values(key) else None
    result = {
        'paired_cases': len(pairs), 'graphs': len({p['graph'] for p in pairs}),
        'jointly_successful': len(valid), 'wins': sum(p['result'] == 1 for p in valid),
        'ties': sum(p['result'] == 0 for p in valid), 'losses': sum(p['result'] == -1 for p in valid),
        'mean_connected_pp_difference': mean('connected_pp'),
        'equal_connectivity_cases': len(values('delivery_pp_if_equal')),
        'mean_delivery_pp_difference_if_equal': mean('delivery_pp_if_equal'),
        'mean_seconds_difference': mean('seconds_difference'),
        'net_win_fraction': mean('result'),
    }
    if intervals:
        result['connected_pp_95pct_cluster_interval'] = cluster_interval(pairs, 'connected_pp')
        result['conditional_delivery_pp_95pct_cluster_interval'] = cluster_interval(pairs, 'delivery_pp_if_equal')
        result['net_win_95pct_cluster_interval'] = cluster_interval(pairs, 'result')
    return result


def main():
    rows = read_rows()
    report = {'protocol': 'protocol.json', 'source_freeze': 'source-freeze.json',
              'notes': ['No composite weighted score', 'Graph clusters retain both budgets',
                        'Conditional delivery analysis is not an overall delivery claim',
                        'All intervals descriptive; four contrasts, no corrected significance tests',
                        'Runtime includes cold process start; one run per deterministic case',
                        'Confirmation sizes6,8,10,12 only; n14 exploratory only'], 'stages': {}}
    table, budget_table = [], []
    for stage in ('development', 'confirmation'):
        current = [r for r in rows if r['stage'] == stage]
        methods = {m: method_summary([r for r in current if r['method'] == m])
                   for m in sorted({r['method'] for r in current})}
        contrasts = {}
        for left, right in CONTRASTS:
            pairs = paired_rows(current, left, right)
            contrasts[f'{left} vs {right}'] = compare(pairs, intervals=stage == 'confirmation')
            for budget in (20, 40):
                budget_table.append(dict(stage=stage, left=left, right=right, budget=budget,
                                         **compare([p for p in pairs if p['budget_percent'] == budget])))
        for method, stats in methods.items():
            table.append(dict(stage=stage, method=method, **stats))
        report['stages'][stage] = dict(methods=methods, contrasts=contrasts)
    (HERE / 'study_summary.json').write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + '\n')
    for filename, records in [('method_summary.csv', table), ('budget_contrasts.csv', budget_table)]:
        with (HERE / filename).open('w', newline='') as handle:
            writer = csv.DictWriter(handle, fieldnames=list(records[0]))
            writer.writeheader()
            writer.writerows(records)
    print(json.dumps(report['stages']['confirmation'], ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
