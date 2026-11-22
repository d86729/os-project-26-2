"""Reproduce descriptive summaries from immutable web CSV evidence."""
import csv
from decimal import Decimal, ROUND_HALF_EVEN
import json
from pathlib import Path
import statistics

HERE = Path(__file__).resolve().parent


def score(row):
    n = int(row['scenario'].split('-')[0][1:])
    pairs = round(float(row['connected_ratio']) * n * (n - 1) / 2)
    units = int((Decimal(row['delivery_ratio']) * 1000000).quantize(Decimal('1'), rounding=ROUND_HALF_EVEN))
    return pairs, units


def summarize(directory=HERE):
    data = {method: list(csv.DictReader((directory / (method + '-web.csv')).open(encoding='utf-8-sig', newline='')))
            for method in ('degree', 'betweenness')}
    protocol = json.loads((directory / 'protocol.json').read_text())
    summary = {'scope': '20-case exploratory/development comparison; not a held-out test', 'methods': {}}
    for method, rows in data.items():
        assert [r['scenario'] for r in rows] == protocol['cases']
        successful = [r for r in rows if r['status'] == 'completed']
        summary['methods'][method] = {
            'completed': len(successful), 'total': len(rows),
            'optimal_score_count': sum(r['gap_connected_pairs'] == '0' and r['gap_delivery_units'] == '0' for r in successful),
            'median_connected_ratio': statistics.median(float(r['connected_ratio']) for r in successful),
            'median_delivery_ratio': statistics.median(float(r['delivery_ratio']) for r in successful),
            'median_search_seconds': statistics.median(float(r['search_seconds']) for r in successful),
            'max_search_seconds': max(float(r['search_seconds']) for r in successful),
            'max_worker_peak_mb': max(float(r['worker_peak_mb']) for r in successful),
        }
    comparisons = []
    for baseline, proposed in zip(data['degree'], data['betweenness']):
        assert baseline['scenario'] == proposed['scenario']
        if baseline['status'] != 'completed' or proposed['status'] != 'completed':
            comparisons.append({'scenario': baseline['scenario'], 'outcome': 'incomplete'})
            continue
        a, b = score(baseline), score(proposed)
        comparisons.append({'scenario': baseline['scenario'], 'baseline_score': list(a), 'proposed_score': list(b),
                            'outcome': 'win' if b > a else 'loss' if b < a else 'tie',
                            'connected_pairs_delta': b[0] - a[0],
                            'delivery_units_delta_when_pairs_equal': b[1] - a[1] if a[0] == b[0] else None})
    summary['paired_outcomes'] = {name: sum(c['outcome'] == name for c in comparisons) for name in ('win', 'tie', 'loss', 'incomplete')}
    summary['by_case'] = comparisons
    summary['inference_limit'] = 'Two budgets share each graph: 20 rows represent 10 graph clusters, not 20 independent draws. No significance or general superiority claimed.'
    return summary


if __name__ == '__main__':
    result = summarize()
    (HERE / 'summary.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({k: v for k, v in result.items() if k != 'by_case'}, indent=2))
