from dataclasses import FrozenInstanceError, replace
import pytest
from protection.models import Node, Edge, Demand, Scenario, AttackSettings, GenerationSettings
from protection.errors import InvalidScenarioError


@pytest.mark.parametrize('factory,args', [
    (Node, (True, .1, .1)), (Node, (0, 1., .1)), (Node, (0, -.1, .1)),
    (Node, (0, float('nan'), .1)), (Node, (0, float('inf'), .1)),
    (Edge, (0, 1, 0, 10, 1)), (Edge, (0, 0, 0, 10, 1)),
    (Edge, (False, 0, 1, 10, 1)), (Edge, (0, 0, 1, 9, 1)),
    (Edge, (0, 0, 1, 31, 1)), (Edge, (0, 0, 1, 10, 11)),
    (Edge, (0, 0, 1, 10, 0)), (Demand, (0, 0, 0, 5)),
    (Demand, (0, 0, 1, 4)), (Demand, (0, 0, 1, 21)),
    (Demand, (0, True, 1, 10))])
def test_bad_values(factory, args):
    with pytest.raises(InvalidScenarioError):
        factory(*args)


def test_valid_input_is_deeply_immutable(path_scenario):
    s = path_scenario
    assert len(s.nodes) == 3 and len(s.demands) == 3
    with pytest.raises(FrozenInstanceError):
        s.nodes[0].x = .2
    with pytest.raises(FrozenInstanceError):
        s.edges = ()
    with pytest.raises(InvalidScenarioError):
        replace(s, nodes=list(s.nodes))
    assert s.attack_settings == AttackSettings()
    assert s.generation == GenerationSettings()


@pytest.mark.parametrize('change', [
    lambda s: dict(nodes=s.nodes[:2]),
    lambda s: dict(demands=s.demands[:2]),
    lambda s: dict(edges=s.edges[:1]),
    lambda s: dict(edges=(s.edges[1], s.edges[0])),
    lambda s: dict(nodes=(s.nodes[0],s.nodes[0],s.nodes[2])),
    lambda s: dict(demands=(s.demands[0], replace(s.demands[0],id=1),s.demands[2])),
    lambda s: dict(edges=(s.edges[0],replace(s.edges[0], id=1))),
    lambda s: dict(demands=(replace(s.demands[0],target=3),*s.demands[1:])),
    lambda s: dict(seed=True), lambda s: dict(schema_version=True)])
def test_scenario_invariants(path_scenario, change):
    with pytest.raises(InvalidScenarioError):
        replace(path_scenario, **change(path_scenario))
