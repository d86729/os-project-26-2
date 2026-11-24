import copy
import json
from pathlib import Path
import pytest
from protection.models import ExperimentManifest
from protection.errors import InvalidScenarioError


def preparation():
    return json.loads((Path(__file__).resolve().parents[2] / 'configs/smoke.json').read_text())


def grading():
    return dict(schema_version=1,kind='grading',run_kind='smoke',owners={'common':'김대건'},
                bank=[{'path':'case.json','case_id':'a'*64}],
                submission=dict(method_id='member_1',file='member.py',class_name='Member1Protector',
                                owner='팀원 1',strategy_name='test',strategy_version='1'),
                limits=dict(algorithm_seconds=300,algorithm_memory_bytes=4000000000),
                resource_policy=dict(sample_interval_ms=10), output_dir='results')


def test_paths_are_relative_to_manifest_parent(tmp_path):
    m = ExperimentManifest.parse(preparation(), tmp_path / 'config.json')
    assert Path(m.to_dict()['output_dir']) == (tmp_path/'../scenarios/smoke').resolve()
    g = ExperimentManifest.parse(grading(), tmp_path / 'config.json').to_dict()
    assert g['bank'][0]['path'] == str(tmp_path / 'case.json')
    assert g['submission']['file'] == str(tmp_path / 'member.py')


@pytest.mark.parametrize('mutation', [
    lambda d: d.update(unknown=1), lambda d: d.update(schema_version=True),
    lambda d: d.update(ready=False), lambda d: d.update(sizes=[]),
    lambda d: d.update(budget_percents=[20]),
    lambda d: d.update(seeds_by_size={'6':[]}),
    lambda d: d.update(seeds_by_size={'6':[0,0]}),
    lambda d: d.update(seeds_by_size={'6':[True]}),
    lambda d: d.update(size_groups={'8':'small'}),
    lambda d: d['limits'].update(extra=1)])
def test_invalid_preparation(mutation,tmp_path):
    d = preparation(); mutation(d)
    with pytest.raises(InvalidScenarioError):
        ExperimentManifest.parse(d,tmp_path/'manifest.json')


@pytest.mark.parametrize('mutation', [
    lambda d: d.update(bank=[]), lambda d: d['bank'].append(copy.deepcopy(d['bank'][0])),
    lambda d: d['bank'][0].update(extra=True),
    lambda d: d['submission'].update(uses_randomness=True),
    lambda d: d['submission'].update(algorithm_seeds=[1]),
    lambda d: d['limits'].update(algorithm_memory_bytes=True)])
def test_invalid_grading(mutation,tmp_path):
    d=grading(); mutation(d)
    with pytest.raises(InvalidScenarioError):
        ExperimentManifest.parse(d,tmp_path/'manifest.json')


def test_grading_needs_no_strategy_seed(tmp_path):
    manifest = ExperimentManifest.parse(grading(), tmp_path/'config.json')
    submission = manifest.to_dict()['submission']
    assert 'algorithm_seeds' not in submission
    assert 'uses_randomness' not in submission
