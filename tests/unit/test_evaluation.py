import importlib
from dataclasses import replace
from types import SimpleNamespace
import pytest
from protection.models import Evaluation
from protection.errors import InvalidProtectionError, EvaluationError


def module(): return importlib.import_module('protection.evaluation')


@pytest.mark.parametrize('bad',[(0,),[True],[0,0],[1,0],[-1],[2],[0.0],None])
def test_invalid_protection(path_scenario,bad):
    with pytest.raises(InvalidProtectionError): module().validate_protection(path_scenario,10,bad)


def test_budget_empty_and_cost(path_scenario):
    e=module()
    assert e.budget_for(path_scenario,20)==2 and e.budget_for(path_scenario,40)==4
    assert e.validate_protection(path_scenario,2,[])==0
    assert e.validate_protection(path_scenario,4,[0])==4
    with pytest.raises(InvalidProtectionError): e.validate_protection(path_scenario,2,[0])
    with pytest.raises(InvalidProtectionError): e.validate_protection(path_scenario,True,[])
    assert e.connected_pairs(path_scenario,(0,1))==3
    assert e.connected_pairs(path_scenario,(0,))==1
    assert e.connected_pairs(path_scenario,())==0


def test_first_metric_before_lp_and_coordinate_tie(path_scenario,monkeypatch):
    a=importlib.import_module('protection.attacks'); e=module()
    prepared=a.prepare_attacks(path_scenario)
    candidates=(a.AttackCandidate(0,0.,0.,()),a.AttackCandidate(1,.1,.1,(0,1)),a.AttackCandidate(2,.2,.2,(0,1)))
    prepared=replace(prepared,candidates=candidates)
    calls=[]
    def fake(s,ids,**kwargs):
        calls.append(ids); assert ids==()
        return SimpleNamespace(delivered_mbps=0.,delivery_ratio=0.,delivery_units=0,diagnostics=None)
    monkeypatch.setattr(e,'maximum_delivery',fake)
    result=e.Evaluator(path_scenario,prepared,use_cache=False).evaluate([],2)
    assert result.score==(0,0) and result.worst_attack==(.1,.1)
    assert len(calls)==2


def test_delivery_cost_id_ties():
    ev=Evaluation((1,),6,1,1/3,10.,1/3,333333,(.1,.1))
    assert replace(ev,connected_pairs=2,delivery_units=0).defender_key < ev.defender_key
    assert replace(ev,delivery_units=333334).defender_key < ev.defender_key
    assert replace(ev,cost=4).defender_key < ev.defender_key
    assert replace(ev,protected_ids=(0,)).defender_key < ev.defender_key


def test_cache_equal_and_new_condition_empty(path_scenario):
    e=module(); on=e.Evaluator(path_scenario); off=e.Evaluator(path_scenario,use_cache=False)
    first=on.evaluate([],2); second=on.evaluate([],2)
    assert first==second==off.evaluate([],2)
    assert on.cache_hits>0
    assert e.Evaluator(path_scenario).cache_size==0
    assert on.evaluate([0],4)==off.evaluate([0],4)


def test_failure_propagates_and_not_cached(path_scenario,monkeypatch):
    e=module(); evaluator=e.Evaluator(path_scenario)
    def fail(*a,**k): raise EvaluationError('injected')
    monkeypatch.setattr(e,'maximum_delivery',fail)
    with pytest.raises(EvaluationError): evaluator.evaluate([],2)
    assert evaluator.cache_size==0


def prepared_subset(scenario, damages):
    from protection.attacks import prepare_attacks, AttackCandidate
    return replace(prepare_attacks(scenario), candidates=tuple(
        AttackCandidate(i, .1, i / 10, ids) for i, ids in enumerate(damages)))


def test_real_delivery_breaks_connectivity_tie(path_scenario):
    # Both residuals have one pair. Edge 0 serves 0->1 (10); edge 1
    # serves none of the three demands, so the later coordinate must win.
    prepared = prepared_subset(path_scenario, [(1,), (0,)])
    result = module().Evaluator(path_scenario, prepared).evaluate([], 2)
    assert result.score == (1, 0)
    assert result.worst_attack == (.1, .1)


def test_rounded_delivery_tie_uses_coordinates_not_raw_value(path_scenario, monkeypatch):
    e = module()
    prepared = prepared_subset(path_scenario, [(1,), (0,)])
    def flow(s, ids, **kwargs):
        raw = 10.000001 if ids == (0,) else 10.0
        return SimpleNamespace(delivered_mbps=raw, delivery_ratio=raw / 30,
                               delivery_units=333333, diagnostics=None)
    monkeypatch.setattr(e, 'maximum_delivery', flow)
    result = e.Evaluator(path_scenario, prepared).evaluate([], 2)
    assert result.worst_attack == (.1, 0.)
    assert result.delivered_mbps == 10.000001


@pytest.mark.parametrize('field,value', [('scenario_id', 'wrong'),
    ('policy_version', 'evaluation-v1'), ('attack_settings', None)])
