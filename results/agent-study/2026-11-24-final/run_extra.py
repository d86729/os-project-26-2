"""Execute six frozen stdin strategies against the same 20 certified cases."""
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
from protection.runner import initialize_single_thread, collect_environment

BOOTSTRAP = """import resource, runpy, sys
runpy.run_path(sys.argv[1], run_name='__main__')
with open(sys.argv[2], 'w') as handle:
    handle.write(str(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024))
"""


def set_limits():
    resource.setrlimit(resource.RLIMIT_AS, (6_000_000_000, 6_000_000_000))


def execute(source, stdin, seconds):
    env = {'PATH': '/usr/bin:/bin', 'LANG': 'C.UTF-8', 'OMP_NUM_THREADS': '1',
           'OPENBLAS_NUM_THREADS': '1', 'MKL_NUM_THREADS': '1'}
    with tempfile.TemporaryDirectory(prefix='protection-final-') as temp:
        peak = Path(temp) / 'peak'
        start = time.monotonic()
        proc = subprocess.Popen([sys.executable, '-I', '-c', BOOTSTRAP, str(source), str(peak)],
                                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                cwd=temp, env=env, start_new_session=True, preexec_fn=set_limits)
        try:
            stdout, stderr = proc.communicate(stdin, timeout=seconds)
            reason = 'returned' if proc.returncode == 0 else 'nonzero_exit'
        except subprocess.TimeoutExpired:
            os.killpg(proc.pid, signal.SIGKILL)
            stdout, stderr = proc.communicate()
            reason = 'timeout'
        elapsed = time.monotonic() - start
        if len(stdout) + len(stderr) > 65536:
            reason = 'output_limit'
        return reason, stdout, stderr, elapsed, proc.returncode, int(peak.read_text()) if peak.exists() else None


def main():
    initialize_single_thread()
    from protection.evaluation import Evaluator
    from protection.models import load_bundle
    from protection.program import grading_lock, protected_ids, scenario_input
    os.sched_setaffinity(0, {min(os.sched_getaffinity(0))})
    protocol_path = HERE / 'protocol-extra.json'
    protocol = json.loads(protocol_path.read_text())
    deadline = datetime.fromisoformat(protocol['execution']['hard_stop_kst'])
    for method in protocol['methods']:
        assert sha256((ROOT / method['path']).read_bytes()).hexdigest() == method['sha256']
    env = collect_environment()
    env.update(timestamp_utc=datetime.now(timezone.utc).isoformat(), affinity=sorted(os.sched_getaffinity(0)),
               protocol_sha256=sha256(protocol_path.read_bytes()).hexdigest(),
               runner_sha256=sha256(Path(__file__).read_bytes()).hexdigest(),
               limits='300s wall; 6GB per process RLIMIT_AS; single CPU; local, not web cgroup',
               scoring='official evaluator after submission; separately timed',
               global_lock=str(Path.home() / '.local/state/protection-judge/grading.lock'))
    if (HERE / 'environment-extra.json').exists() or (HERE / 'runs-extra.jsonl').exists():
        raise RuntimeError('output exists; preserve original execution')
    (HERE / 'environment-extra.json').write_text(json.dumps(env, ensure_ascii=False, indent=2) + '\n')
    with (HERE / 'runs-extra.jsonl').open('x', encoding='utf-8') as out:
        for case in protocol['cases']:
            bundle = load_bundle(ROOT / case['path'], require_reference=True)
            stdin = scenario_input(bundle)
            assert bundle.case_id == case['case_id']
            assert sha256(stdin).hexdigest() == case['stdin_sha256']
            reference = bundle.optimal_reference.evaluation
            for method in protocol['methods']:
                row = {**case, 'method': method['method'], 'source_sha256': method['sha256'],
                       'status': 'failed', 'reason': None, 'error': None,
                       'search_seconds': None, 'evaluation_seconds': None, 'peak_rss_bytes': None,
                       'chosen_edges': None, 'cost': None, 'connected_pairs': None,
                       'connected_ratio': None, 'delivery_units': None, 'delivery_ratio': None,
                       'reference_pairs': reference.connected_pairs,
                       'reference_delivery_units': reference.delivery_units,
                       'started_at_utc': datetime.now(timezone.utc).isoformat()}
                remaining = (deadline - datetime.now(timezone.utc)).total_seconds()
                if remaining <= 0:
                    row.update(status='not_run', reason='global_deadline')
                else:
                    try:
                        with grading_lock():
                            remaining = (deadline - datetime.now(timezone.utc)).total_seconds()
                            if remaining <= 0:
                                row.update(status='not_run', reason='global_deadline')
                            else:
                                reason, stdout, stderr, seconds, code, peak = execute(
                                    ROOT / method['path'], stdin, min(300, remaining))
                                row.update(reason=reason, returncode=code, search_seconds=seconds,
                                           peak_rss_bytes=peak, error=stderr.decode(errors='replace')[-2048:] or None)
                                if reason == 'returned':
                                    started = time.monotonic()
                                    ids = protected_ids(stdout, bundle)
                                    value = Evaluator(bundle.scenario).evaluate(list(ids), bundle.budget)
                                    assert value.score <= reference.score
                                    row.update(status='completed', chosen_edges=list(ids), cost=value.cost,
                                               connected_pairs=value.connected_pairs,
                                               connected_ratio=value.connected_ratio,
                                               delivery_units=value.delivery_units,
                                               delivery_ratio=value.delivery_ratio,
                                               evaluation_seconds=time.monotonic()-started)
                                elif reason == 'timeout':
                                    row['status'] = 'timeout' if remaining >= 300 else 'interrupted'
                    except Exception as exc:
                        row.update(reason='runner_or_scoring_error', error=f'{type(exc).__name__}: {exc}')
                out.write(json.dumps(row, ensure_ascii=False, allow_nan=False) + '\n')
                out.flush()
            print(case['name'], 'processed six methods', flush=True)


if __name__ == '__main__':
    main()
