"""Run registered whole-case exact searches and record their live progress."""
from contextlib import contextmanager
from datetime import datetime, timezone
import fcntl
from hashlib import sha256
import json
import os
from pathlib import Path
import signal
import sqlite3
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
PREVIOUS = ROOT / 'results/agent-study/2026-11-24-final/staging-bank'
STATE = Path.home() / '.local/state/protection-judge'
SOURCE_PATHS = (
    'protection/exact.py', 'protection/models.py', 'protection/evaluation.py',
    'protection/flow.py', 'protection/attacks.py', 'protection/generation.py',
    'protection/runner.py', 'protection/program.py', 'protection/errors.py',
)
sys.path.insert(0, str(ROOT))
from protection.runner import initialize_single_thread


class OperationalDeadline(Exception):
    pass


def deadline_handler(signum, frame):
    raise OperationalDeadline('registered operational deadline or web preemption')


def now():
    return datetime.now(timezone.utc)


def source_hashes():
    return {path: sha256((ROOT / path).read_bytes()).hexdigest() for path in SOURCE_PATHS}


def write_json(path, data, *, overwrite=False):
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and not overwrite:
        raise FileExistsError(path)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile('w', encoding='utf-8', dir=path.parent,
                                         suffix='.tmp', delete=False) as handle:
            temporary = Path(handle.name)
            json.dump(data, handle, ensure_ascii=False, indent=2, allow_nan=False)
            handle.write('\n')
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        temporary = None
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def active_web_jobs():
    connection = sqlite3.connect(f'file:{STATE / "judge.sqlite3"}?mode=ro', uri=True, timeout=3)
    try:
        return connection.execute("SELECT COUNT(*) FROM jobs WHERE state IN ('queued','running')").fetchone()[0]
    finally:
        connection.close()


@contextmanager
def grading_lock_until(deadline):
    STATE.mkdir(mode=0o700, parents=True, exist_ok=True)
    with (STATE / 'grading.lock').open('a') as handle:
        while now() < deadline:
            # Do not occupy the shared lock while a team submission is pending.
            if active_web_jobs():
                time.sleep(2)
                continue
            try:
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
                if active_web_jobs():
                    fcntl.flock(handle, fcntl.LOCK_UN)
                    time.sleep(2)
                    continue
                break
            except BlockingIOError:
                time.sleep(.2)
        else:
            raise OperationalDeadline('global deadline while waiting for web grading')
        try:
            yield
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)


class ProgressJSON:
    """Observe exact.search's decoded progress without changing message contents."""
    def __init__(self, context):
        self.context = context
        self.last_write = 0.
        self.latest_count = 0
        self.samples = 0

    def loads(self, *args, **kwargs):
        value = json.loads(*args, **kwargs)
        if isinstance(value, dict) and value.get('type') in ('PROGRESS', 'DONE', 'TIMEOUT', 'ERROR'):
            self.latest_count = value.get('count', self.latest_count)
            self.samples += 1
            current = time.monotonic()
            if current - self.last_write >= 10 or value.get('type') != 'PROGRESS':
                data = {**self.context, 'updated_at_utc': now().isoformat(),
                        'elapsed_seconds': current - self.context['start_monotonic'],
                        'evaluated_combinations': self.latest_count,
                        'evaluation_calls': value.get('calls'), 'cache_hits': value.get('cache_hits'),
                        'fallback_solves': value.get('fallback_solves'), 'worker_message': value.get('type')}
                data.pop('start_monotonic')
                try:
                    write_json(HERE / 'status.json', data, overwrite=True)
                    self.last_write = current
                except OSError:
                    pass
        return value

    def __getattr__(self, name):
        return getattr(json, name)


def make_reference(scenario, record, target, *, write_json_fn):
    from protection.models import bundle_from_record, load_bundle, to_data
    elapsed = sum(x or 0 for x in (record.preparation_seconds, record.search_seconds,
                                   record.shutdown_seconds))
    if not (record.status == 'completed' and record.optimality_proven and elapsed < 10800):
        return None
    bundle = bundle_from_record(scenario, record)
    data = to_data(bundle)
    data['artifact_kind'] = 'scenario_bundle'
    write_json_fn(target, data)
    assert load_bundle(target, require_reference=True) == bundle
    return bundle


