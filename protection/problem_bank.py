"""Build an audited fixed bank, stopping expansion at the first unproved graph.

The manifest fixes candidate sizes/seeds before any search. Only graphs with
both exhaustive budget references enter bank.json. This certifies measured
saved inputs, not every possible graph of the same size. Run serially via
python -m protection.problem_bank --manifest PATH.
"""
from pathlib import Path
import argparse
import time

from protection.models import (ExperimentManifest, atomic_json, strict_json_loads,
                               save_scenario, save_bundle, load_bundle,
                               bundle_from_record)


def build_bank(manifest):
    from protection.generation import generate_scenario
    from protection.exact import search
    from protection.runner import collect_environment

    manifest = ExperimentManifest.parse(manifest.to_dict(), manifest.source_path)
    d = manifest.to_dict()
    if d['run_kind'] != 'scale_probe' or d['kind'] != 'preparation':
        raise ValueError('scale_probe preparation manifest required')
    if d['sizes'] != sorted(d['sizes']):
        raise ValueError('candidate sizes must be ascending')
    output = Path(d['output_dir'])
    output.mkdir(parents=True, exist_ok=False)
    atomic_json(output/'manifest.json', d)
    atomic_json(output/'environment.json', collect_environment())
    # Freeze every candidate before looking at scores or durations.
    scenarios = []
    for n in d['sizes']:
        s = generate_scenario(n, d['seeds_by_size'][str(n)][0])
        save_scenario(s, output/'inputs'/f'n{n}-seed{s.seed}.json')
        scenarios.append(s)
    state = {'status': 'running', 'time_limit_per_budget_seconds': 10800,
             'candidate_sizes': d['sizes'], 'accepted_sizes': [], 'cases': [],
             'active': None, 'stop_reason': None,
             'scope': 'saved inputs only; not a bound on all graphs of a size'}
    bank = {'schema_version': 1, 'status': 'building', 'bank': [],
            'accepted_sizes': [], 'excluded_sizes': [], 'not_started_sizes': []}

    def persist():
        atomic_json(output/'progress.json', state, overwrite=True)
        atomic_json(output/'bank.json', bank, overwrite=True)

    persist()
    try:
        for s in scenarios:
            n = len(s.nodes)
            rows = []
            for percent in d['budget_percents']:
                state['active'] = {'n': n, 'seed': s.seed, 'budget_percent': percent}
                persist()
                print(f'START n={n} seed={s.seed} budget={percent}', flush=True)
                start = time.monotonic()
                r = search(s, percent, method='exhaustive', run_kind='scale_probe',
                           manifest=manifest)
                elapsed = time.monotonic()-start
                atomic_json(output/'records'/f'n{n}-seed{s.seed}-p{percent}.json', r)
                accepted = (r.status == 'completed' and r.optimality_proven
                            and r.condition.method == 'exhaustive'
                            and r.search_seconds is not None
                            and r.search_seconds < 10800
                            and elapsed < 10800)
                state['cases'].append({'n': n, 'seed': s.seed, 'edges': len(s.edges),
                    'budget_percent': percent, 'status': r.status,
                    'search_seconds': r.search_seconds, 'wall_seconds': elapsed,
                    'evaluated_combinations': r.evaluated_combinations,
                    'eligible': accepted})
                persist()
                print(f'END n={n} budget={percent} status={r.status} '
                      f'search={r.search_seconds} wall={elapsed:.3f} eligible={accepted}', flush=True)
                if not accepted:
                    bank['excluded_sizes'].append(n)
                    bank['not_started_sizes'] = [v for v in d['sizes'] if v > n]
                    state['stop_reason'] = f'n={n}, budget={percent}: incomplete or over limit'
                    break
                rows.append(r)
            if len(rows) != len(d['budget_percents']):
                break
            # Publish only after BOTH budgets pass; independent re-scoring and readback.
            entries = []
            for r in rows:
                bundle = bundle_from_record(s, r)
                path = output/'bundles'/f'n{n}-seed{s.seed}-p{r.condition.budget_percent}.json'
                save_bundle(bundle, path)
                checked = load_bundle(path, require_reference=True)
                if checked != bundle:
                    raise ValueError('bundle readback mismatch')
                entries.append({'path': str(path.resolve()), 'case_id': checked.case_id})
            bank['bank'].extend(entries)
            bank['accepted_sizes'].append(n)
            state['accepted_sizes'].append(n)
            persist()
        bank['status'] = 'ready' if bank['bank'] else 'empty'
        state['status'] = 'finished'
        state['active'] = None
        if state['stop_reason'] is None:
            state['stop_reason'] = 'all predefined candidates completed; no maximum-size claim'
        persist()
        print('FINISHED accepted sizes='+str(bank['accepted_sizes']), flush=True)
        return bank
    except BaseException as exc:
        state['status'] = 'interrupted' if isinstance(exc, KeyboardInterrupt) else 'failed'
        state['stop_reason'] = f'{type(exc).__name__}: {exc}'
        bank['status'] = 'partial'
        persist()
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', required=True)
    args = parser.parse_args()
    from protection.runner import initialize_single_thread
    initialize_single_thread()
    path = Path(args.manifest)
    manifest = ExperimentManifest.parse(strict_json_loads(path.read_text()), path)
    build_bank(manifest)


if __name__ == '__main__':
    main()
