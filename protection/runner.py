"""Single-worker submission supervisor and fail-closed numerical bootstrap."""
from __future__ import annotations

import hashlib
import importlib.metadata
import json
import multiprocessing as mp
import os
from pathlib import Path
import platform
import select
import socket
import sys
import time
import uuid
from dataclasses import replace
from datetime import datetime, timezone

from protection.context import JsonChannel, ProtocolError, validate_ids
from protection.models import (ScenarioBundle, ExperimentCondition, RunRecord, Evaluation,
                               ExperimentManifest, from_data, load_bundle,
                               strict_json_loads, require)
from protection.submission import algorithm_worker

THREAD_VARIABLES = ('OMP_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'MKL_NUM_THREADS')


def initialize_single_thread() -> None:
    """Environment changes cannot undo an already initialized scientific runtime."""
    loaded = [name for name in ('numpy', 'scipy') if name in sys.modules]
    if loaded:
        raise RuntimeError('Initialize before scientific imports: ' + ', '.join(loaded))
    for name in THREAD_VARIABLES:
        os.environ[name] = '1'


def collect_environment() -> dict:
    cpu_info = Path('/proc/cpuinfo').read_text()
    cpu = next((line.split(':', 1)[1].strip() for line in cpu_info.splitlines()
                if line.startswith(('model name', 'Hardware', 'Processor'))), platform.machine())
    mem = dict(line.split(':', 1) for line in Path('/proc/meminfo').read_text().splitlines())
    return {
        'os': platform.platform(), 'cpu': cpu, 'machine': platform.machine(),
        'logical_cpu_count': os.cpu_count(),
        'ram_bytes': int(mem['MemTotal'].split()[0]) * 1024,
        'python': platform.python_version(), 'python_executable': sys.executable,
        'packages': {name: importlib.metadata.version(name) for name in
                     ('numpy', 'networkx', 'scipy', 'pytest', 'nbformat', 'nbclient', 'ipykernel')},
        'thread_environment': {name: os.environ.get(name) for name in THREAD_VARIABLES},
    }


def validate_environment(output: str) -> dict:
    initialize_single_thread()
    report = collect_environment()
    report['initialized_before_scientific_imports'] = True
    path = Path(output)
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        from scipy.optimize import linprog
        from scipy.optimize._highspy._core import _Highs, HighsStatus
        highs = _Highs()
        status = highs.setOptionValue('threads', 1)
        get_status, threads = highs.getOptionValue('threads')
        report['highs_threads_option'] = threads
        report['highs_set_option_status'] = str(status)
        report['highs_get_option_status'] = str(get_status)
        if status != HighsStatus.kOk or get_status != HighsStatus.kOk or threads != 1:
            raise RuntimeError('HiGHS native threads=1 option failed')
        report['process_threads_before'] = len(tuple(Path('/proc/self/task').iterdir()))
        if report['process_threads_before'] != 1:
            raise RuntimeError('process thread count before LP must be 1')
        result = linprog([-1, -1], A_ub=[[1, 1]], b_ub=[10], bounds=[(0, 20)] * 2,
                         method='highs', options={'threads': 1, 'presolve': False, 'disp': True})
        report['process_threads_after'] = len(tuple(Path('/proc/self/task').iterdir()))
        report['lp'] = {'success': bool(result.success), 'status': int(result.status),
                       'objective': float(result.fun) if result.success and result.fun is not None else None,
                       'message': str(result.message)}
        if not result.success:
            raise RuntimeError(result.message)
        if report['process_threads_after'] != 1:
            raise RuntimeError('process thread count after LP must be 1')
    except Exception as exc:
        report['validation_error'] = str(exc)
        raise
    finally:
        path.write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + '\n')
    return report


def _read_rss(pid):
    """Whole live RSS/native high-water RSS, including LP, libraries and cache."""
    lines = Path(f'/proc/{pid}/status').read_text().splitlines()
    if any(line.startswith('State:') and line.split()[1] in ('Z', 'X') for line in lines):
        return 0
    values = {line.split(':', 1)[0]: int(line.split()[1]) * 1024
              for line in lines if line.startswith(('VmRSS:', 'VmHWM:'))}
    if set(values) != {'VmRSS', 'VmHWM'}:
        raise OSError('live RSS/HWM unavailable')
    return max(values.values())


