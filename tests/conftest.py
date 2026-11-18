"""Only hand-derived fixtures and test-only submissions; no member strategies."""
from dataclasses import dataclass
import pytest
from protection.runner import initialize_single_thread

initialize_single_thread()


@dataclass(frozen=True)
class HandExample:
    # Path 0--1--2, capacities 10 per direction; total cost 10.
    coordinates: tuple = ((0.1, 0.1), (0.5, 0.1), (0.9, 0.1))
    edges: tuple = ((0, 1, 10, 4), (1, 2, 10, 6))
    demands: tuple = ((0, 2, 10), (0, 1, 10), (2, 0, 10))
    # 0->1 shared 10 plus independent reverse 10, total demand 30.
    expected_delivered: int = 20
    expected_units: int = 666667
    expected_connected_pairs: int = 3


@pytest.fixture
def hand_example():
    return HandExample()


@pytest.fixture
def submission_file(tmp_path):
    path = tmp_path / 'test_only_submission.py'
    path.write_text('class TestOnlySubmission:\n    def solve(self, scenario, budget, context):\n        return []\n')
    return path


@pytest.fixture
def path_scenario(hand_example):
    from protection.models import Node, Edge, Demand, Scenario
    h = hand_example
    return Scenario(nodes=tuple(Node(i, *xy) for i, xy in enumerate(h.coordinates)),
                    edges=tuple(Edge(i, *e) for i, e in enumerate(h.edges)),
                    demands=tuple(Demand(i, *d) for i, d in enumerate(h.demands)), seed=0)
