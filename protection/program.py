"""제출 프로그램과 표준 입출력을 주고받고, 제한된 격리 환경에서 직렬로 채점한다."""
import hashlib
from contextlib import contextmanager
import fcntl
import json
import os
from pathlib import Path
import re
import selectors
import shutil
import subprocess
import sys
import tempfile
import time
import uuid

from protection.attacks import prepare_attacks
from protection.context import validate_ids
from protection.models import ExperimentCondition, RunRecord
from protection.runner import collect_environment

MAX_SECONDS = 300
MAX_MEMORY_BYTES = 6_000_000_000
MIN_MEMORY_MB = 256
MAX_SOURCE_BYTES = 128 * 1024
MAX_OUTPUT_BYTES = 64 * 1024
THREAD_ENV = ('OPENBLAS_NUM_THREADS', 'OMP_NUM_THREADS', 'MKL_NUM_THREADS',
              'NUMEXPR_NUM_THREADS', 'BLIS_NUM_THREADS')
# 생성한 자식이 제출 코드를 읽기 전에 먼저 자원 제한 그룹에 들어가도록 한다.
LAUNCH = '''
import os, sys
with open(sys.argv[1] + '/cgroup.procs', 'w') as handle:
    handle.write(str(os.getpid()))
os.execv(sys.argv[2], sys.argv[2:])
'''
BOOTSTRAP = "import runpy,sys; sys.path.insert(0,'/packages'); runpy.run_path('/submission.py',run_name='__main__')"


def state_directory():
    return Path(os.environ.get('PROTECTION_STATE_DIR', Path.home() / '.local/state/protection-judge'))


@contextmanager
def grading_lock():
    """웹·로컬 채점과 문제은행 완전탐색이 같은 호스트에서 겹치지 않도록 한다."""
    state = state_directory()
    state.mkdir(mode=0o700, parents=True, exist_ok=True)
    with (state / 'grading.lock').open('a') as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)
        yield


def scenario_input(bundle, seed=None):
    """문제 본문의 줄 순서로 입력을 만든다. 최적해와 실행 환경 기록은 전달하지 않는다."""
    scenario = bundle.scenario
    attacks = prepare_attacks(scenario).candidates
    rows = [
        (len(scenario.nodes), len(scenario.edges), len(scenario.demands), len(attacks)),
        (bundle.budget, bundle.budget_percent, scenario.seed, -1 if seed is None else seed),
    ]
    rows.extend((node.id, node.x, node.y) for node in scenario.nodes)
    rows.extend((e.id, e.u, e.v, e.capacity_mbps, e.cost) for e in scenario.edges)
    rows.extend((d.id, d.source, d.target, d.amount_mbps) for d in scenario.demands)
    rows.extend((a.id, a.x, a.y, len(a.damaged_edge_ids), *a.damaged_edge_ids) for a in attacks)
    return ('\n'.join(' '.join(map(str, row)) for row in rows) + '\n').encode('ascii')


def protected_ids(output, bundle):
    """출력 형식, 간선 번호의 유효성, 오름차순, 방호 비용을 채점 전에 확인한다."""
    tokens = output.decode('ascii').split()
    if not tokens or len(tokens) > len(bundle.scenario.edges) + 1:
        raise ValueError('출력은 선택 개수와 간선 ID 목록이어야 합니다.')
    if any(re.fullmatch(r'[0-9]{1,10}', token) is None for token in tokens):
        raise ValueError('출력에는 음이 아닌 정수만 사용할 수 있습니다.')
    count, *ids = map(int, tokens)
    if len(ids) != count:
        raise ValueError('선택 개수와 간선 ID 개수가 다릅니다.')
    validate_ids(bundle.scenario, bundle.budget, ids)
    return tuple(sorted(ids))


def scope_root():
    """감독자와 제출 프로세스를 서로 다른 cgroup 하위 그룹에 배치한다."""
    membership = Path('/proc/self/cgroup').read_text().strip()
    if not membership.startswith('0::/'):
        raise RuntimeError('cgroup v2 is required')
    own = Path('/sys/fs/cgroup') / membership[4:].lstrip('/')
    root = own.parent
    if own.name != 'supervisor' or not os.access(root / 'cgroup.subtree_control', os.W_OK):
        raise RuntimeError('run the grader in a delegated service with DelegateSubgroup=supervisor')
    enabled = set((root / 'cgroup.subtree_control').read_text().split())
    missing = {'cpu', 'memory', 'pids'} - enabled
    if missing:
        (root / 'cgroup.subtree_control').write_text(' '.join('+' + controller for controller in sorted(missing)))
    return root


