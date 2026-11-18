import importlib
import multiprocessing
import time


def test_tiny_deadline_returns_no_invented_incumbent(path_scenario):
    exact = importlib.import_module('protection.exact')
    before = {p.pid for p in multiprocessing.active_children()}
    started = time.monotonic()
    record = exact.search(path_scenario, 40, limit_seconds=0.000001)
    assert record.status == 'timeout'
    assert not record.optimality_proven
    assert record.best_evaluation is None
    assert record.upper_bound.connected_pairs == 3
    assert record.upper_bound.delivery_units == 1000000
    assert time.monotonic() - started < 10
    assert {p.pid for p in multiprocessing.active_children()} == before


def test_timeout_preserves_received_incumbent():
    from protection.generation import generate_scenario
    exact = importlib.import_module('protection.exact')
    record = exact.search(generate_scenario(12,0),40,method='branch_bound',limit_seconds=1.)
    assert record.status == 'timeout'
    assert not record.optimality_proven
    assert record.best_evaluation is not None
    assert record.evaluated_combinations > 0
    assert record.upper_bound.connected_pairs == 66
    assert record.upper_bound.delivery_units == 1000000
    assert any(e.startswith('upper_bound_calls=') for e in record.events)
    assert record.search_seconds < 3
    assert record.shutdown_seconds < 2
