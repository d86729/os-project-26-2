"""Numerical environment validation and local standard-input grading."""
from __future__ import annotations

import importlib.metadata
import json
import os
from pathlib import Path
import platform
import sys

from protection.models import ExperimentManifest, load_bundle, strict_json_loads, require

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


def grade_manifest(manifest):
    """저장된 각 사례를 한 번씩 웹과 같은 채점기로 실행한다."""
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
    with grading_lock():
        return [grade_program(bundle, source, method=submission['method_id'],
                              run_kind=data['run_kind'])
                for bundle in bank]



if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='Validate common numerical environment only')
    parser.add_argument('--validate-environment', required=True)
    args = parser.parse_args()
    validate_environment(args.validate_environment)
