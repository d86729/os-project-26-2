"""별도 프로세스에서 방호 집합을 탐색하고, 종료 여부와 최적성 근거를 기록한다."""
from __future__ import annotations
import json
import math
import multiprocessing as mp
import os
from pathlib import Path
import time
import uuid
from datetime import datetime, timezone
from protection.models import (Evaluation, ExperimentCondition, RunRecord,
    ScenarioBundle, UpperBound, canonical_json, feasible_protection_count, from_data, to_data)


def _send(conn, payload):
    conn.send_bytes(canonical_json(payload).encode('utf8'))


def _peak(pid):
    rows = Path(f'/proc/{pid}/status').read_text().splitlines()
    values = [int(row.split()[1]) * 1024 for row in rows
              if row.startswith(('VmRSS:', 'VmHWM:'))]
    if not values:
        raise RuntimeError('RSS observation unavailable')
    return max(values)


def _worker(conn, scenario, budget, method):
    # 부모가 spawn 전에 스레드 환경 변수를 설정하므로 작업자의 과학 계산도 단일 스레드로 시작한다.
    from protection.evaluation import Evaluator, connected_pairs
    from protection.attacks import surviving_ids
    from protection.errors import DeadlineExceeded
    evaluator = Evaluator(scenario, require_certificate=method == 'exhaustive')
    _send(conn, {'type':'READY'})
    deadline = json.loads(conn.recv_bytes())['deadline']
    best = None
    count = bounds = 0
    next_progress = 0.

    def check():
        if time.monotonic() >= deadline:
            raise DeadlineExceeded('exact deadline')

    def progress(kind='PROGRESS', error=None):
        _send(conn, {'type':kind, 'best':to_data(best), 'count':count,
                     'bounds':bounds, 'calls':evaluator.evaluation_calls,
                     'fallback_solves':evaluator.fallback_solves,
                     'cache_hits':evaluator.cache_hits, 'error':error})

    def score(ids):
        nonlocal best, count, next_progress
        check()
        value = evaluator.evaluate(ids, budget, deadline=deadline)
        check()
        count += 1
        # 키의 순서는 연결 쌍, 전달 점수, 비용, 간선 번호다. 마지막 두 값은 동점 해를 고른다.
        if best is None or value.defender_key < best.defender_key:
            best = value
        now = time.monotonic()
        # 매 조합마다 IPC를 하면 탐색이 느려진다. 중간 보고만 제한하고 종료 보고에는 최종 건수를 담는다.
        if now >= next_progress:
            progress()
            next_progress = now + .05

    try:
        # 빈 집합도 유효한 방호안이다. DFS에서 만나는 빈 집합은 이미 채점했으므로 건너뛴다.
        score([])
        stack = [(0, (), 0)]
        edges = scenario.edges
        while stack:
            check()
            index, selected, cost = stack.pop()
            if cost > budget:
                continue
            if index == len(edges):
                if selected:
                    score(list(selected))
                continue
            if method == 'branch_bound':
                # 남은 간선을 비용과 무관하게 모두 방호했을 때의 연결 쌍 수는 이 분기의 상한이다.
                virtual = selected + tuple(range(index, len(edges)))
                c = len(scenario.nodes) * (len(scenario.nodes)-1) // 2
                for attack in evaluator.prepared.candidates:
                    check()
                    c = min(c, connected_pairs(scenario, surviving_ids(scenario, attack, virtual)))
                bounds += 1
                if (c, 1000000) < best.score:
                    continue
            # 스택에는 제외 분기를 먼저 넣으므로 실제 방문 순서는 포함 분기가 먼저다.
            stack.append((index+1, selected, cost))
            if cost + edges[index].cost <= budget:
                stack.append((index+1, selected+(index,), cost+edges[index].cost))
        check()
        progress('DONE')
        conn.recv_bytes()  # 부모가 마지막 RSS를 읽고 ACK를 보낼 때까지 대기한다.
    except DeadlineExceeded:
        progress('TIMEOUT')
        conn.recv_bytes()  # Stay observable until supervisor terminates/acknowledges.
    except Exception as exc:
        progress('ERROR', f'{type(exc).__name__}: {exc}')
        conn.recv_bytes()
    finally:
        conn.close()


def execution_limit(scenario, budget_percent, method, limit_seconds, run_kind, manifest):
    """실행 종류와 manifest를 검증해 연구 명세의 시간 한도를 반환한다."""
    from protection.models import ExperimentManifest, strict_json_loads
    if run_kind not in ('smoke', 'main', 'scale_probe'):
        raise ValueError('unknown run_kind')
    if run_kind == 'smoke':
        return 600 if limit_seconds is None else limit_seconds
    if manifest is None:
        raise ValueError('main/scale_probe requires an explicit preparation manifest')
    if limit_seconds is not None:
        raise ValueError('limit override is allowed only for smoke')
    if not isinstance(manifest, ExperimentManifest):
        manifest = ExperimentManifest.parse(strict_json_loads(Path(manifest).read_text()),manifest)
    d = manifest.to_dict()
    n = len(scenario.nodes)
    if (d['kind'] != 'preparation' or d['run_kind'] != run_kind
            or n not in d['sizes'] or scenario.seed not in d['seeds_by_size'][str(n)]
            or budget_percent not in d['budget_percents']):
        raise ValueError('exact case is absent from matching manifest')
    group = d['size_groups'][str(n)]
    if run_kind == 'scale_probe' or group != 'small':
        if method != 'exhaustive':
            raise ValueError('scale/medium-large reference uses exhaustive search only')
        return d['limits']['large_exact_seconds']
    return d['limits']['small_exact_seconds']


