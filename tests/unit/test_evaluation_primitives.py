"""T016-only boundaries; no flow solver or Evaluator dependency."""
from dataclasses import replace

import pytest

from protection.errors import EvaluationError, InvalidProtectionError, InvalidScenarioError
from protection.evaluation import budget_for, connected_pairs, validate_protection
from protection.models import Demand, Edge, Node, Scenario


@pytest.mark.parametrize('percent', [True, False, 20.0, '20', None, -20, 0, 21, 100])
def test_invalid_budget_percent(path_scenario, percent):
    with pytest.raises(InvalidScenarioError):
        budget_for(path_scenario, percent)


@pytest.mark.parametrize('budget', [True, False, -1, 4.0, '4', None])
def test_invalid_budget(path_scenario, budget):
    with pytest.raises(InvalidProtectionError):
        validate_protection(path_scenario, budget, [])


def test_floor_and_no_input_mutation(path_scenario):
    scenario = replace(path_scenario, edges=(replace(path_scenario.edges[0], cost=3),
                                            path_scenario.edges[1]), scenario_id='')
    assert budget_for(scenario, 20) == 1
    assert budget_for(scenario, 40) == 3
    ids = [0, 1]
    assert validate_protection(scenario, 9, ids) == 9
    assert ids == [0, 1]
    assert validate_protection(scenario, 0, []) == 0
    assert type(connected_pairs(scenario, ids)) is int
    assert ids == [0, 1]


@pytest.mark.parametrize('ids', [(True,), (False,), (-1,), (2,), (0.0,), (0, 0), (1, 0), None])
def test_invalid_surviving_ids(path_scenario, ids):
    with pytest.raises(EvaluationError):
        connected_pairs(path_scenario, ids)


def test_components_cycle_and_isolated_node():
    # Triangle 0,1,2; pair 3,4; isolated 5 after edges 3 and 5 are removed.
    endpoints = ((0, 1), (0, 2), (1, 2), (2, 3), (3, 4), (4, 5))
    scenario = Scenario(
        nodes=tuple(Node(i, i / 10, 0.1) for i in range(6)),
        edges=tuple(Edge(i, u, v, 10, 1) for i, (u, v) in enumerate(endpoints)),
        demands=tuple(Demand(i, i, (i + 1) % 6, 5) for i in range(6)), seed=0)
    assert connected_pairs(scenario, (0, 1, 2, 4)) == 4  # 3 + 1 + 0
    assert connected_pairs(scenario, tuple(range(6))) == 15
    assert connected_pairs(scenario, ()) == 0
