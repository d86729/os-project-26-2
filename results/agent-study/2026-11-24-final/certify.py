"""Probe and attempt registered exact references until the 23:35 KST deadline."""
from contextlib import contextmanager
from datetime import datetime, timezone
import fcntl
from hashlib import sha256
import json
import os
from pathlib import Path
import signal
import sys
import time

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from protection.runner import initialize_single_thread


class OperationalDeadline(Exception):
    pass


def alarm_handler(signum, frame):
    raise OperationalDeadline('registered per-case or 23:35 operational deadline')


@contextmanager
def timed_grading_lock(deadline):
    path = Path.home() / '.local/state/protection-judge/grading.lock'
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    with path.open('a') as handle:
        while True:
            if datetime.now(timezone.utc) >= deadline:
                raise OperationalDeadline('global deadline while waiting for grading lock')
            try:
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                time.sleep(.2)
        try:
            yield
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        raise RuntimeError(f'refusing overwrite: {path}')
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n')


def main():
    initialize_single_thread()
    from protection.evaluation import budget_for
    from protection.exact import search
    from protection.generation import generate_scenario
    from protection.models import (ExperimentManifest, bundle_from_record, feasible_protection_count,
                                   load_bundle, load_scenario, save_scenario, to_data)
    os.sched_setaffinity(0, {min(os.sched_getaffinity(0))})
    if len(sys.argv) != 2 or sys.argv[1] not in ('pilot', 'full', 'pilot12', 'full12', 'pilot13', 'full13'):
        raise ValueError('usage: certify.py pilot|full|pilot12|full12|pilot13|full13')
    suffix = '12' if sys.argv[1].endswith('12') else '13' if sys.argv[1].endswith('13') else ''
    mode = sys.argv[1].removesuffix(suffix) if suffix else sys.argv[1]
    protocol_path = HERE / f'protocol{suffix}.json'
    protocol = json.loads(protocol_path.read_text())
    deadline = datetime.fromisoformat(protocol['execution']['hard_stop_kst'])
    manifest_path = HERE / f'exact-manifest{suffix}.json'
    manifest = ExperimentManifest.parse(json.loads(manifest_path.read_text()), manifest_path)
    stage = HERE / 'staging-bank'
    result_file = HERE / (f'exact-pilot{suffix}.jsonl' if mode == 'pilot' else f'exact-runs{suffix}.jsonl')
    if result_file.exists():
        raise RuntimeError('results exist; preserve original run')
    if mode == 'full' and not (HERE / f'exact-pilot{suffix}.jsonl').exists():
        raise RuntimeError('registered pilot must run first')
    scenarios = []
    for size, seeds in protocol['candidate_graphs'].items():
        for seed in seeds:
            n = int(size)
            path = stage / 'inputs' / f'n{n}-seed{seed}.json'
            if not path.exists():
                save_scenario(generate_scenario(n, seed), path)
            scenario = load_scenario(path)
            assert len(scenario.nodes) == n and scenario.seed == seed
            scenarios.append((n, seed, scenario))
    signal.signal(signal.SIGALRM, alarm_handler)
    with result_file.open('x', encoding='utf-8') as out:
        for n, seed, scenario in scenarios:
            eligible = []
            previous_failed = False
            for percent in protocol['candidate_budget_percents']:
                name = f'n{n}-seed{seed}-p{percent}'
                count = feasible_protection_count(scenario, budget_for(scenario, percent))
                row = {'name': name, 'n': n, 'seed': seed, 'budget_percent': percent,
                       'feasible_sets': str(count), 'protocol_sha256': sha256(protocol_path.read_bytes()).hexdigest(),
                       'mode': mode, 'status': 'not_run'}
                if previous_failed and mode == 'full':
                    row['reason'] = 'previous budget not certified; pair cannot be published'
                elif datetime.now(timezone.utc) >= deadline:
                    row['reason'] = 'global_deadline'
                else:
                    try:
                        with timed_grading_lock(deadline):
                            available = (deadline - datetime.now(timezone.utc)).total_seconds() - 5
                            if available <= 0:
                                raise OperationalDeadline('global deadline before search')
                            if mode == 'pilot':
                                cap = min(protocol['candidate_pilot_limit_seconds'], available)
                                record = search(scenario, percent, method='exhaustive', run_kind='smoke',
                                                limit_seconds=cap)
                            else:
                                cap = min(protocol['candidate_operational_caps_seconds'][str(n)][str(percent)],
                                          available)
                                signal.setitimer(signal.ITIMER_REAL, cap)
                                try:
                                    record = search(scenario, percent, method='exhaustive',
                                                    run_kind='scale_probe', manifest=manifest)
                                finally:
                                    signal.setitimer(signal.ITIMER_REAL, 0)
                        row.update(status=record.status, operational_cap_seconds=cap,
                                   evaluated_sets=record.evaluated_combinations,
                                   preparation_seconds=record.preparation_seconds,
                                   search_seconds=record.search_seconds,
                                   shutdown_seconds=record.shutdown_seconds,
                                   error=record.error_message, record=to_data(record))
                        if mode == 'full':
                            write_json(stage / 'records' / f'{name}.json', to_data(record))
                            elapsed = sum(x or 0 for x in (record.preparation_seconds,
                                                           record.search_seconds, record.shutdown_seconds))
                            if record.status == 'completed' and elapsed < 10800:
                                bundle = bundle_from_record(scenario, record)
                                path = stage / 'bundles' / f'{name}.json'
                                payload = to_data(bundle)
                                payload['artifact_kind'] = 'scenario_bundle'
                                write_json(path, payload)
                                assert load_bundle(path, require_reference=True) == bundle
                                eligible.append(name)
                            else:
                                previous_failed = True
                    except Exception as exc:
                        row.update(status='failed', error=f'{type(exc).__name__}: {exc}')
                        previous_failed = True
                out.write(json.dumps(row, ensure_ascii=False, allow_nan=False) + '\n')
                out.flush()
                print(name, row['status'], row.get('evaluated_sets'), '/', count, flush=True)
            if mode == 'full':
                print(f'n{n}-seed{seed} complete_pair={len(eligible)==2}', flush=True)


if __name__ == '__main__':
    main()