def main():
    initialize_single_thread()
    from protection import exact
    from protection.evaluation import budget_for
    from protection.generation import generate_scenario
    from protection.models import (ExperimentManifest, RunRecord, bundle_from_record,
                                   feasible_protection_count, from_data, load_bundle,
                                   load_scenario, to_data)
    from protection.runner import collect_environment
    os.sched_setaffinity(0, {min(os.sched_getaffinity(0))})
    if len(sys.argv) != 2 or sys.argv[1] not in ('smoke', 'first', 'second'):
        raise ValueError('usage: run.py smoke|first|second')
    mode = sys.argv[1]
    protocol_path = HERE / 'protocol.json'
    protocol = json.loads(protocol_path.read_text())
    deadline = datetime.fromisoformat(protocol['hard_stop_kst'])
    if now() >= deadline:
        raise OperationalDeadline('12:45 KST cutoff reached')
    manifest_path = HERE / 'exact-manifest.json'
    manifest = ExperimentManifest.parse(json.loads(manifest_path.read_text()), manifest_path)
    signal.signal(signal.SIGALRM, deadline_handler)
    stage = HERE / 'staging-bank'
    stage.mkdir(exist_ok=True)
    environment_path = HERE / f'environment-{mode}.json'
    if environment_path.exists():
        raise RuntimeError('previous mode exists; preserve existing run')
    env = collect_environment()
    frozen_sources = source_hashes()
    env.update(affinity=sorted(os.sched_getaffinity(0)), mode=mode,
               protocol_sha256=sha256(protocol_path.read_bytes()).hexdigest(),
               run_sha256=sha256(Path(__file__).read_bytes()).hexdigest(),
               source_sha256=frozen_sources,
               wall_cutoff_kst=protocol['hard_stop_kst'],
               lock=str(STATE / 'grading.lock'))
    write_json(environment_path, env)
    outputs = HERE / f'runs-{mode}.jsonl'
    if outputs.exists():
        raise RuntimeError('results exist; preserve previous run')
    with outputs.open('x', encoding='utf-8') as out:
        if mode == 'smoke':
            items = [(6, 0, 20, 10)]
        elif mode == 'first':
            # Verify the old complete 20% record, never use the old partial 40% record.
            first = protocol['first_graph']
            scenario = load_scenario(PREVIOUS / 'inputs/n14-seed1284121877.json')
            previous_record_path = ROOT / first['previous_record']
            previous_bundle_path = ROOT / first['previous_bundle']
            with grading_lock_until(deadline):
                old_record = from_data(RunRecord, json.loads(previous_record_path.read_text()))
                reference = bundle_from_record(scenario, old_record)
                assert reference == load_bundle(previous_bundle_path, require_reference=True)
            write_json(HERE / 'reused-20-percent.json', {
                'case_id': reference.case_id, 'seed': scenario.seed,
                'record_sha256': sha256(previous_record_path.read_bytes()).hexdigest(),
                'bundle_sha256': sha256(previous_bundle_path.read_bytes()).hexdigest(),
                'evaluated_combinations': old_record.evaluated_combinations,
                'search_seconds': old_record.search_seconds,
                'verification': 'single completed exhaustive record, independent re-score and DP count',
            })
            items = [(14, first['seed'], 40, first['operational_cap_seconds'])]
        else:
            second = protocol['second_graph']
            items = [(14, second['seed'], p, second['operational_caps_seconds'][str(p)]) for p in (20, 40)]
        previous_failed = False
        for n, seed, percent, cap in items:
            name = f'n{n}-seed{seed}-p{percent}'
            if previous_failed:
                out.write(json.dumps({'name': name, 'status': 'not_run',
                                      'reason': 'other budget not certified'}) + '\n')
                out.flush()
                continue
            if now() >= deadline:
                out.write(json.dumps({'name': name, 'status': 'not_run', 'reason': '12:45 cutoff'}) + '\n')
                out.flush()
                continue
            scenario = (generate_scenario(n, seed) if mode == 'smoke' else
                        load_scenario(PREVIOUS / 'inputs' / f'n{n}-seed{seed}.json'))
            assert source_hashes() == frozen_sources, 'exact sources changed before execution'
            total = feasible_protection_count(scenario, budget_for(scenario, percent))
            name_path = stage / 'records' / f'{name}.json'
            if name_path.exists():
                raise RuntimeError('existing record; do not overwrite a prior attempt')
            started = now()
            try:
                with grading_lock_until(deadline):
                    available = (deadline - now()).total_seconds() - 5
                    if available <= 0:
                        raise OperationalDeadline('global cutoff before search')
                    actual_cap = min(cap, available)
                    started = now()
                    ctx = {'case': name, 'status': 'running', 'total_combinations': str(total),
                           'actual_started_at_utc': started.isoformat(), 'cap_seconds': actual_cap,
                           'start_monotonic': time.monotonic()}
                    proxy = ProgressJSON(ctx)
                    exact.json = proxy
                    signal.setitimer(signal.ITIMER_REAL, actual_cap)
                    try:
                        if mode == 'smoke':
                            record = exact.search(scenario, percent, method='exhaustive',
                                                  run_kind='smoke', limit_seconds=actual_cap)
                        else:
                            record = exact.search(scenario, percent, method='exhaustive',
                                                  run_kind='scale_probe', manifest=manifest)
                    finally:
                        signal.setitimer(signal.ITIMER_REAL, 0)
                        exact.json = json
                if source_hashes() != frozen_sources:
                    raise RuntimeError('exact sources changed during execution; reject certification')
                result = {'name': name, 'status': record.status, 'operational_cap_seconds': actual_cap,
                          'actual_started_at_utc': started.isoformat(), 'actual_finished_at_utc': now().isoformat(),
                          'total_combinations': str(total), 'evaluated_combinations': record.evaluated_combinations,
                          'progress_messages_observed': proxy.samples, 'last_observed_count': proxy.latest_count,
                          'record': to_data(record)}
                write_json(name_path, to_data(record))
                if record.status == 'completed':
                    assert proxy.latest_count == record.evaluated_combinations == total
                    verification_deadline = datetime.fromisoformat(protocol['delivery_deadline_kst'])
                    with grading_lock_until(verification_deadline):
                        if mode == 'smoke':
                            reference = load_bundle(ROOT / 'scenarios/problem-bank/bundles/n6-seed0-p20.json',
                                                    require_reference=True)
                            assert record.best_evaluation.score == reference.optimal_reference.evaluation.score
                            result['smoke_reference_score_match'] = True
                        else:
                            bundle = make_reference(scenario, record, stage / 'bundles' / f'{name}.json',
                                                    write_json_fn=write_json)
                            assert bundle is not None
                            result['reference_verified'] = True
                else:
                    previous_failed = True
                out.write(json.dumps(result, ensure_ascii=False, allow_nan=False) + '\n')
                out.flush()
                write_json(HERE / 'status.json', {'case': name, 'status': record.status,
                           'actual_started_at_utc': started.isoformat(), 'actual_finished_at_utc': now().isoformat(),
                           'evaluated_combinations': record.evaluated_combinations,
                           'total_combinations': str(total), 'error': record.error_message}, overwrite=True)
                print(name, record.status, record.evaluated_combinations, '/', total, flush=True)
            except Exception as error:
                previous_failed = True
                result = {'name': name, 'status': 'failed', 'actual_started_at_utc': started.isoformat(),
                          'actual_finished_at_utc': now().isoformat(),
                          'error': f'{type(error).__name__}: {error}'}
                out.write(json.dumps(result, ensure_ascii=False) + '\n')
                out.flush()
                write_json(HERE / 'status.json', result, overwrite=True)
                print(name, 'failed', result['error'], flush=True)


if __name__ == '__main__':
    main()
