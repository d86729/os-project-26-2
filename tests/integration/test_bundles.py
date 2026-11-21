from dataclasses import replace
import pytest
from protection import models
from protection.errors import InvalidScenarioError
from protection.exact import search


def test_completed_exhaustive_bundle_and_reference_removal(path_scenario, tmp_path):
    record = search(path_scenario, 40, limit_seconds=20)
    bundle = models.bundle_from_record(path_scenario, record)
    path = tmp_path / 'bundle.json'
    models.save_bundle(bundle, path)
    assert models.load_bundle(path, require_reference=True) == bundle
    copy = replace(bundle, optimal_reference=None)
    assert copy.case_id == bundle.case_id
    assert copy.algorithm_input() == bundle.algorithm_input()
    bad = replace(record, case_id='0'*64)
    with pytest.raises(InvalidScenarioError):
        models.bundle_from_record(path_scenario, bad)
    with pytest.raises(InvalidScenarioError):
        models.bundle_from_record(path_scenario, replace(record, optimality_proven=False))
    with pytest.raises(InvalidScenarioError, match='evaluation count'):
        models.bundle_from_record(path_scenario, replace(record, evaluated_combinations=1))
    with pytest.raises(InvalidScenarioError, match='certified'):
        models.bundle_from_record(path_scenario,
                                  replace(record, events=('highs_residual_fallback_solves=1',)))
    bnb = search(path_scenario, 40, method='branch_bound', limit_seconds=20)
    with pytest.raises(InvalidScenarioError):
        models.bundle_from_record(path_scenario, bnb)
    altered = replace(bundle.optimal_reference.evaluation, worst_attack=(0.,0.))
    ref = replace(bundle.optimal_reference, evaluation=altered)
    models.save_bundle(replace(bundle,optimal_reference=ref),path,overwrite=True)
    with pytest.raises(InvalidScenarioError):
        models.load_bundle(path,require_reference=True)
