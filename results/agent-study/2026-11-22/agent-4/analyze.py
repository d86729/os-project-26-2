"""Validate saved exact-search evidence and reproduce summary/CSV without new runs."""
import csv
import hashlib
import json
from pathlib import Path
from statistics import median

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]


def analyze(write=True):
    protocol=json.loads((HERE/'protocol.json').read_text())
    raw=json.loads((HERE/'records.json').read_text())
    assert len(raw)==len(protocol['cases'])*2
    for path,expected in protocol['code_sha256'].items():
        assert hashlib.sha256((ROOT/path).read_bytes()).hexdigest()==expected, path
    seen=set(); rows=[]
    for item in raw:
        case=item['case']; r=item['record']; ref=item['reference']; method=r['condition']['method']
        assert (case,method) not in seen
        seen.add((case,method))
        assert case in protocol['cases'] and method in protocol['methods']
        assert r['condition']['limit_seconds']==60 and r['run_kind']=='smoke'
        p=ROOT/'scenarios/problem-bank/bundles'/f'{case}.json'
        assert hashlib.sha256(p.read_bytes()).hexdigest()==item['bundle_sha256']
        bundle=json.loads(p.read_text())
        assert bundle['case_id']==r['case_id']
        events={k:int(v) for k,v in (s.split('=',1) for s in r['events'])}
        completed=r['status']=='completed'
        best=r['best_evaluation']
        score_matches=(best is not None and (best['connected_pairs'],best['delivery_units'])==
                       (ref['evaluation']['connected_pairs'],ref['evaluation']['delivery_units']))
        canonical_matches=(score_matches and best['cost']==ref['cost'] and best['protected_ids']==ref['protected_ids'])
        if completed:
            assert r['optimality_proven'] and score_matches and canonical_matches
        else:
            assert not r['optimality_proven']
        # Independent subset-cost DP checks complete exhaustive enumeration.
        expected=[0]*(bundle['budget']+1); expected[0]=1
        for edge in bundle['scenario']['edges']:
            for b in range(bundle['budget'],edge['cost']-1,-1):
                expected[b]+=expected[b-edge['cost']]
        if completed and method=='exhaustive':
            assert r['evaluated_combinations']==sum(expected)
        rows.append(dict(case=case,method=method,status=r['status'],optimality_proven=r['optimality_proven'],
                         matches_reference_score=completed and score_matches,
                         matches_reference_full_tiebreak=completed and canonical_matches,
                         evaluated_combinations=r['evaluated_combinations'],
                         feasible_combinations=sum(expected),evaluation_calls=r['evaluation_calls'],
                         cache_hits=r['cache_hits'],upper_bound_calls=events['upper_bound_calls'],
                         fallback_solves=events['highs_residual_fallback_solves'],
                         search_seconds=r['search_seconds'],preparation_seconds=r['preparation_seconds'],
                         shutdown_seconds=r['shutdown_seconds'],
                         total_seconds=sum(r[k] for k in ['search_seconds','preparation_seconds','shutdown_seconds']),
                         exact_peak_rss_mb=r['exact_peak_rss_bytes']/1e6,
                         error_message=r['error_message']))
    methods={}
    for method in protocol['methods']:
        values=[r for r in rows if r['method']==method]
        methods[method]=dict(completed=sum(r['status']=='completed' for r in values),
            reference_score_matches=sum(r['matches_reference_score'] for r in values),
            full_tiebreak_matches=sum(r['matches_reference_full_tiebreak'] for r in values),
            evaluated_combinations=sum(r['evaluated_combinations'] for r in values),
            evaluation_calls=sum(r['evaluation_calls'] for r in values),
            upper_bound_calls=sum(r['upper_bound_calls'] for r in values),
            fallback_solves=sum(r['fallback_solves'] for r in values),
            median_search_seconds=median(r['search_seconds'] for r in values),
            total_search_seconds=sum(r['search_seconds'] for r in values),
            max_peak_rss_mb=max(r['exact_peak_rss_mb'] for r in values))
    pairs=[]
    for case in protocol['cases']:
        e=next(r for r in rows if r['case']==case and r['method']=='exhaustive')
        b=next(r for r in rows if r['case']==case and r['method']=='branch_bound')
        pairs.append(dict(case=case,exhaustive_evaluations=e['evaluated_combinations'],
            branch_bound_evaluations=b['evaluated_combinations'],
            evaluation_reduction=1-b['evaluated_combinations']/e['evaluated_combinations'],
            upper_bound_calls=b['upper_bound_calls'],
            exhaustive_search_seconds=e['search_seconds'],branch_bound_search_seconds=b['search_seconds'],
            branch_bound_time_ratio=b['search_seconds']/e['search_seconds'],
            search_seconds_difference=b['search_seconds']-e['search_seconds']))
    summary=dict(sample='preparatory exact comparison; 4 graphs with paired budgets, no confirmatory significance claim',
        methods=methods,pairs=pairs,
        branch_bound_faster_cases=sum(r['search_seconds_difference']<0 for r in pairs),
        median_paired_time_ratio=median(r['branch_bound_time_ratio'] for r in pairs),
        aggregate_evaluation_reduction=1-methods['branch_bound']['evaluated_combinations']/methods['exhaustive']['evaluated_combinations'],
        timing_note='search time excludes worker startup and shutdown; web timing is different; one run per method/case',
        policy_note='exhaustive requires rational certificate; branch_bound permits evaluation-v2 fallback; actual fallback counts reported')
    if write:
        (HERE/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
        with (HERE/'results.csv').open('w',newline='') as f:
            writer=csv.DictWriter(f,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
        with (HERE/'comparison.csv').open('w',newline='') as f:
            writer=csv.DictWriter(f,fieldnames=list(pairs[0]));writer.writeheader();writer.writerows(pairs)
    return summary


if __name__=='__main__':
    print(json.dumps(analyze(),ensure_ascii=False,indent=2))
