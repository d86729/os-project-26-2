"""Direct context contract with a fake evaluator: no scientific imports/LP."""
from types import SimpleNamespace
import time
import pytest
from protection.context import ExecutionContext
from protection.errors import DeadlineExceeded, InvalidProtectionError, EvaluationError


class FakeEvaluator:
    def __init__(self):
        self.calls = []
    def evaluate(self, ids, budget, *, deadline):
        self.calls.append((ids, budget, deadline))
        return SimpleNamespace(connected_pairs=1, delivery_units=2, cost=0, protected_ids=tuple(ids))


def make_context(scenario, evaluator, t0=None):
    return ExecutionContext(scenario, 4, 1., None, 0, 1,
                            time.monotonic_ns() if t0 is None else t0, evaluator)


def test_direct_call_identity_and_deadline(path_scenario):
    evaluator = FakeEvaluator()
    context = make_context(path_scenario, evaluator)
    result = context.evaluate([])
    assert context._best[0] is result
    assert evaluator.calls == [([], 4, context._t0_ns/1e9+1.)]
    assert not hasattr(context, '_channel')


def test_expired_and_invalid_never_evaluate(path_scenario):
    evaluator = FakeEvaluator()
    context = make_context(path_scenario, evaluator, time.monotonic_ns()-2_000_000_000)
    with pytest.raises(DeadlineExceeded):
        context.evaluate([])
    with pytest.raises(InvalidProtectionError):
        context.evaluate([True])
    assert evaluator.calls == []


def test_evaluator_exception_propagates(path_scenario):
    class Broken:
        def evaluate(self, *a, **k):
            raise EvaluationError('local failure')
    with pytest.raises(EvaluationError, match='local failure'):
        make_context(path_scenario, Broken()).evaluate([])