def test_prepared_metadata_mismatch(path_scenario, field, value):
    prepared = prepared_subset(path_scenario, [()])
    with pytest.raises(EvaluationError, match='do not match'):
        module().Evaluator(path_scenario, replace(prepared, **{field: value}))


def test_prepared_unknown_edge(path_scenario):
    with pytest.raises(EvaluationError, match='unknown edge'):
        module().Evaluator(path_scenario, prepared_subset(path_scenario, [(2,)]))


def test_cache_is_residual_keyed_not_protection_or_coordinate(path_scenario, monkeypatch):
    e = module()
    prepared = prepared_subset(path_scenario, [(1,), (1,)])
    actual = e.maximum_delivery
    calls = []
    def flow(s, ids, **kwargs):
        calls.append(ids)
        return actual(s, ids, **kwargs)
    monkeypatch.setattr(e, 'maximum_delivery', flow)
    evaluator = e.Evaluator(path_scenario, prepared)
    first = evaluator.evaluate([], 4)
    second = evaluator.evaluate([0], 4)
    assert calls == [(0,)]
    assert evaluator.cache_hits == 3 and evaluator.cache_size == 1
    assert first.score == second.score == (1, 333333)
    assert first.worst_attack == second.worst_attack == (.1, 0.)
    assert first.protected_ids == () and second.protected_ids == (0,)
    assert first.cost == 0 and second.cost == 4
    assert set(evaluator._cache) == {(path_scenario.scenario_id, 1, 'evaluation-v2')}
    fresh = e.Evaluator(path_scenario, prepared)
    assert fresh.cache_size == fresh.cache_hits == 0
    fresh.evaluate([], 4)
    assert calls == [(0,), (0,)]


@pytest.mark.parametrize('warm', [False, True])
def test_deadline_at_entry_even_with_warm_cache(path_scenario, monkeypatch, warm):
    from protection.errors import DeadlineExceeded
    e = module()
    evaluator = e.Evaluator(path_scenario, prepared_subset(path_scenario, [(1,)]))
    if warm:
        evaluator.evaluate([], 2)
    before = evaluator.evaluation_calls
    monkeypatch.setattr(e.time, 'monotonic', lambda: 10.)
    with pytest.raises(DeadlineExceeded):
        evaluator.evaluate([], 2, deadline=10.)
    assert evaluator.evaluation_calls == before


def test_deadline_during_connectivity_never_calls_flow(path_scenario, monkeypatch):
    from protection.errors import DeadlineExceeded
    e = module()
    evaluator = e.Evaluator(path_scenario, prepared_subset(path_scenario, [(1,), (0,)]))
    clock = [0.]
    original = e.connected_pairs
    def connected(s, ids):
        clock[0] = 10.
        return original(s, ids)
    monkeypatch.setattr(e.time, 'monotonic', lambda: clock[0])
    monkeypatch.setattr(e, 'connected_pairs', connected)
    monkeypatch.setattr(e, 'maximum_delivery', lambda *a, **k: pytest.fail('late LP'))
    with pytest.raises(DeadlineExceeded):
        evaluator.evaluate([], 2, deadline=10.)
    assert evaluator.cache_size == 0


def test_late_flow_result_not_cached(path_scenario, monkeypatch):
    from protection.errors import DeadlineExceeded
    e = module()
    evaluator = e.Evaluator(path_scenario, prepared_subset(path_scenario, [(1,)]))
    clock = [0.]
    def flow(s, ids, *, deadline):
        assert deadline == 10.
        clock[0] = 10.
        return SimpleNamespace(delivered_mbps=10., delivery_ratio=1/3,
                               delivery_units=333333, diagnostics=None)
    monkeypatch.setattr(e.time, 'monotonic', lambda: clock[0])
    monkeypatch.setattr(e, 'maximum_delivery', flow)
    with pytest.raises(DeadlineExceeded):
        evaluator.evaluate([], 2, deadline=10.)
    assert evaluator.cache_size == 0
    assert evaluator.last_diagnostics == ()


def test_partial_failure_never_returns_score_or_caches_failed_residual(path_scenario, monkeypatch):
    e = module()
    evaluator = e.Evaluator(path_scenario, prepared_subset(path_scenario, [(1,), (0,)]))
    actual = e.maximum_delivery
    def flow(s, ids, **kwargs):
        if ids == (1,):
            raise EvaluationError('second residual failed')
        return actual(s, ids, **kwargs)
    monkeypatch.setattr(e, 'maximum_delivery', flow)
    with pytest.raises(EvaluationError, match='second residual'):
        evaluator.evaluate([], 2)
    assert evaluator.cache_size == 1  # Only the independently completed residual.
    assert evaluator.last_diagnostics == ()
    monkeypatch.setattr(e, 'maximum_delivery', actual)
    assert evaluator.evaluate([], 2) == e.Evaluator(
        path_scenario, evaluator.prepared, use_cache=False).evaluate([], 2)
