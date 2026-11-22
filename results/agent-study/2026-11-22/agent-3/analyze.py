"""Analyze all registered rows, preserving lexicographic scores and failures."""
import csv
from decimal import Decimal, ROUND_HALF_EVEN
import json
from pathlib import Path
import statistics


def analyze(directory):
    root = Path(directory)
    protocol = json.loads((root / 'protocol.json').read_text())
    variants = {}
    summary = {}
    for variant in protocol['variants']:
        with (root / (variant + '.csv')).open(encoding='utf-8-sig', newline='') as handle:
            rows = list(csv.DictReader(handle))
        assert [r['scenario'] for r in rows] == protocol['cases']
        variants[variant] = {r['scenario']: r for r in rows}
        completed = [r for r in rows if r['status'] == 'completed']
        summary[variant] = {
            'total': len(rows), 'completed': len(completed),
            'failures': [r for r in rows if r['status'] != 'completed'],
            'optimal_score_count': sum(r['gap_connected_pairs'] == '0' and r['gap_delivery_units'] == '0' for r in completed),
            'median_seconds': statistics.median(float(r['search_seconds']) for r in completed),
            'max_seconds': max(float(r['search_seconds']) for r in completed),
            'max_peak_mb': max(float(r['worker_peak_mb']) for r in completed),
        }

    def score(row):
        n = int(row['scenario'].split('-')[0][1:])
        pairs = round(float(row['connected_ratio']) * n * (n-1) / 2)
        units = int((Decimal(row['delivery_ratio']) * 1000000).quantize(Decimal(1), rounding=ROUND_HALF_EVEN))
        return pairs, units

    comparisons = []
    for case in protocol['cases']:
        base = variants['greedy'][case]
        improved = variants['local_search'][case]
        entry = {'scenario': case, 'greedy_status': base['status'], 'local_search_status': improved['status']}
        if base['status'] == improved['status'] == 'completed':
            b, a = score(base), score(improved)
            entry.update(greedy_score=b, local_search_score=a,
                         outcome='improved' if a > b else 'worsened' if a < b else 'tied',
                         connected_pairs_change=a[0]-b[0],
                         delivery_units_change_when_connected_tied=a[1]-b[1] if a[0] == b[0] else None)
        else:
            entry['outcome'] = 'incomplete'
        comparisons.append(entry)
    return {'scope': 'development/pilot: 10 graphs, 20 paired budget cases; not independent 20 graphs',
            'summary': summary,
            'paired_counts': {label: sum(r['outcome'] == label for r in comparisons)
                              for label in ['improved', 'tied', 'worsened', 'incomplete']},
            'comparisons': comparisons}


if __name__ == '__main__':
    root = Path(__file__).resolve().parent
    result = analyze(root)
    (root / 'analysis.json').write_text(json.dumps(result, indent=2)+'\n')
    print(json.dumps({k: v for k, v in result.items() if k != 'comparisons'}, indent=2))
