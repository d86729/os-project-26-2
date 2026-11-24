"""Retry incomplete registered cases with longer operational caps before 23:35."""
from datetime import datetime, timezone
from hashlib import sha256
import importlib.util
import json
import os
from pathlib import Path
import signal
import sys

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from protection.runner import initialize_single_thread


def main():
    initialize_single_thread()
    from protection.exact import search
    from protection.models import (ExperimentManifest, RunRecord, bundle_from_record, feasible_protection_count,
                                   from_data, load_scenario, to_data)
    from protection.evaluation import budget_for
    os.sched_setaffinity(0, {min(os.sched_getaffinity(0))})
    spec = importlib.util.spec_from_file_location('registered_certify', HERE / 'certify.py')
    cert = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cert)
    plan_path = HERE / 'retry-plan.json'
    plan = json.loads(plan_path.read_text())
    original = json.loads((HERE / 'protocol.json').read_text())
    assert plan['candidate_graphs'] == original['candidate_graphs']
    deadline = datetime.fromisoformat(plan['hard_stop_kst'])
    assert plan['hard_stop_kst'] == original['execution']['hard_stop_kst']
    manifest_path = HERE / 'exact-manifest.json'
    manifest = ExperimentManifest.parse(json.loads(manifest_path.read_text()), manifest_path)
    stage = HERE / 'staging-bank'
    destination = HERE / 'retry-runs.jsonl'
    if destination.exists():
        raise RuntimeError('retry results exist; preserve original attempt')
    signal.signal(signal.SIGALRM, cert.alarm_handler)
    with destination.open('x', encoding='utf-8') as out:
        for size, seeds in plan['candidate_graphs'].items():
            for seed in seeds:
                n = int(size)
                graph = f'n{n}-seed{seed}'
                scenario = load_scenario(stage / 'inputs' / f'{graph}.json')
                eligible = []
                previous_failed = False
                for percent in (20, 40):
                    name = f'{graph}-p{percent}'
                    original_path = stage / 'records' / f'{name}.json'
                    prior = (from_data(RunRecord, json.loads(original_path.read_text()))
                             if original_path.exists() else None)
                    count = feasible_protection_count(scenario, budget_for(scenario, percent))
                    row = {'name': name, 'n': n, 'seed': seed, 'budget_percent': percent,
                           'feasible_sets': str(count), 'plan_sha256': sha256(plan_path.read_bytes()).hexdigest(),
                           'status': 'not_run'}
                    if prior and prior.status == 'completed' and prior.optimality_proven:
                        row.update(status='reused', original_run_id=prior.run_id)
                        eligible.append(name)
                    elif previous_failed:
                        row['reason'] = 'other budget still not certified'
                    elif datetime.now(timezone.utc) >= deadline:
                        row['reason'] = 'global_deadline'
                    else:
                        try:
                            with cert.timed_grading_lock(deadline):
                                remaining = (deadline - datetime.now(timezone.utc)).total_seconds() - 5
                                if remaining <= 0:
                                    raise cert.OperationalDeadline('global deadline before search')
                                cap = min(plan['retry_caps_seconds'][str(percent)], remaining)
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
                            cert.write_json(stage / 'retry' / 'records' / f'{name}.json', to_data(record))
                            elapsed = sum(x or 0 for x in (record.preparation_seconds,
                                                           record.search_seconds, record.shutdown_seconds))
                            if record.status == 'completed' and elapsed < 10800:
                                bundle = bundle_from_record(scenario, record)
                                data = to_data(bundle)
                                data['artifact_kind'] = 'scenario_bundle'
                                cert.write_json(stage / 'retry' / 'bundles' / f'{name}.json', data)
                                eligible.append(name)
                            else:
                                previous_failed = True
                        except Exception as exc:
                            row.update(status='failed', error=f'{type(exc).__name__}: {exc}')
                            previous_failed = True
                    out.write(json.dumps(row, ensure_ascii=False, allow_nan=False) + '\n')
                    out.flush()
                    print(name, row['status'], row.get('evaluated_sets'), '/', count, flush=True)
                print(graph, 'complete_pair=' + str(len(eligible) == 2), flush=True)


if __name__ == '__main__':
    main()
