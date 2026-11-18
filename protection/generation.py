"""D-001 generation-v1: one RNG, explicit calls and ordered edge/demand IDs."""
from __future__ import annotations
import numpy as np
from protection.models import (Node, Edge, Demand, Scenario, GenerationSettings,
                               integer, require)


def connection_probabilities(coordinates, degrees, new_id, candidates):
    distances = np.linalg.norm(coordinates[np.asarray(candidates)] - coordinates[new_id], axis=1)
    weights = np.asarray([degrees[i] for i in candidates], dtype=np.float64) / np.maximum(distances, 1e-9)**3
    total = weights.sum()
    require(np.isfinite(weights).all() and np.isfinite(total) and total > 0,
            'nonfinite or unnormalizable attachment weights')
    probabilities = weights / total
    require(np.isfinite(probabilities).all(), 'invalid attachment probabilities')
    return probabilities


def generate_scenario(n: int, seed: int) -> Scenario:
    integer(n, 'n', 3)
    integer(seed, 'seed')
    rng = np.random.default_rng(seed)
    coordinates = rng.random((n, 2))
    edges = {(0, 1), (0, 2), (1, 2)}
    degrees = [2, 2, 2] + [0] * (n - 3)
    for new_id in range(3, n):
        candidates = list(range(new_id))
        for _ in range(2):
            probabilities = connection_probabilities(coordinates, degrees, new_id, candidates)
            selected = int(rng.choice(candidates, p=probabilities))
            edges.add((selected, new_id))
            degrees[selected] += 1
            degrees[new_id] += 1
            candidates.remove(selected)
    ordered = sorted(edges)
    capacities = rng.integers(10, 31, size=len(ordered))
    costs = rng.integers(1, 11, size=len(ordered))
    pairs = [(source, target) for source in range(n) for target in range(n) if source != target]
    selection = rng.choice(n * (n - 1), size=n, replace=False)
    amounts = rng.integers(5, 21, size=n)
    return Scenario(
        nodes=tuple(Node(i, float(x), float(y)) for i, (x, y) in enumerate(coordinates)),
        edges=tuple(Edge(i, u, v, int(capacities[i]), int(costs[i])) for i, (u, v) in enumerate(ordered)),
        demands=tuple(Demand(i, *pairs[int(selected)], int(amounts[i])) for i, selected in enumerate(selection)),
        seed=seed, generation=GenerationSettings(),
        environment=(('numpy', np.__version__), ('bit_generator', type(rng.bit_generator).__name__),
                     ('generation_version', 'generation-v1')))