def sandbox_command(source_path):
    """제출에 필요한 실행 파일과 패키지만 읽기 전용으로 연결하고 네트워크를 분리한다."""
    bwrap = shutil.which('bwrap')
    if bwrap is None:
        raise RuntimeError('bubblewrap is required')
    command = [
        bwrap, '--unshare-all', '--unshare-user', '--disable-userns', '--die-with-parent',
        '--new-session', '--clearenv', '--ro-bind', '/usr', '/usr',
        '--symlink', 'usr/lib', '/lib', '--symlink', 'usr/lib64', '/lib64',
        '--symlink', 'usr/bin', '/bin', '--dev', '/dev', '--proc', '/proc',
        '--tmpfs', '/tmp', '--chdir', '/tmp', '--setenv', 'PATH', '/usr/bin',
        '--setenv', 'HOME', '/tmp', '--setenv', 'LANG', 'C.UTF-8',
        '--ro-bind', str(source_path), '/submission.py',
        '--ro-bind', str(Path(sys.prefix) / 'lib' / f'python{sys.version_info.major}.{sys.version_info.minor}' / 'site-packages'), '/packages',
    ]
    for key in THREAD_ENV:
        command.extend(('--setenv', key, '1'))
    return [*command, '/usr/bin/python3', '-I', '-c', BOOTSTRAP]


def capture(process, deadline, cancelled, kill):
    """두 출력 스트림을 번갈아 읽으면서 시간·출력량·취소 요청을 검사한다."""
    stdout = bytearray()
    stderr = bytearray()
    total = 0
    with selectors.DefaultSelector() as selector:
        selector.register(process.stdout, selectors.EVENT_READ, stdout)
        selector.register(process.stderr, selectors.EVENT_READ, stderr)
        while selector.get_map() or process.poll() is None:
            if cancelled():
                kill()
                return 'cancelled', bytes(stdout), bytes(stderr)
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                kill()
                return 'deadline', bytes(stdout), bytes(stderr)
            for key, _ in selector.select(min(.1, remaining)):
                chunk = os.read(key.fd, 8192)
                if not chunk:
                    selector.unregister(key.fd)
                    continue
                total += len(chunk)
                if total > MAX_OUTPUT_BYTES:
                    kill()
                    return 'output_limit', b'', b''
                key.data.extend(chunk)
    return 'exit', bytes(stdout), bytes(stderr)


def execute_program(bundle, source, seconds, memory_bytes, seed, cancelled):
    root = scope_root()
    group = root / ('submission-' + uuid.uuid4().hex)
    group.mkdir()
    process = None
    try:
        # CPU 사용량은 한 코어 분량으로 제한한다. 메모리·프로세스 수는 자손까지 합산한다.
        for filename, value in (('memory.max', memory_bytes), ('memory.swap.max', 0),
                                ('memory.oom.group', 1), ('cpu.max', '100000 100000'),
                                ('pids.max', 32)):
            (group / filename).write_text(str(value))
        def kill():
            # 제출 코드가 자식 프로세스를 띄웠어도 그룹 전체를 종료한다.
            (group / 'cgroup.kill').write_text('1')

        with tempfile.TemporaryDirectory(prefix='protection-source-') as temporary:
            source_path = Path(temporary, 'submission.py')
            source_path.write_bytes(source)
            with tempfile.TemporaryFile() as input_file:
                input_file.write(scenario_input(bundle, seed))
                input_file.seek(0)
                started = time.monotonic()
                process = subprocess.Popen(
                    [sys.executable, '-I', '-c', LAUNCH, str(group), *sandbox_command(source_path)],
                    stdin=input_file, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                    env={'PATH': '/usr/bin:/bin'}, close_fds=True,
                )
                with process.stdout, process.stderr:
                    reason, output, diagnostics = capture(process, started + seconds, cancelled, kill)
                process.wait(timeout=5)
                elapsed = time.monotonic() - started
        events = dict(line.split() for line in (group / 'memory.events').read_text().splitlines())
        peak = int((group / 'memory.peak').read_text())
        # 메모리 초과로 종료됐으면 일반적인 비정상 종료와 구분해 기록한다.
        if reason == 'exit' and int(events['oom_kill']):
            reason = 'memory_limit'
        elif reason == 'exit' and process.returncode == 75:
            reason = 'not_implemented'
        elif reason == 'exit' and process.returncode:
            reason = 'nonzero_exit'
        return reason, output, elapsed, peak, diagnostics
    finally:
        (group / 'cgroup.kill').write_text('1')
        if process is not None:
            if process.poll() is None:
                process.kill()
            process.wait(timeout=5)
        for _ in range(50):
            try:
                group.rmdir()
                break
            except OSError:
                time.sleep(.02)
        else:
            group.rmdir()


