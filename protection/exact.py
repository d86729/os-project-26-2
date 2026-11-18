"""Exact DFS in a separately supervised process; no team memory limit.

Certificates mean exhaustive completion under the fixed evaluation policy.
A universal upper bound covers ALL unfinished branches on interruption.
"""
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
    ScenarioBundle, UpperBound, canonical_json, from_data, to_data)


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
    # Parent sets environment before spawn so even __main__ imports are bounded.
    from protection.evaluation import Evaluator, connected_pairs
    from protection.attacks import surviving_ids
    from protection.errors import DeadlineExceeded
    evaluator = Evaluator(scenario)
    _send(conn, {'type':'READY'})
    deadline = json.loads(conn.recv_bytes())['deadline']
    best = None
    count = bounds = 0

    def check():
        if time.monotonic() >= deadline:
            raise DeadlineExceeded('exact deadline')

    def progress(kind='PROGRESS', error=None):
        _send(conn, {'type':kind, 'best':to_data(best), 'count':count,
                     'bounds':bounds, 'calls':evaluator.evaluation_calls,
                     'fallback_solves':evaluator.fallback_solves,
                     'cache_hits':evaluator.cache_hits, 'error':error})

    def score(ids):
        nonlocal best, count
        check()
        value = evaluator.evaluate(ids, budget, deadline=deadline)
        check()
        count += 1
        if best is None or value.defender_key < best.defender_key:
            best = value
        progress()

    try:
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
                virtual = selected + tuple(range(index, len(edges)))
                c = len(scenario.nodes) * (len(scenario.nodes)-1) // 2
                for attack in evaluator.prepared.candidates:
                    check()
                    c = min(c, connected_pairs(scenario, surviving_ids(scenario, attack, virtual)))
                bounds += 1
                if (c, 1000000) < best.score:
                    continue
            # Push exclude first, then include so traversal is include-first.
            stack.append((index+1, selected, cost))
            if cost + edges[index].cost <= budget:
                stack.append((index+1, selected+(index,), cost+edges[index].cost))
        check()
        progress('DONE')
        conn.recv_bytes()  # Preserve final RSS observation until ACK.
    except DeadlineExceeded:
        progress('TIMEOUT')
        conn.recv_bytes()  # Stay observable until supervisor terminates/acknowledges.
    except Exception as exc:
        progress('ERROR', f'{type(exc).__name__}: {exc}')
        conn.recv_bytes()
    finally:
        conn.close()


def execution_limit(scenario, budget_percent, method, limit_seconds, run_kind, manifest):
    """Resolve fixed research limits without running any experiment."""
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
    """Run a bounded exact search. Main execution must be authorized by caller.

    Preparation is separately measured. No result received at/after deadline
    becomes an incumbent. Failure/timeout never carries optimality_proven.
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
        # Bounded startup is an environment guard, not the search allowance.
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
