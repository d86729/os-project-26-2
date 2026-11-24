"""Run two frozen stdin programs on the registered cases.

The host user bus could not start the delegated service. This fallback uses a
300-second wall limit and per-process RLIMIT_AS. It does not claim cgroup or
web execution; GNU/Linux ru_maxrss is recorded for the submitted process.
"""
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
initialize_single_thread()

from protection.evaluation import Evaluator
from protection.models import load_bundle
from protection.program import grading_lock, protected_ids, scenario_input

BOOTSTRAP = """import resource, runpy, sys
runpy.run_path(sys.argv[1], run_name='__main__')
with open(sys.argv[2], 'w') as handle:
    handle.write(str(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024))
"""


def set_limits():
    resource.setrlimit(resource.RLIMIT_AS, (6_000_000_000, 6_000_000_000))


def execute(source, stdin):
    env = {'PATH':'/usr/bin:/bin', 'LANG':'C.UTF-8',
           'OMP_NUM_THREADS':'1','OPENBLAS_NUM_THREADS':'1','MKL_NUM_THREADS':'1'}
    with tempfile.TemporaryDirectory(prefix='protection-sized-') as temp:
        peak = Path(temp)/'peak'
        start = time.monotonic()
        proc = subprocess.Popen(
            [sys.executable,'-I','-c',BOOTSTRAP,str(source),str(peak)],
            stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,
            cwd=temp,env=env,start_new_session=True,preexec_fn=set_limits)
        try:
            stdout,stderr=proc.communicate(stdin,timeout=300)
            reason='returned' if proc.returncode == 0 else 'nonzero_exit'
        except subprocess.TimeoutExpired:
            os.killpg(proc.pid,signal.SIGKILL)
            stdout,stderr=proc.communicate()
            reason='timeout'
        elapsed=time.monotonic()-start
        if len(stdout)+len(stderr)>65536:
            reason='output_limit'
        peak_bytes = int(peak.read_text()) if peak.exists() else None
        return reason,stdout,stderr,elapsed,proc.returncode,peak_bytes


def main():
    protocol_path=HERE/'protocol.json'
    protocol=json.loads(protocol_path.read_text())
    cases=json.loads((HERE/'cases.json').read_text())
    output=HERE/'runs.jsonl'
    if output.exists() or (HERE/'environment.json').exists():
        raise RuntimeError('output exists; preserve original run')
    assert len(cases)==20
    cpus=sorted(os.sched_getaffinity(0))
    os.sched_setaffinity(0,{cpus[0]})
    environment=collect_environment()
    environment.update(
        timestamp_utc=datetime.now(timezone.utc).isoformat(),
        protocol_sha256=sha256(protocol_path.read_bytes()).hexdigest(),
        runner_sha256=sha256(Path(__file__).read_bytes()).hexdigest(),
        affinity=sorted(os.sched_getaffinity(0)),
        cgroup=Path('/proc/self/cgroup').read_text().strip(),
        sandbox='standalone local processes; no bubblewrap',
        wall_limit_seconds=300,
        address_space_limit_bytes_per_process=6_000_000_000,
        rss_measurement='ru_maxrss of submitted process; no cgroup aggregate',
        output_limit='64KiB checked after process exit',
        global_lock=str(Path.home()/'.local/state/protection-judge/grading.lock'),
        measured_time='local process startup through output; official scoring separately',
        reason_not_cgroup='user systemd bus could not start delegated service')
    (HERE/'environment.json').write_text(json.dumps(environment,ensure_ascii=False,indent=2)+'\n')
    for method in protocol['strategies']:
        assert sha256((ROOT/method['path']).read_bytes()).hexdigest()==method['sha256']
    with output.open('x',encoding='utf-8') as handle:
        for case in cases:
            bundle=load_bundle(ROOT/case['path'],require_reference=case['reference_available'])
            assert bundle.case_id==case['case_id']
            stdin=scenario_input(bundle)
            assert sha256(stdin).hexdigest()==case['stdin_sha256']
            reference=bundle.optimal_reference.evaluation if bundle.optimal_reference else None
            for method in protocol['strategies']:
                row={**case,'method':method['method'],'source_sha256':method['sha256'],
                    'started_at_utc':datetime.now(timezone.utc).isoformat(),
                    'status':'failed','reason':None,'returncode':None,'error':None,
                    'search_seconds':None,'evaluation_seconds':None,'peak_rss_bytes':None,
                    'chosen_edges':None,'cost':None,'connected_pairs':None,
                    'connected_ratio':None,'delivery_units':None,'delivery_ratio':None,
                    'reference_pairs':reference.connected_pairs if reference else None,
                    'reference_delivery_units':reference.delivery_units if reference else None}
                try:
                    with grading_lock():
                        reason,stdout,stderr,elapsed,code,peak=execute(ROOT/method['path'],stdin)
                        row.update(reason=reason,returncode=code,search_seconds=elapsed,peak_rss_bytes=peak)
                        if reason=='returned':
                            start=time.monotonic()
                            chosen=protected_ids(stdout,bundle)
                            value=Evaluator(bundle.scenario).evaluate(list(chosen),bundle.budget)
                            if reference is not None:
                                assert value.score<=reference.score
                            row.update(status='completed',chosen_edges=list(chosen),cost=value.cost,
                                       connected_pairs=value.connected_pairs,connected_ratio=value.connected_ratio,
                                       delivery_units=value.delivery_units,delivery_ratio=value.delivery_ratio,
                                       evaluation_seconds=time.monotonic()-start)
                        else:
                            row.update(status='timeout' if reason=='timeout' else 'failed',
                                       error=stderr.decode(errors='replace')[-2048:] or None)
                except Exception as error:
                    row.update(reason='runner_or_scoring_error',error=f'{type(error).__name__}: {error}')
                handle.write(json.dumps(row,ensure_ascii=False,allow_nan=False)+'\n')
                handle.flush()
            print(case['name'], 'completed both strategies',flush=True)


if __name__=='__main__':
    main()