def grade_program(bundle, source, *, seconds=MAX_SECONDS, memory_bytes=MAX_MEMORY_BYTES,
                  seed=None, repeat_index=0, repeat_count=1, method='member_1', run_kind='smoke',
                  cancelled=lambda: False):
    """제출 실행과 공식 점수 계산을 분리해 성공한 출력에만 점수를 부여한다."""
    if not 1 <= seconds <= MAX_SECONDS or not MIN_MEMORY_MB * 1_000_000 <= memory_bytes <= MAX_MEMORY_BYTES:
        raise ValueError('invalid grading limits')
    if not 1 <= len(source) <= MAX_SOURCE_BYTES:
        raise ValueError('invalid source size')
    condition = ExperimentCondition(bundle.scenario.scenario_id, bundle.budget_percent,
                                    bundle.budget, method, seconds, memory_bytes)
    base = dict(run_id=uuid.uuid4().hex, condition=condition, case_id=bundle.case_id,
                algorithm_memory_limit_bytes=memory_bytes, algorithm_seed=seed,
                repeat_index=repeat_index, repeat_count=repeat_count, run_kind=run_kind,
                policy_version=bundle.scenario.evaluation_policy.version,
                submission_sha256=hashlib.sha256(source).hexdigest(),
                environment=tuple((key, json.dumps(value, sort_keys=True))
                                  for key, value in collect_environment().items()),
                memory_measurement_method='cgroup v2 memory.peak, aggregate worker memory',
                algorithm_vcpu_limit=1)
    try:
        if cancelled():
            return RunRecord(**base, status='failed', termination_reason='cancelled')
        reason, output, elapsed, peak, diagnostics = execute_program(bundle, source, seconds, memory_bytes, seed, cancelled)
    except (OSError, RuntimeError, subprocess.SubprocessError) as error:
        return RunRecord(**base, status='failed', termination_reason='environment_blocked',
                         error_type=type(error).__name__, error_message=str(error))
    base.update(search_seconds=elapsed, launch_status='started', resource_monitor_supported=True,
                algorithm_peak_memory_bytes=peak)
    if reason != 'exit' or cancelled():
        reason = 'cancelled' if cancelled() else reason
        status = {'deadline': 'timeout', 'memory_limit': 'memory_limit',
                  'not_implemented': 'not_implemented'}.get(reason, 'failed')
        message = diagnostics.decode(errors='replace')[-2048:] if reason == 'nonzero_exit' else None
        return RunRecord(**base, status=status, termination_reason=reason, error_message=message)
    scoring_start = time.monotonic()
    # 제출이 끝난 뒤 감독자가 공통 평가기로 답안을 다시 평가한다.
    try:
        from protection.evaluation import Evaluator
        ids = protected_ids(output, bundle)
        evaluation = Evaluator(bundle.scenario).evaluate(list(ids), bundle.budget)
    except (ValueError, UnicodeError) as error:
        return RunRecord(**base, status='failed', termination_reason='invalid_output',
                         error_type=type(error).__name__, error_message=str(error))
    except Exception as error:
        return RunRecord(**base, status='failed', termination_reason='final_scoring_failed',
                         error_type=type(error).__name__, error_message=str(error))
    if cancelled():
        return RunRecord(**base, status='failed', termination_reason='cancelled')
    return RunRecord(**base, status='completed', termination_reason='returned',
                     submitted_protected_ids=ids, submitted_evaluation=evaluation,
                     final_scoring_seconds=time.monotonic() - scoring_start)
