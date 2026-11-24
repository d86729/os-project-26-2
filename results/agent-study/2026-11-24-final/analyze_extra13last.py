"""Recheck all scores and summarize the pre-defined paired comparisons."""
from collections import Counter
from hashlib import sha256
import json
from pathlib import Path
import statistics
import sys

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from protection.runner import initialize_single_thread


def main():
    initialize_single_thread()
    from protection.evaluation import Evaluator
    from protection.models import load_bundle
    from protection.program import grading_lock, scenario_input
    protocol = json.loads((HERE / 'protocol-extra13last.json').read_text())
    rows = [json.loads(line) for line in (HERE / 'runs-extra13last.jsonl').read_text().splitlines()]
    expected = {(c['name'], m['method']) for c in protocol['cases'] for m in protocol['methods']}
    assert len(rows) == len(expected) == 12
    assert {(r['name'], r['method']) for r in rows} == expected
    for method in protocol['methods']:
        assert sha256((ROOT / method['path']).read_bytes()).hexdigest() == method['sha256']
    for case in protocol['cases']:
        bundle = load_bundle(ROOT / case['path'], require_reference=True)
        assert case['case_id'] == bundle.case_id
        assert case['stdin_sha256'] == sha256(scenario_input(bundle)).hexdigest()
        with grading_lock():
            evaluator = Evaluator(bundle.scenario)
            for row in [r for r in rows if r['name'] == case['name'] and r['status'] == 'completed']:
                value = evaluator.evaluate(row['chosen_edges'], bundle.budget)
                assert (value.connected_pairs, value.delivery_units, value.cost) == (
                    row['connected_pairs'], row['delivery_units'], row['cost'])
                assert value.score <= bundle.optimal_reference.evaluation.score
    methods = {}
    for method in protocol['methods']:
        group = [r for r in rows if r['method'] == method['method']]
        done = [r for r in group if r['status'] == 'completed']
        methods[method['method']] = {
            'statuses': dict(Counter(r['status'] for r in group)),
            'optimal_score_matches': sum((r['connected_pairs'], r['delivery_units']) ==
                                         (r['reference_pairs'], r['reference_delivery_units']) for r in done),
            'mean_connected_ratio': statistics.mean(r['connected_ratio'] for r in done) if done else None,
            'mean_delivery_ratio': statistics.mean(r['delivery_ratio'] for r in done) if done else None,
            'median_submission_seconds': statistics.median(r['search_seconds'] for r in done) if done else None,
            'max_submission_seconds': max((r['search_seconds'] for r in done), default=None),
            'median_evaluation_seconds': statistics.median(r['evaluation_seconds'] for r in done) if done else None,
            'max_evaluation_seconds': max((r['evaluation_seconds'] for r in done), default=None),
        }
    comparisons = []
    for first, second in protocol['predefined_contrasts']:
        pairs = []
        for case in protocol['cases']:
            a = next(r for r in rows if r['name'] == case['name'] and r['method'] == first)
            b = next(r for r in rows if r['name'] == case['name'] and r['method'] == second)
            if a['status'] != 'completed' or b['status'] != 'completed':
                outcome = 'not_compared'
            else:
                sa, sb = (a['connected_pairs'], a['delivery_units']), (b['connected_pairs'], b['delivery_units'])
                outcome = 'win' if sa > sb else 'loss' if sa < sb else 'tie'
            pairs.append({'case': case['name'], 'n': case['n'], 'outcome': outcome})
        comparisons.append({'first': first, 'second': second,
                            'outcomes': dict(Counter(x['outcome'] for x in pairs)),
                            'by_size': {str(n): dict(Counter(x['outcome'] for x in pairs if x['n'] == n))
                                        for n in (13,)}, 'pairs': pairs})
    report = {'cases': len(protocol['cases']),
              'graphs': len({(c['n'], c['seed']) for c in protocol['cases']}),
              'attempts': len(rows), 'status_counts': dict(Counter(r['status'] for r in rows)),
              'all_completed_scores_independently_recomputed': True,
              'methods': methods, 'comparisons': comparisons,
              'limitations': ['1 newly generated graph; its two budgets are not independent',
                              'only one graph; cases and strategies are public',
                              'single generation-v1 synthetic graph family',
                              'local per-process RLIMIT_AS rather than web cgroup']}
    (HERE / 'summary-extra13last.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({k: report[k] for k in ('cases', 'graphs', 'attempts', 'status_counts', 'methods')},
                     ensure_ascii=False, indent=2))
    print(json.dumps([{k: c[k] for k in ('first', 'second', 'outcomes')} for c in comparisons],
                     ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
