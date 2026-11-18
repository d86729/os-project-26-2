"""Independent enumeration oracle; not generated reference performance."""
import importlib
from itertools import combinations
import pytest
from protection.evaluation import Evaluator, budget_for


def oracle(scenario, percent):
    budget = budget_for(scenario, percent)
    evaluator = Evaluator(scenario)
    values = []
    for count in range(len(scenario.edges) + 1):
        for ids in combinations(range(len(scenario.edges)), count):
            if sum(scenario.edges[i].cost for i in ids) <= budget:
                values.append(evaluator.evaluate(list(ids), budget))
    return min(values, key=lambda ev: ev.defender_key), len(values)


@pytest.mark.parametrize('percent', [20, 40])
@pytest.mark.parametrize('method', ['exhaustive', 'branch_bound'])
def test_exact_matches_enumeration(path_scenario, percent, method):
    exact = importlib.import_module('protection.exact')
    expected, count = oracle(path_scenario, percent)
    record = exact.search(path_scenario, percent, method=method, limit_seconds=20)
    assert record.status == 'completed'
    assert record.optimality_proven
    assert record.best_evaluation == expected
    assert record.best_protected_ids == expected.protected_ids
    assert record.best_evaluation.cost <= budget_for(path_scenario, percent)
    if method == 'exhaustive':
        assert record.evaluated_combinations == count
    assert record.upper_bound.connected_pairs == expected.connected_pairs
    assert record.upper_bound.delivery_units == expected.delivery_units
    assert record.exact_peak_rss_bytes > 0


@pytest.mark.parametrize('costs, expected', [((1,1,1),(0,)), ((5,4,6),(1,))])
def test_exact_cost_and_id_ties(costs, expected):
    from protection.models import Node, Edge, Demand, Scenario
    scenario = Scenario(tuple(Node(i,.5,.5) for i in range(3)),
        tuple(Edge(i,u,v,10,costs[i]) for i,(u,v) in enumerate(((0,1),(0,2),(1,2)))),
        tuple(Demand(i,u,v,5) for i,(u,v) in enumerate(((0,1),(1,2),(2,0)))),0)
    exact = importlib.import_module('protection.exact')
    for method in ('exhaustive','branch_bound'):
        result = exact.search(scenario,40,method=method,limit_seconds=20)
        assert result.status == 'completed'
        assert result.best_protected_ids == expected


def test_invalid_exact_options(path_scenario):
    exact = importlib.import_module('protection.exact')
    for kwargs in ({'method':'invented'}, {'limit_seconds':0}, {'limit_seconds':True}):
        with pytest.raises(ValueError):
            exact.search(path_scenario, 20, **kwargs)