def _error_payload(exc, reason=None):
    return dict(error_type=type(exc).__name__, message=str(exc)[:4096],
                reason=reason or getattr(exc, 'reason', 'execution_error'))


def _shutdown(processes):
    start = time.monotonic()
    for p in processes:
        if p.is_alive():
            p.terminate()
    deadline = time.monotonic() + .2
    for p in processes:
        p.join(max(0, deadline - time.monotonic()))
    for p in processes:
        if p.is_alive():
            p.kill()
    deadline = time.monotonic() + 1
    for p in processes:
        p.join(max(0, deadline - time.monotonic()))
    return time.monotonic() - start, any(p.is_alive() for p in processes)


def _before_deadline(received_ns, deadline_ns):
    return received_ns < deadline_ns


def run_submission(bundle, file, class_name, *, method_id='member_1', limit_seconds=300,
                   memory_limit_bytes=4_000_000_000, algorithm_seed=None, repeat_index=0,
                   repeat_count=1, run_kind='smoke', sample_interval_ms=10,
                   _evaluation_delay_seconds=0, _evaluation_allocation_bytes=0,
                   _evaluation_failure=None):
    """Run one submission in ONE fresh spawn worker containing its Evaluator.

    START through FINAL receipt is the search budget (300s in main). Final
    scoring is outside that budget but in the same RSS-limited worker. Parent
    samples whole-process RSS/HWM every 10ms, never subtracting LP/cache memory.
    Only lifecycle/final/error messages cross IPC, never evaluation calls.
    Diagnostics are returned at FINAL/ERROR only: a forcibly killed worker's
    intermediate candidates/counters are unavailable, not fabricated checkpoints.
    Legacy evaluation_peak_rss_bytes stays None (there is no evaluator process).
    This trusted research runner is not a hostile-code security sandbox.
    """
    require(type(bundle) is ScenarioBundle, 'ScenarioBundle required')
    require(run_kind != 'main' or (limit_seconds == 300 and memory_limit_bytes == 4_000_000_000
        and not (_evaluation_delay_seconds or _evaluation_allocation_bytes or _evaluation_failure)),
        'main requires official limits and no test injections')
    require(type(class_name) is str and class_name.isidentifier(), 'invalid class name')
    require(type(sample_interval_ms) is int and sample_interval_ms == 10, '10ms observation required')
    condition = ExperimentCondition(bundle.scenario.scenario_id, bundle.budget_percent,
        bundle.budget, method_id, limit_seconds, memory_limit_bytes)
    base = RunRecord(uuid.uuid4().hex, condition, case_id=bundle.case_id,
        algorithm_seed=algorithm_seed, repeat_index=repeat_index, repeat_count=repeat_count,
        run_kind=run_kind, algorithm_memory_limit_bytes=memory_limit_bytes,
        policy_version=bundle.scenario.evaluation_policy.version,
        memory_measurement_method='Linux /proc VmRSS/VmHWM (KiB*1024); whole worker including LP/cache',
        memory_sample_interval_ms=sample_interval_ms)
    prep_start = time.monotonic()
    try:
        file = str(Path(file).resolve())
        digest = hashlib.sha256(Path(file).read_bytes()).hexdigest()
    except OSError as exc:
        return replace(base, status='failed', termination_reason='submission_load_error',
                       error_type=type(exc).__name__, error_message=str(exc))
    for name in THREAD_VARIABLES:
        os.environ[name] = '1'
    base = replace(base, submission_sha256=digest,
        environment=tuple((k, json.dumps(v, sort_keys=True)) for k,v in collect_environment().items()))
    parent, child = socket.socketpair()
    channel = JsonChannel(parent, base.run_id)
    worker = mp.get_context('spawn').Process(target=algorithm_worker, args=(child, base.run_id,
        bundle.scenario, bundle.budget, file, class_name, algorithm_seed, repeat_index,
        repeat_count, _evaluation_delay_seconds, _evaluation_allocation_bytes, _evaluation_failure))
    processes, events = [], []
    state = dict(status='failed', termination_reason='worker_failure', resource_monitor_supported=True)
    peak = 0
    last_sample = None
    max_gap = 0.0
    t0 = deadline = final_ns = search_end = None
    submitted = recovered = None
    calls = hits = 0
    final_scoring_seconds = scoring_start = None

    def sample():
        nonlocal peak, last_sample, max_gap
        now = time.monotonic_ns()
        if last_sample is not None:
            max_gap = max(max_gap, (now-last_sample)/1e6)
        last_sample = now
        if worker.pid is not None and worker.is_alive():
            try:
                peak = max(peak, _read_rss(worker.pid))
            except OSError:
                if worker.is_alive():
                    raise
        return peak > memory_limit_bytes

    def wait(timeout=.01):
        select.select([channel.sock], [channel.sock] if channel.outgoing else [], [], max(0, timeout))

    def diagnostics(payload):
        nonlocal calls, hits, recovered
        calls, hits = payload['evaluation_calls'], payload['cache_hits']
        events.append('highs_residual_fallback_solves=' + str(payload.get('fallback_solves', 0)))
        if payload['recovered'] is not None:
            recovered = from_data(Evaluation, payload['recovered'])

    try:
        worker.start()
        processes.append(worker)
        child.close()
        events.append(f'algorithm_pid={worker.pid}')
        setup_deadline = time.monotonic() + 30
        while True:
            if sample():
                state.update(status='memory_limit', termination_reason='memory_limit')
                break
            if time.monotonic() >= setup_deadline:
                raise RuntimeError('worker preparation deadline expired')
            result = channel.step()
            if result is not None:
                msg, _ = result
                if msg['type'] != 'READY':
                    raise RuntimeError('worker preparation failed: ' + str(msg['payload']))
                events.append('evaluation_initial_cache_size=' + str(msg['payload']['cache_size']))
                t0 = time.monotonic_ns()
                deadline = t0 + int(limit_seconds * 1e9)
                state.update(launch_status='started', started_at=datetime.now(timezone.utc).isoformat(),
                             preparation_seconds=time.monotonic()-prep_start)
                channel.queue('START', {'t0_ns': t0, 'limit_seconds': limit_seconds})
                break
            wait()
        while t0 is not None:
            over_memory = sample()
            now = time.monotonic_ns()
            expired = final_ns is None and now >= deadline
            if over_memory or expired:
                state.update(status='memory_limit' if over_memory else 'timeout',
                             termination_reason='memory_limit' if over_memory else 'deadline')
                events.append('observed_memory_limit' if over_memory else 'observed_deadline')
                if search_end is None:
                    search_end = now
                break
            result = channel.step()
            if result is None:
                wait(.01 if final_ns is not None else min(.01, (deadline-now)/1e9))
                continue
            msg, received = result
            kind, payload = msg['type'], msg['payload']
            if kind == 'FINAL' and final_ns is None:
                final_ns = search_end = received
                if sample() or not _before_deadline(received, deadline):
                    state.update(status='memory_limit' if peak > memory_limit_bytes else 'timeout',
                                 termination_reason='memory_limit' if peak > memory_limit_bytes else 'deadline')
                    break
                validate_ids(bundle.scenario, bundle.budget, payload['ids'])
                submitted = tuple(payload['ids'])
                diagnostics(payload)
                events.append('search_termination=final_received')
                scoring_start = time.monotonic()
                channel.queue('SCORE')
            elif kind == 'SCORED' and final_ns is not None:
                if sample():
                    state.update(status='memory_limit', termination_reason='memory_limit')
                    break
                score = from_data(Evaluation, payload['evaluation'])
                require(score.protected_ids == submitted, 'final score must match actual return')
                diagnostics(payload)
                state.update(status='completed', termination_reason='final_received', submitted_evaluation=score)
                channel.queue('ACK')
                channel.flush()
                break
            elif kind == 'ERROR':
                diagnostics(payload)
                state.update(status='not_implemented' if payload['error_type']=='NotImplementedError'
                    else 'timeout' if payload['error_type']=='DeadlineExceeded' else 'failed',
                    termination_reason=payload['reason'], error_type=payload['error_type'],
                    error_message=payload['message'])
                if search_end is None:
                    search_end = received
                break
            else:
                raise ProtocolError('unexpected worker message')
    except OSError as exc:
        monitor_error = not isinstance(exc, (BrokenPipeError, ConnectionResetError))
        state.update(status='failed', termination_reason='resource_monitor_unavailable' if monitor_error else 'protocol_error',
                     resource_monitor_supported=not monitor_error, error_type=type(exc).__name__, error_message=str(exc))
        state.pop('submitted_evaluation', None)
    except BaseException as exc:
        state.update(status='failed', termination_reason='protocol_error' if isinstance(exc, (ProtocolError, EOFError))
                     else 'execution_error', error_type=type(exc).__name__, error_message=str(exc)[:4096])
        state.pop('submitted_evaluation', None)
    finally:
        if t0 is not None and search_end is None:
            search_end = time.monotonic_ns()
        if scoring_start is not None:
            final_scoring_seconds = time.monotonic()-scoring_start
        try:
            if sample():
                state.update(status='memory_limit', termination_reason='memory_limit')
                state.pop('submitted_evaluation', None)
        except OSError:
            state.update(status='failed', termination_reason='resource_monitor_unavailable', resource_monitor_supported=False)
            state.pop('submitted_evaluation', None)
        shutdown_seconds, residual = _shutdown(processes)
        if residual:
            state.update(status='failed', termination_reason='environment_blocked')
            state.pop('submitted_evaluation', None)
            events.append('residual_worker')
        channel.close()
        child.close()
        for process in processes:
            if not process.is_alive():
                process.close()
    return replace(base, **state, submitted_protected_ids=submitted,
        recovered_protected_ids=None if recovered is None else recovered.protected_ids,
        recovered_evaluation=recovered, evaluation_calls=calls, cache_hits=hits,
        t0_monotonic_ns=t0, deadline_monotonic_ns=deadline, final_received_monotonic_ns=final_ns,
        search_seconds=None if t0 is None else max(0, (search_end-t0)/1e9),
        final_scoring_seconds=final_scoring_seconds, shutdown_seconds=shutdown_seconds,
        algorithm_peak_rss_bytes=peak or None, evaluation_peak_rss_bytes=None,
        observed_max_sample_gap_ms=max_gap, events=tuple(events))


