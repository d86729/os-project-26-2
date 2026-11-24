"""Run frozen stdin strategies serially on pre-registered saved cases.

This is a local research runner. RLIMIT_AS measures each process's virtual
address space and is distinct from the web judge's aggregate cgroup memory.
"""
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import resource
import signal
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from protection.runner import collect_environment, initialize_single_thread

initialize_single_thread()

from protection.evaluation import Evaluator
from protection.models import RunRecord, bundle_from_record, from_data, load_bundle, strict_json_loads
from protection.program import protected_ids, scenario_input


def digest(data):
    return hashlib.sha256(data).hexdigest()


def limit_address_space():
    resource.setrlimit(resource.RLIMIT_AS, (512_000_000, 512_000_000))


def run_strategy(source, data, timeout):
    env = {
        'PATH': '/usr/bin:/bin',
        'LANG': 'C.UTF-8',
        'PYTHONHASHSEED': '0',
        'OMP_NUM_THREADS': '1',
        'OPENBLAS_NUM_THREADS': '1',
        'MKL_NUM_THREADS': '1',
    }
    started = time.monotonic()
    proc = subprocess.Popen(
        [sys.executable, '-I', str(source)],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        cwd='/tmp', env=env, start_new_session=True, preexec_fn=limit_address_space,
    )
    try:
        stdout, stderr = proc.communicate(data, timeout=timeout)
        elapsed = time.monotonic() - started
    except subprocess.TimeoutExpired:
        os.killpg(proc.pid, signal.SIGKILL)
        stdout, stderr = proc.communicate()
        return 'timeout', stdout, stderr, time.monotonic() - started, proc.returncode
    if len(stdout) + len(stderr) > 65536:
        return 'output_limit', stdout[:2048], stderr[:2048], elapsed, proc.returncode
    if proc.returncode:
        return 'nonzero_exit', stdout, stderr, elapsed, proc.returncode
    return 'returned', stdout, stderr, elapsed, proc.returncode


def main():
    protocol_path = HERE / 'protocol.json'
    protocol = json.loads(protocol_path.read_text(encoding='utf-8'))
    output = HERE / 'runs.jsonl'
    environment_path = HERE / 'environment.json'
    if output.exists() or environment_path.exists():
        raise RuntimeError('result exists, choose a new experiment directory')

    affinity_before = sorted(os.sched_getaffinity(0))
    os.sched_setaffinity(0, {affinity_before[0]})
    for method in protocol['methods']:
        assert digest((ROOT / method['path']).read_bytes()) == method['sha256']
    environment = collect_environment()
    environment.update(
        recorded_at_utc=datetime.now(timezone.utc).isoformat(),
        cpu_affinity_before=affinity_before,
        cpu_affinity_selected=sorted(os.sched_getaffinity(0)),
        cgroup_membership=Path('/proc/self/cgroup').read_text().strip(),
        memory_measurement='RLIMIT_AS 512,000,000 bytes per process; peak RSS not measured',
        output_limit='64KiB checked after process exit',
        runtime_boundary='local subprocess start through stdout/stderr collection',
        evaluation_boundary='common evaluator after submission process exit',
        protocol_sha256=digest(protocol_path.read_bytes()),
        runner_sha256=digest(Path(__file__).read_bytes()),
    )
    environment_path.write_text(json.dumps(environment, ensure_ascii=False, indent=2) + '\n')

    with output.open('x', encoding='utf-8') as handle:
        for index, case in enumerate(protocol['cases'], start=1):
            bundle = load_bundle(ROOT / case['path'], require_reference=True)
            assert bundle.case_id == case['case_id']
            assert len(bundle.scenario.nodes) == case['n']
            assert bundle.scenario.seed == case['seed']
            assert bundle.budget_percent == case['budget_percent']

            record_path = ROOT / 'scenarios/problem-bank/records' / (case['name'] + '.json')
            original = from_data(RunRecord, strict_json_loads(record_path.read_text()))
            assert bundle_from_record(bundle.scenario, original) == bundle
            input_bytes = scenario_input(bundle)
            reference = bundle.optimal_reference.evaluation
            for method in protocol['methods']:
                source = ROOT / method['path']
                assert digest(source.read_bytes()) == method['sha256']
                row = {
                    **case,
                    'method': method['method'],
                    'source_sha256': method['sha256'],
                    'stdin_sha256': digest(input_bytes),
                    'started_at_utc': datetime.now(timezone.utc).isoformat(),
                    'status': 'failed',
                    'termination_reason': None,
                    'return_code': None,
                    'search_seconds': None,
                    'evaluation_seconds': None,
                    'peak_memory_bytes': None,
                    'chosen_edges': None,
                    'cost': None,
                    'connected_pairs': None,
                    'connected_ratio': None,
                    'delivery_units': None,
                    'delivery_ratio': None,
                    'reference_pairs': reference.connected_pairs,
                    'reference_delivery_units': reference.delivery_units,
                    'reference_edges': list(reference.protected_ids),
                    'reference_cost': reference.cost,
                    'certificate_fallback_solves': None,
                    'error': None,
                }
                try:
                    reason, stdout, stderr, elapsed, returncode = run_strategy(
                        source, input_bytes, protocol['execution']['wall_seconds'])
                    row.update(termination_reason=reason, return_code=returncode, search_seconds=elapsed)
                    if reason == 'returned':
                        evaluation_started = time.monotonic()
                        chosen = protected_ids(stdout, bundle)
                        evaluator = Evaluator(bundle.scenario)
                        evaluation = evaluator.evaluate(list(chosen), bundle.budget)
                        assert evaluation.score <= reference.score, 'submitted score exceeds certified reference'
                        row.update(
                            status='completed', chosen_edges=list(chosen), cost=evaluation.cost,
                            connected_pairs=evaluation.connected_pairs, connected_ratio=evaluation.connected_ratio,
                            delivery_units=evaluation.delivery_units, delivery_ratio=evaluation.delivery_ratio,
                            evaluation_seconds=time.monotonic() - evaluation_started,
                            certificate_fallback_solves=evaluator.fallback_solves,
                        )
                    else:
                        row['error'] = stderr.decode('utf-8', errors='replace')[-2048:] or None
                        if reason == 'timeout':
                            row['status'] = 'timeout'
                except Exception as error:
                    row.update(termination_reason='runner_or_scoring_error',
                               error=f'{type(error).__name__}: {error}')
                handle.write(json.dumps(row, ensure_ascii=False, allow_nan=False) + '\n')
                handle.flush()
            if index % 5 == 0 or index == len(protocol['cases']):
                print(f'{index}/{len(protocol["cases"])} cases recorded', flush=True)


if __name__ == '__main__':
    main()
