"""Run four pre-registered 20-second exhaustive diagnostics, holding the grading lock."""
from hashlib import sha256
import json
import os
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from protection.runner import initialize_single_thread


def main():
    initialize_single_thread()
    from protection.evaluation import budget_for
    from protection.exact import search
    from protection.generation import generate_scenario
    from protection.models import feasible_protection_count, to_data
    from protection.program import grading_lock
    os.sched_setaffinity(0, {min(os.sched_getaffinity(0))})
    protocol = json.loads((HERE / 'protocol.json').read_text())
    destination = HERE / 'exact-pilot.jsonl'
    if destination.exists():
        raise RuntimeError('pilot results exist; preserve the original run')
    with destination.open('x', encoding='utf-8') as out:
        for n in protocol['exact_sizes']:
            for seed in protocol['seeds_by_size'][str(n)]:
                scenario = generate_scenario(n, seed)
                for percent in protocol['budget_percents']:
                    budget = budget_for(scenario, percent)
                    count = feasible_protection_count(scenario, budget)
                    started = time.monotonic()
                    with grading_lock():
                        record = search(scenario, percent, method='exhaustive',
                                        run_kind='smoke', limit_seconds=20)
                    wall = time.monotonic() - started
                    data = {'n': n, 'seed': seed, 'budget_percent': percent,
                            'feasible_sets': str(count), 'wall_seconds_including_lock_wait': wall,
                            'protocol_sha256': sha256((HERE / 'protocol.json').read_bytes()).hexdigest(),
                            'record': to_data(record)}
                    out.write(json.dumps(data, ensure_ascii=False, allow_nan=False) + '\n')
                    out.flush()
                    print(f'n={n} seed={seed} p={percent} {record.status} '
                          f'evaluated={record.evaluated_combinations}/{count}', flush=True)


if __name__ == '__main__':
    main()