def grade_manifest(manifest):
    """저장된 사례와 반복 시드로 웹과 같은 채점기를 로컬에서 실행한다."""
    from protection.program import grade_program, grading_lock

    if not isinstance(manifest, ExperimentManifest):
        path = Path(manifest)
        manifest = ExperimentManifest.parse(strict_json_loads(path.read_text()), path)
    data = manifest.to_dict()
    require(data['kind'] == 'grading', 'grading manifest required')
    submission = data['submission']
    require('class_name' not in submission,
            'legacy manifest: remove submission.class_name and set the memory limit to 6000000000')
    source = Path(submission['file']).read_bytes()
    # 사례와 케이스 ID를 모두 검사한 뒤에만 제출 프로그램을 실행한다.
    bank = []
    for entry in data['bank']:
        bundle = load_bundle(entry['path'], require_reference=data['run_kind'] == 'main')
        require(bundle.case_id == entry['case_id'], 'bank case_id mismatch')
        bank.append(bundle)
    seeds = submission['algorithm_seeds'] if submission['uses_randomness'] else [None]
    with grading_lock():
        return [grade_program(bundle, source, seed=seed, repeat_index=index,
                              repeat_count=len(seeds), method=submission['method_id'],
                              run_kind=data['run_kind'])
                for bundle in bank for index, seed in enumerate(seeds)]



if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='Validate common numerical environment only')
    parser.add_argument('--validate-environment', required=True)
    args = parser.parse_args()
    validate_environment(args.validate_environment)
