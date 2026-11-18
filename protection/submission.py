"""One fresh submission worker: direct evaluations, control/results only IPC."""
import importlib.util
import os
import sys
import time

from protection.context import ExecutionContext, JsonChannel, ProtocolError, validate_ids
from protection.models import to_data


def algorithm_worker(sock, run_id, scenario, budget, file, class_name, seed, index,
                     count, delay=0, allocation=0, failure=None):
    from protection.runner import initialize_single_thread, _error_payload
    initialize_single_thread()
    channel = JsonChannel(sock, run_id)
    phase = 'worker_preparation_error'
    context = None
    evaluator = None

    def diagnostics():
        return dict(evaluation_calls=evaluator.evaluation_calls if evaluator else 0,
                    cache_hits=evaluator.cache_hits if evaluator else 0,
                    fallback_solves=evaluator.fallback_solves if evaluator else 0,
                    recovered=to_data(context._best[0]) if context and context._best[0] else None)

    try:
        from protection.evaluation import Evaluator
        evaluator = Evaluator(scenario)
        # Private smoke-only hooks remain local; no evaluation messages exist.
        allocation_hold = bytearray(allocation) if allocation else None
        if delay or failure:
            original = evaluator.evaluate
            def evaluate(ids, budget, *, deadline=None):
                if delay:
                    time.sleep(delay)
                if failure == 'exit':
                    os._exit(12)
                if failure == 'error':
                    from protection.errors import EvaluationError
                    raise EvaluationError('test-only injected LP failure')
                return original(ids, budget, deadline=deadline)
            evaluator.evaluate = evaluate
        channel.send('READY', {'cache_size': evaluator.cache_size})
        start = channel.recv()
        if start['type'] != 'START':
            raise ProtocolError('START required')
        data = start['payload']
        context = ExecutionContext(scenario, budget, data['limit_seconds'], seed,
                                   index, count, data['t0_ns'], evaluator)
        phase = 'submission_load_error'
        spec = importlib.util.spec_from_file_location('_submission_' + run_id, file)
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        instance = getattr(module, class_name)()
        phase = 'execution_error'
        answer = instance.solve(scenario, budget, context)
        validate_ids(scenario, budget, answer)
        channel.send('FINAL', dict(ids=answer, **diagnostics()))
        if channel.recv()['type'] != 'SCORE':
            raise ProtocolError('SCORE required')
        # Search has ended. Score the actual return in this same worker/cache.
        phase = 'final_scoring_failed'
        score = evaluator.evaluate(answer, budget)
        channel.send('SCORED', dict(evaluation=to_data(score), **diagnostics()))
        if channel.recv()['type'] != 'ACK':
            raise ProtocolError('ACK required')
    except BaseException as exc:
        try:
            channel.send('ERROR', dict(**_error_payload(exc, phase), **diagnostics()))
            channel.recv()  # parent can still observe final whole-worker RSS
        except BaseException:
            pass
    finally:
        channel.close()
