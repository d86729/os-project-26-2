"""US1 only: intermediate inputs and real evaluation, never optimal bundles."""
import json
import os
from pathlib import Path

import pytest
from protection.attacks import prepare_attacks
from protection.errors import InvalidProtectionError, InvalidScenarioError
from protection.evaluation import Evaluator, budget_for
from protection.generation import generate_scenario
from protection.models import (save_scenario, load_scenario, load_bundle,
                               to_data, atomic_json)
from protection.runner import collect_environment


def test_common_pipeline(tmp_path, path_scenario):
    generated = generate_scenario(6, 0)
    regenerated = generate_scenario(6, 0)
    assert generated == regenerated
    assert generated.scenario_id == regenerated.scenario_id
    source = tmp_path / 'n6-seed0.json'
    save_scenario(generated, source)
    loaded = load_scenario(source)
    assert loaded == generated
    payload = json.loads(source.read_text())
    assert payload['artifact_kind'] == 'scenario_input'
    assert 'optimal_reference' not in payload
    with pytest.raises(InvalidScenarioError):
        load_bundle(source, require_reference=True)
    prepared = prepare_attacks(loaded)
    assert prepared.candidates == prepare_attacks(regenerated).candidates
    rows = []
    for percent in (20, 40):
        budget = budget_for(loaded, percent)
        assert budget == sum(e.cost for e in loaded.edges) * percent // 100
        cached = Evaluator(loaded, prepared)
        uncached = Evaluator(loaded, prepared, use_cache=False)
        assert cached.cache_size == 0
        # Deterministic test input, not an implemented protection strategy.
        affordable = next(e.id for e in loaded.edges if e.cost <= budget)
        evaluations = []
        for ids in ([], [affordable]):
            result = cached.evaluate(ids, budget)
            assert result == uncached.evaluate(ids, budget)
            assert result == cached.evaluate(ids, budget)
            evaluations.append(to_data(result))
        invalid = ([True], [0, 0], [1, 0], [-1], [len(loaded.edges)],
                   list(range(len(loaded.edges))))
        for ids in invalid:
            with pytest.raises(InvalidProtectionError):
                cached.evaluate(ids, budget)
        assert cached.cache_hits > 0
        assert uncached.cache_size == 0
        rows.append(dict(budget_percent=percent, budget=budget,
                         evaluations=evaluations, invalid_rejections=len(invalid),
                         cache_hits=cached.cache_hits, cache_size=cached.cache_size))

    # Independent hand derivation (no solver-derived expected numbers):
    # Path (.1,.1)--(.5,.1)--(.9,.1), edge costs 4+6, capacities 10.
    # Demands 0->2, 0->1, 2->0 each 10. Empty protection: a center
    # within .15 of node 1 removes both edges, leaving 0 connected pairs.
    # Earliest candidate doing so is (.4,0): endpoint distance sqrt(.02)
    # < .15. All earlier-x candidates lie farther from the right segment.
    # Protecting edge 0 leaves one pair at worst; only 0->1 can be served,
    # exactly 10/30 -> 333333 units. The same (.4,0) is the first center
    # that can remove edge 1. Protecting both leaves all 3 pairs; forward
    # traffic shares the 10 bottleneck, reverse adds an independent 10:
    # total 20/30 -> 666667 units. Every attack ties, so (0,0) wins.
    # The all-protected case is a test-only budget 10, not a 20/40% case.
    hand = Evaluator(path_scenario)
    expected = [([], 2, 0, 0, 0., 0, (.4, 0.)),
                ([0], 4, 4, 1, 10., 333333, (.4, 0.)),
                ([0, 1], 10, 10, 3, 20., 666667, (0., 0.))]
    oracle_rows = []
    for ids, budget, cost, pairs, mbps, units, attack in expected:
        result = hand.evaluate(ids, budget)
        assert result.protected_ids == tuple(ids)
        assert result.cost == cost
        assert result.score == (pairs, units)
        assert result.connected_ratio == pytest.approx(pairs / 3)
        assert result.delivered_mbps == pytest.approx(mbps)
        assert result.delivery_ratio == pytest.approx(mbps / 30)
        assert result.worst_attack == attack
        oracle_rows.append(dict(expected=dict(cost=cost, connected_pairs=pairs,
            delivered_mbps=mbps, delivery_units=units, worst_attack=attack),
            actual=to_data(result), budget=budget, matched=True))
    report = dict(run_kind='smoke', scope='T013/T019/T020/T021 common evaluation only',
                  formal_distribution=False, optimal_reference=None,
                  environment=collect_environment(),
                  generated=dict(n=6, seed=0, scenario_id=loaded.scenario_id,
                      reproducible=True, intermediate_roundtrip_equal=True,
                      artifact_kind=payload['artifact_kind'],
                      candidate_count=len(prepared.candidates), conditions=rows),
                  hand_oracle=dict(derivation='Path capacities 10 per direction; demands '
                      '0->2,0->1,2->0 each 10. Empty: 0. Edge0 protected: 10. '
                      'Both protected: forward shared 10 + reverse 10 = 20. '
                      'Earliest damaging center (.4,0), full protection tie (0,0).',
                      scenario=to_data(path_scenario), comparisons=oracle_rows))
    # Explicit opt-in artifact production; ordinary regressions use tmp_path only.
    if output := os.environ.get('COMMON_VALIDATION_REPORT'):
        target = Path(output)
        target.parent.mkdir(parents=True, exist_ok=True)
        intermediate = target.with_name('common-n6-seed0-input.json')
        save_scenario(loaded, intermediate, overwrite=True)
        report['generated']['intermediate_path'] = str(intermediate)
        atomic_json(target, report, overwrite=True)
