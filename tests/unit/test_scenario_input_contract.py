"""입력 텍스트에는 문제 풀이에 필요한 값만 담는다."""
from protection.attacks import prepare_attacks
from protection.evaluation import Evaluator
from protection.models import ScenarioBundle
from protection.program import protected_ids, scenario_input


def test_input_contains_only_problem_data(path_scenario):
    bundle = ScenarioBundle(path_scenario, 40, 4)
    rows = iter(scenario_input(bundle).decode('ascii').splitlines())
    n, m, d, a = map(int, next(rows).split())
    assert (n, m, d) == (len(path_scenario.nodes), len(path_scenario.edges), len(path_scenario.demands))
    assert next(rows) == str(bundle.budget)
    for node in path_scenario.nodes:
        assert tuple(map(float, next(rows).split())) == (node.x, node.y)
    for edge in path_scenario.edges:
        assert tuple(map(int, next(rows).split())) == (edge.u, edge.v, edge.capacity_mbps, edge.cost)
    for demand in path_scenario.demands:
        assert tuple(map(int, next(rows).split())) == (demand.source, demand.target, demand.amount_mbps)
    attacks = prepare_attacks(path_scenario).candidates
    assert a == len(attacks)
    for attack in attacks:
        values = next(rows).split()
        assert tuple(map(float, values[:2])) == (attack.x, attack.y)
        assert int(values[2]) == len(attack.damaged_edge_ids)
        assert tuple(map(int, values[3:])) == attack.damaged_edge_ids
    assert list(rows) == []


def test_same_protection_uses_existing_official_score(path_scenario):
    bundle = ScenarioBundle(path_scenario, 40, 4)
    selected = protected_ids(b'1 0', bundle)
    result = Evaluator(path_scenario).evaluate(list(selected), bundle.budget)
    assert result == Evaluator(bundle.scenario).evaluate([0], 4)
