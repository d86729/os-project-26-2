"""Summarize the fixed input, submitted-program, exact and scoring probes."""
from collections import Counter
import json
from pathlib import Path
import statistics

HERE = Path(__file__).resolve().parent


def lines(name):
    return [json.loads(x) for x in (HERE / name).read_text().splitlines()]


def main():
    prepared = lines('preparation.jsonl')
    runs = lines('runs.jsonl')
    exact = lines('exact-pilot.jsonl')
    scoring = lines('scoring-pilot.jsonl')
    assert len(prepared) == 10 and sum(len(x['cases']) for x in prepared) == 20
    assert len(runs) == 40 and len(exact) == 4 and len(scoring) == 5
    sizes = sorted({x['n'] for x in runs})
    methods = ('degree', 'betweenness')
    report = {
        'graphs': len(prepared),
        'cases': sum(len(x['cases']) for x in prepared),
        'runs': len(runs),
        'status_counts': dict(Counter(x['status'] for x in runs)),
        'reference_cases': 0,
        'submission_seconds': {
            str(n): {method: {
                'median': statistics.median(r['submit_seconds'] for r in runs
                                            if r['n'] == n and r['method'] == method),
                'max': max(r['submit_seconds'] for r in runs
                           if r['n'] == n and r['method'] == method),
            } for method in methods} for n in sizes
        },
        'generation_and_first_input_seconds': [
            {k: x[k] for k in ('n', 'seed', 'generation_seconds',
                               'first_input_preparation_seconds', 'total_wall_seconds')}
            for x in prepared
        ],
        'exact_20_second_pilots': [
            {'n': x['n'], 'seed': x['seed'], 'budget_percent': x['budget_percent'],
             'status': x['record']['status'], 'feasible_sets': x['feasible_sets'],
             'evaluated_sets': x['record']['evaluated_combinations'],
             'search_seconds': x['record']['search_seconds'],
             'cache_hits': x['record']['cache_hits']}
            for x in exact
        ],
        'scoring_20_second_pilots': scoring,
        'published_to_web_bank': False,
        'limits': '300s submission / 6GB per-process RLIMIT_AS / 1 CPU, local; not web cgroup',
        'notes': [
            'Runtime probes validate output only; official scoring was attempted separately on representative cases.',
            'Pilot timeouts do not prove infeasibility in three hours; throughput and cache warmth can vary.',
            'All generation uses generation-v1; 20 cases represent 10 graph clusters.',
            'An initial pilot launch failed because scientific imports preceded thread initialization; the script was corrected before any pilot record was written.'
        ],
    }
    (HERE / 'summary.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({k: report[k] for k in ('graphs', 'cases', 'runs', 'status_counts',
                                             'reference_cases', 'submission_seconds')}, indent=2))


if __name__ == '__main__':
    main()
