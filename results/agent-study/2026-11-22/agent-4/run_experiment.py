"""AI-authored exact-search experiment harness; core search is reused unchanged.

Explicit invocation creates 16 real runs (at most 60 search seconds each).
The reproduction notebook only validates/analyzes saved records by default.
"""
import hashlib
import json
from pathlib import Path
import sys
from datetime import datetime, timezone

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
sys.path.insert(0, str(ROOT))


def main():
    from protection.runner import initialize_single_thread, collect_environment
    initialize_single_thread()
    from protection.exact import search
    from protection.models import load_bundle, to_data
    from protection.program import grading_lock

    cases = [f'n{n}-seed{s}-p{b}' for n in (6,8) for s in (0,1) for b in (20,40)]
    protocol = dict(cases=cases, methods=['exhaustive','branch_bound'],
                    seconds_per_run=60, run_kind='smoke', repeats=1,
                    ordering='alternate method order by case index; all runs serialized',
                    provenance='AI-authored harness; existing protection.exact implementation reused',
                    registered_utc=datetime.now(timezone.utc).isoformat(),
                    environment=collect_environment(),
                    code_sha256={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest()
                                 for p in [Path(__file__).resolve(),ROOT/'protection/exact.py',ROOT/'protection/evaluation.py',ROOT/'protection/flow.py']})
    target=HERE/'records.json'
    if target.exists():
        raise SystemExit('Existing results preserved: use an explicit new study directory for reruns')
    (HERE/'protocol.json').write_text(json.dumps(protocol,ensure_ascii=False,indent=2)+'\n')
    records=[]
    for index,case in enumerate(cases):
        methods=protocol['methods'] if index%2==0 else list(reversed(protocol['methods']))
        for method in methods:
            print('Waiting for shared grading lock:',case,method,flush=True)
            with grading_lock():
                path=ROOT/'scenarios/problem-bank/bundles'/f'{case}.json'
                bundle=load_bundle(path,require_reference=True)
                # Only Scenario is passed: stored reference does not seed the search.
                record=search(bundle.scenario,bundle.budget_percent,method=method,
                              limit_seconds=60,run_kind='smoke')
            reference=bundle.optimal_reference
            row=dict(case=case,bundle_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                     reference=to_data(reference),record=to_data(record))
            records.append(row)
            temp=target.with_suffix('.tmp')
            temp.write_text(json.dumps(records,ensure_ascii=False,indent=2)+'\n')
            temp.replace(target)
            print(case,method,record.status,'search_seconds=',record.search_seconds,
                  'evaluations=',record.evaluated_combinations,flush=True)
    print('Saved',len(records),'runs',flush=True)


if __name__=='__main__':
    main()
