"""Check source/input identities, re-score outputs, and compare paired cases."""
from collections import Counter
from hashlib import sha256
import json
import os
from pathlib import Path
import statistics
import sys

ROOT=Path(__file__).resolve().parents[3]
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT))
from protection.runner import initialize_single_thread
initialize_single_thread()
from protection.evaluation import Evaluator
from protection.models import feasible_protection_count, load_bundle
from protection.program import scenario_input


def main():
    protocol=json.loads((HERE/'protocol.json').read_text())
    cases=json.loads((HERE/'cases.json').read_text())
    rows=[json.loads(line) for line in (HERE/'runs.jsonl').read_text().splitlines()]
    expected={(c['name'],s['method']) for c in cases for s in protocol['strategies']}
    assert len(rows)==len(expected)==40
    assert {(r['name'],r['method']) for r in rows}==expected
    assert len(cases)==20 and len({(c['n'],c['seed']) for c in cases})==10
    for s in protocol['strategies']:
        assert sha256((ROOT/s['path']).read_bytes()).hexdigest()==s['sha256']
    for case in cases:
        bundle=load_bundle(ROOT/case['path'],require_reference=case['reference_available'])
        assert bundle.case_id==case['case_id']
        assert sha256(scenario_input(bundle)).hexdigest()==case['stdin_sha256']
        assert feasible_protection_count(bundle.scenario,bundle.budget)==case['feasible_sets']
        for row in [r for r in rows if r['name']==case['name'] and r['status']=='completed']:
            evaluator=Evaluator(bundle.scenario)
            value=evaluator.evaluate(row['chosen_edges'],bundle.budget)
            assert (value.connected_pairs,value.delivery_units,value.cost)==(
                row['connected_pairs'],row['delivery_units'],row['cost'])
            if bundle.optimal_reference:
                assert value.score<=bundle.optimal_reference.evaluation.score
    contrasts=[]
    for case in cases:
        a=next(r for r in rows if r['name']==case['name'] and r['method']=='betweenness')
        b=next(r for r in rows if r['name']==case['name'] and r['method']=='degree')
        score_a=(a['connected_pairs'],a['delivery_units']) if a['status']=='completed' else None
        score_b=(b['connected_pairs'],b['delivery_units']) if b['status']=='completed' else None
        outcome=None if score_a is None or score_b is None else (
            'betweenness' if score_a>score_b else 'degree' if score_a<score_b else 'tie')
        contrasts.append({'name':case['name'],'n':case['n'],'budget_percent':case['budget_percent'],
                          'outcome':outcome,'reference_available':case['reference_available'],
                          'betweenness_score':score_a,'degree_score':score_b})
    report={'cases':len(cases),'graphs':10,'runs':len(rows),
            'status_counts':dict(Counter(r['status'] for r in rows)),
            'outcomes':dict(Counter(c['outcome'] for c in contrasts)),
            'outcomes_by_size':{str(n):dict(Counter(c['outcome'] for c in contrasts if c['n']==n))
                                for n in (8,12,16,24,32)},
            'max_submission_seconds':max(r['search_seconds'] for r in rows if r['search_seconds'] is not None),
            'median_submission_seconds':statistics.median(r['search_seconds'] for r in rows if r['search_seconds'] is not None),
            'reference_cases':sum(c['reference_available'] for c in cases),
            'unverified_reference_cases':sum(not c['reference_available'] for c in cases),
            'all_successful_scores_recomputed':True,
            'runtime_environment':'local single CPU, wall 300 s, per-process RLIMIT_AS 6 GB; not web cgroup',
            'results_are_descriptive':'10 graph clusters, 2 budgets per graph; no universal superiority claim',
            'contrasts':contrasts}
    (HERE/'summary.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({k:v for k,v in report.items() if k!='contrasts'},ensure_ascii=False,indent=2))


if __name__=='__main__':
    main()