def search(scenario, budget_percent, *, method='exhaustive', limit_seconds=None,
           run_kind='smoke', manifest=None):
    """준비와 탐색 시간을 따로 측정하고, 기한 안에 받은 결과만 기록한다.

    실패나 시간 초과에는 현재까지 받은 최선의 해와 모든 미탐색 분기에 유효한 상한을 남긴다.
    """
    from protection.evaluation import budget_for
    from protection.runner import THREAD_VARIABLES, collect_environment
    if method not in ('exhaustive','branch_bound'):
        raise ValueError('unknown exact method')
    limit_seconds = execution_limit(scenario, budget_percent, method, limit_seconds, run_kind, manifest)
    if type(limit_seconds) not in (int,float) or not math.isfinite(limit_seconds) or limit_seconds <= 0:
        raise ValueError('limit_seconds must be finite and positive')
    budget = budget_for(scenario, budget_percent)
    for name in THREAD_VARIABLES:
        os.environ[name] = '1'
    condition = ExperimentCondition(scenario.scenario_id, budget_percent, budget, method, limit_seconds)
    environment = tuple(sorted((key, json.dumps(value, ensure_ascii=False, sort_keys=True))
                               for key,value in collect_environment().items()))
    run_id = uuid.uuid4().hex
    case_id = ScenarioBundle(scenario,budget_percent,budget).case_id
    # 탐색 트리와 별개인 배낭 DP 결과로 완전탐색의 평가 건수를 검사한다.
    expected_count = feasible_protection_count(scenario, budget) if method == 'exhaustive' else None
    prepare_start = time.monotonic()
    ctx = mp.get_context('spawn')
    parent, child = ctx.Pipe()
    process = ctx.Process(target=_worker, args=(child,scenario,budget,method))
    process.start()
    child.close()
    best = None
    count = calls = hits = bounds = peak = fallback_solves = 0
    state, error = 'failed', None
    start = end = None
    preparation = 0.
    try:
        # 준비 시간은 탐색 한도와 별개다. 시작 신호를 받지 못한 작업자는 60초 후 종료한다.
        ready_deadline = prepare_start + 60
        while not parent.poll(.01):
            if not process.is_alive() or time.monotonic() >= ready_deadline:
                raise RuntimeError('exact worker did not become ready')
            peak = max(peak, _peak(process.pid))
        ready = json.loads(parent.recv_bytes())
        if ready.get('type') != 'READY':
            raise RuntimeError('invalid exact READY message')
        peak = max(peak, _peak(process.pid))
        start = time.monotonic()
        preparation = start - prepare_start
        deadline = start + limit_seconds
        _send(parent, {'deadline':deadline})
        state = 'timeout'
        while True:
            now = time.monotonic()
            if now >= deadline:
                end = now
                break
            if process.is_alive():
                peak = max(peak, _peak(process.pid))
            if not parent.poll(min(.01, deadline-now)):
                if not process.is_alive():
                    state, error = 'failed', 'exact worker exited without a terminal message'
                    end = time.monotonic()
                    break
                continue
            message = json.loads(parent.recv_bytes())
            received = time.monotonic()
            if received >= deadline:
                end = received
                break
            if message['best'] is not None:
                best = from_data(Evaluation, message['best'])
            count, calls, hits, bounds = (message[k] for k in ('count','calls','cache_hits','bounds'))
            fallback_solves = message['fallback_solves']
            if message['type'] == 'PROGRESS':
                continue
            end = received
            if message['type'] == 'DONE':
                peak = max(peak, _peak(process.pid))
                if best is None or (expected_count is not None and count != expected_count):
                    state = 'failed'
                    error = 'exact worker did not report complete evaluation coverage'
                else:
                    state = 'completed'
                _send(parent, {'type':'ACK'})
            elif message['type'] == 'TIMEOUT':
                state = 'timeout'
            else:
                state, error = 'failed', message.get('error')
            break
    except Exception as exc:
        state, error = 'failed', f'{type(exc).__name__}: {exc}'
        end = time.monotonic()
    finally:
        shutdown = time.monotonic()
        if state == 'completed':
            process.join(.2)
        if process.is_alive():
            process.terminate()
            process.join(.2)
        if process.is_alive():
            process.kill()
            process.join(1)
        parent.close()
        if process.is_alive():
            raise RuntimeError('exact worker remains alive; batch must stop')
        shutdown_seconds = time.monotonic()-shutdown
        process.close()
    n = len(scenario.nodes)
    upper = (UpperBound(*best.score, 'optimistic_remaining', True) if state == 'completed'
             else UpperBound(n*(n-1)//2, 1000000, 'universal', True))
    return RunRecord(run_id, condition, case_id=case_id, status=state,
        termination_reason=state, started_at=datetime.now(timezone.utc).isoformat(),
        environment=environment, best_protected_ids=None if best is None else best.protected_ids,
        best_evaluation=best, upper_bound=upper, optimality_proven=state=='completed',
        evaluated_combinations=count, evaluation_calls=calls, cache_hits=hits,
        search_seconds=None if start is None else max(0.,end-start),
        preparation_seconds=preparation, shutdown_seconds=shutdown_seconds,
        exact_peak_rss_bytes=peak or None, memory_measurement_method='/proc VmRSS/VmHWM',
        error_message=error, run_kind=run_kind, launch_status='started',
        events=(f'upper_bound_calls={bounds}', f'highs_residual_fallback_solves={fallback_solves}'))
