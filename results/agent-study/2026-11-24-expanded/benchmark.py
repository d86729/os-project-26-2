"""Measure submitted programs, separately from scenario preparation and scoring."""
from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import resource
import signal
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from protection.models import load_bundle
from protection.program import grading_lock, protected_ids


def set_limits():
    resource.setrlimit(resource.RLIMIT_AS, (6_000_000_000, 6_000_000_000))


def execute(source, stdin):
    env = {'PATH': '/usr/bin:/bin', 'LANG': 'C.UTF-8', 'OMP_NUM_THREADS': '1',
           'OPENBLAS_NUM_THREADS': '1', 'MKL_NUM_THREADS': '1'}
    with tempfile.TemporaryDirectory(prefix='protection-size-') as cwd:
        started = time.monotonic()
        proc = subprocess.Popen([sys.executable, '-I', str(source)], stdin=subprocess.PIPE,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, cwd=cwd,
                                env=env, start_new_session=True, preexec_fn=set_limits)
        try:
            stdout, stderr = proc.communicate(stdin, timeout=300)
            reason = 'returned' if proc.returncode == 0 else 'nonzero_exit'
        except subprocess.TimeoutExpired:
            os.killpg(proc.pid, signal.SIGKILL)
            stdout, stderr = proc.communicate()
            reason = 'timeout'
        elapsed = time.monotonic() - started
        if len(stdout) + len(stderr) > 65536:
            reason = 'output_limit'
        return reason, stdout, stderr, elapsed, proc.returncode


def main():
    from protection.runner import initialize_single_thread
    initialize_single_thread()
    os.sched_setaffinity(0, {min(os.sched_getaffinity(0))})
    protocol = json.loads((HERE / 'protocol.json').read_text())
    prepared = [json.loads(line) for line in (HERE / 'preparation.jsonl').read_text().splitlines()]
    if any(p['status'] != 'completed' for p in prepared):
        raise RuntimeError('input preparation failed; do not silently omit cases')
    cases = [case for p in prepared for case in p['cases']]
    if len(cases) != 20:
        raise RuntimeError('the pre-registered 20 cases were not prepared')
    for method in protocol['strategies']:
        if sha256((ROOT / method['path']).read_bytes()).hexdigest() != method['sha256']:
            raise RuntimeError('submitted source differs from registered hash')
    with (HERE / 'runs.jsonl').open('x', encoding='utf-8') as out:
        for case in cases:
            bundle = load_bundle(ROOT / case['bundle_path'])
            stdin = (ROOT / case['input_path']).read_bytes()
            assert bundle.case_id == case['case_id']
            assert sha256(stdin).hexdigest() == case['stdin_sha256']
            for method in protocol['strategies']:
                row = {'case': case['name'], 'n': case['n'], 'seed': case['seed'],
                       'budget_percent': case['budget_percent'], 'case_id': case['case_id'],
                       'method': method['method'], 'source_sha256': method['sha256'],
                       'stdin_sha256': case['stdin_sha256'], 'status': 'failed',
                       'started_at_utc': datetime.now(timezone.utc).isoformat(),
                       'official_scoring_status': 'not_run', 'official_score': None}
                try:
                    with grading_lock():
                        reason, stdout, stderr, seconds, code = execute(ROOT / method['path'], stdin)
                    row.update(reason=reason, submit_seconds=seconds, returncode=code,
                               error=stderr.decode(errors='replace')[-2048:] or None)
                    if reason == 'returned':
                        row.update(status='completed', chosen_edges=list(protected_ids(stdout, bundle)))
                    elif reason == 'timeout':
                        row['status'] = 'timeout'
                except Exception as exc:
                    row.update(reason='runner_or_output_error', error=f'{type(exc).__name__}: {exc}')
                out.write(json.dumps(row, ensure_ascii=False, allow_nan=False) + '\n')
                out.flush()
                print(case['name'], method['method'], row['status'], row.get('submit_seconds'), flush=True)


if __name__ == '__main__':
    main()
