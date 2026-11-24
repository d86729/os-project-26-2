"""Probe the common final evaluator separately with a diagnostic deadline."""
from hashlib import sha256
import json
import os
from pathlib import Path
import resource
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from protection.runner import initialize_single_thread


def limit_memory():
    resource.setrlimit(resource.RLIMIT_AS, (6_000_000_000, 6_000_000_000))


def main():
    initialize_single_thread()
    from protection.models import load_bundle
    from protection.program import grading_lock
    os.sched_setaffinity(0, {min(os.sched_getaffinity(0))})
    if len(sys.argv) == 3 and sys.argv[1] == '--case':
        from protection.evaluation import Evaluator
        data = json.loads(sys.argv[2])
        bundle = load_bundle(ROOT / data['bundle_path'])
        started = time.monotonic()
        value = Evaluator(bundle.scenario).evaluate(data['chosen_edges'], bundle.budget)
        print(json.dumps({'connected_pairs': value.connected_pairs,
                          'delivery_units': value.delivery_units,
                          'cost': value.cost,
                          'evaluation_seconds': time.monotonic() - started}))
        return
    protocol = json.loads((HERE / 'protocol.json').read_text())
    prepared = [json.loads(line) for line in (HERE / 'preparation.jsonl').read_text().splitlines()]
    runs = [json.loads(line) for line in (HERE / 'runs.jsonl').read_text().splitlines()]
    if (HERE / 'scoring-pilot.jsonl').exists():
        raise RuntimeError('scoring results exist; preserve the original run')
    with (HERE / 'scoring-pilot.jsonl').open('x', encoding='utf-8') as out:
        stop = False
        for n in protocol['runtime_probe_sizes']:
            seed = protocol['seeds_by_size'][str(n)][0]
            case = next(c for p in prepared for c in p['cases']
                        if c['n'] == n and c['seed'] == seed and c['budget_percent'] == 20)
            run = next(r for r in runs if r['case_id'] == case['case_id'] and r['method'] == 'degree')
            row = {'case': case['name'], 'n': n, 'seed': seed, 'case_id': case['case_id'],
                   'method': 'degree', 'diagnostic_timeout_seconds': 20,
                   'protocol_sha256': sha256((HERE / 'protocol.json').read_bytes()).hexdigest()}
            if stop:
                row.update(status='not_run', reason='earlier scoring diagnostic failed or timed out')
            else:
                data = {'bundle_path': case['bundle_path'], 'chosen_edges': run['chosen_edges']}
                start = time.monotonic()
                try:
                    with grading_lock():
                        proc = subprocess.run([sys.executable, str(Path(__file__).resolve()), '--case',
                                               json.dumps(data)], text=True, capture_output=True,
                                              timeout=20, preexec_fn=limit_memory)
                    if proc.returncode:
                        row.update(status='failed', error=proc.stderr[-2048:])
                    else:
                        row.update(status='completed', score=json.loads(proc.stdout))
                except subprocess.TimeoutExpired:
                    row.update(status='timeout')
                except Exception as exc:
                    row.update(status='failed', error=f'{type(exc).__name__}: {exc}')
                row['wall_seconds_including_lock_wait'] = time.monotonic() - start
                stop = row['status'] != 'completed'
            out.write(json.dumps(row, ensure_ascii=False, allow_nan=False) + '\n')
            out.flush()
            print(case['name'], row['status'], row.get('wall_seconds_including_lock_wait'), flush=True)


if __name__ == '__main__':
    main()
