from dataclasses import replace
import pytest
from protection.errors import InvalidScenarioError
from protection.models import Evaluation, UpperBound, ExperimentCondition, RunRecord, to_data, from_data


def evaluation():
    return Evaluation((), 0, 1, 1/3, 10., 1/3, 333333, (0., 0.))


def condition():
    return ExperimentCondition('a'*64, 20, 2, 'member_1', 300., 4000000000)


@pytest.mark.parametrize('units', [-1, 1000001, True])
def test_units_bounds(units):
    with pytest.raises(InvalidScenarioError):
        replace(evaluation(), delivery_units=units)
    with pytest.raises(InvalidScenarioError):
        UpperBound(3, units, 'universal', True)


def test_state_machine_and_nullable_fields():
    r = RunRecord('test', condition(), case_id='b'*64)
    assert r.status == 'pending' and r.search_seconds is None
    with pytest.raises(InvalidScenarioError):
        r.transition('completed')
    running = r.transition('running', launch_status='started')
    failed = running.transition('timeout', recovered_protected_ids=(), recovered_evaluation=evaluation())
    assert failed.submitted_evaluation is None and failed.recovered_evaluation is not None
    assert failed.best_evaluation is None and not failed.optimality_proven
    assert from_data(RunRecord, to_data(failed)) == failed
    with pytest.raises(InvalidScenarioError):
        failed.transition('completed')
    with pytest.raises(InvalidScenarioError):
        replace(failed, submitted_protected_ids=(), submitted_evaluation=evaluation())
    with pytest.raises(InvalidScenarioError):
        replace(failed, optimality_proven=True)


def test_exact_and_member_fields_do_not_mix():
    with pytest.raises(InvalidScenarioError):
        RunRecord('bad', condition(), best_protected_ids=(), best_evaluation=evaluation())
    exact = replace(condition(), method='exhaustive', algorithm_memory_limit_bytes=None)
    r = RunRecord('exact', exact).transition('running').transition('completed', best_protected_ids=(), best_evaluation=evaluation(), optimality_proven=True)
    assert from_data(RunRecord, to_data(r)) == r
    with pytest.raises(InvalidScenarioError):
        replace(exact, algorithm_memory_limit_bytes=4000000000)


def test_schema_unknown_keys_and_bool():
    d = to_data(RunRecord('test', condition()))
    d['unknown'] = 1
    with pytest.raises(InvalidScenarioError):
        from_data(RunRecord, d)
    with pytest.raises(InvalidScenarioError):
        replace(condition(), budget_percent=True)
