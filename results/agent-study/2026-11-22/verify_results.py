"""Audit saved web CSVs against frozen sources and the common evaluator.

This does not submit jobs or rerun participant programs. Recomputed integer
scores avoid deriving official six-decimal scores from rounded CSV floats.
Run explicitly from the repository with .venv/bin/python PATH/verify_results.py.
"""
import csv
import hashlib
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT))

METHODS = {
    'degree': (1, 'degree.py', 'degree-web.csv'),
    'betweenness': (1, 'betweenness.py', 'betweenness-web.csv'),
    'demand_single': (2, 'ablation_single.py', 'ablation_single-web.csv'),
    'demand_bundle': (2, 'submission.py', 'submission-web.csv'),
    'connectivity_greedy': (3, 'greedy.py', 'greedy.csv'),
    'local_search': (3, 'local_search.py', 'local_search.csv'),
}


def main():
    from protection.runner import initialize_single_thread, collect_environment
    initialize_single_thread()
    from protection.models import load_bundle
    from protection.program import grading_lock
    from protection.evaluation import Evaluator

    protocol = json.loads((HERE / 'protocol.json').read_text())
    frozen = json.loads((HERE / 'source-freeze.json').read_text())['sources']
    rows, bundles, evaluators = [], {}, {}
    with grading_lock():
        for stage in ('development', 'confirmation'):
            cases = protocol[stage + '_cases']
            base = HERE if stage == 'development' else HERE / stage
            for method, (agent, source, filename) in METHODS.items():
                relative = f'agent-{agent}/{source}'
                assert hashlib.sha256((HERE / relative).read_bytes()).hexdigest() == frozen[relative]
                csv_path = base / f'agent-{agent}' / filename
                records = list(csv.DictReader(csv_path.open(encoding='utf-8-sig', newline='')))
                assert [r['scenario'] for r in records] == cases, (stage, method, 'case order')
                for record in records:
                    name = record['scenario']
                    if name not in bundles:
                        bundles[name] = load_bundle(ROOT / 'scenarios/problem-bank/bundles' / (name + '.json'), require_reference=True)
                        evaluators[name] = Evaluator(bundles[name].scenario)
                    bundle = bundles[name]
                    assert record['case_id'] == bundle.case_id
                    assert record['seconds_limit'] == '10' and record['memory_limit_mb'] == '512'
                    assert record['algorithm_seed'] == ''
                    n = len(bundle.scenario.nodes)
                    reference = bundle.optimal_reference.evaluation
                    row = dict(stage=stage, method=method, scenario=name,
                               graph=name.rsplit('-p', 1)[0], n=n,
                               seed=bundle.scenario.seed, budget_percent=bundle.budget_percent,
                               case_id=bundle.case_id, source_sha256=frozen[relative],
                               status=record['status'], termination_reason=record['termination_reason'],
                               seconds=float(record['search_seconds']),
                               peak_mb=float(record['worker_peak_mb']),
                               chosen_edges=record['chosen_edges'],
                               optimal_connected_pairs=reference.connected_pairs,
                               optimal_delivery_units=reference.delivery_units,
                               connected_pairs=None, connected_ratio=None, delivery_units=None,
                               delivery_ratio=None, optimal_score_match=None, canonical_optimum_match=None)
                    if record['status'] == 'completed':
                        chosen = list(map(int, record['chosen_edges'].split()))
                        score = evaluators[name].evaluate(chosen, bundle.budget)
                        assert abs(score.connected_ratio - float(record['connected_ratio'])) < 1e-12
                        assert abs(score.delivery_ratio - float(record['delivery_ratio'])) < 1e-12
                        assert reference.connected_pairs - score.connected_pairs == int(record['gap_connected_pairs'])
                        if record['gap_delivery_units']:
                            assert reference.delivery_units - score.delivery_units == int(record['gap_delivery_units'])
                        assert score.score <= reference.score
                        row.update(connected_pairs=score.connected_pairs,
                                   connected_ratio=score.connected_ratio,
                                   delivery_units=score.delivery_units, delivery_ratio=score.delivery_ratio,
                                   optimal_score_match=score.score == reference.score,
                                   canonical_optimum_match=score.defender_key == reference.defender_key)
                    rows.append(row)
                print(stage, method, len(records), 'verified', flush=True)
    target = HERE / 'verified_rows.csv'
    with target.open('w', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    (HERE / 'verification.json').write_text(json.dumps({
        'rows': len(rows), 'cases': len(bundles), 'sources_verified': len(frozen),
        'environment': collect_environment(),
        'method': 'frozen-source hash check, exact case IDs and limits, common-evaluator replay of returned edge sets',
        'timing': 'seconds and peak_mb remain original web execution measurements; replay time excluded',
        'reference': 'optimal score equality and canonical cost/ID tie-break equality are separate',
    }, ensure_ascii=False, indent=2) + '\n')


if __name__ == '__main__':
    main()
