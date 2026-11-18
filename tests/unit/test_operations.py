"""Operational authorization tests; all main searches are mocked."""
import json
from pathlib import Path
from unittest.mock import Mock
import pytest
from protection.models import ExperimentManifest, save_scenario
from protection.generation import generate_scenario
from protection.cli import main

ROOT = Path(__file__).resolve().parents[2]


def preparation(tmp_path, kind='main'):
    d = json.loads((ROOT/'configs/smoke.json').read_text())
    d.update(run_kind=kind, output_dir=str(tmp_path/'out'), owners={'common':'김대건'})
    return d


@pytest.mark.parametrize('owner', ['팀원 1', 'member_1', 'TBD', '미정', '담당자 미제출', 'unknown', '<name>'])
def test_main_rejects_placeholder_owners(tmp_path, owner):
    d = preparation(tmp_path); d['owners']['common'] = owner
    with pytest.raises(ValueError, match='owner'):
        ExperimentManifest.parse(d, tmp_path/'manifest.json')


def test_main_cli_passes_manifest_without_limit_override(tmp_path, monkeypatch):
    from protection import exact, runner
    monkeypatch.setattr(runner, 'initialize_single_thread', lambda: None)
    from protection.models import ExperimentCondition, RunRecord
    s = generate_scenario(6, 0); source = tmp_path/'input.json'; save_scenario(s, source)
    d = preparation(tmp_path); path = tmp_path/'manifest.json'; path.write_text(json.dumps(d))
    record = RunRecord('mock', ExperimentCondition(s.scenario_id,20,0,'exhaustive',600), status='failed', run_kind='main')
    search = Mock(return_value=record); monkeypatch.setattr(exact, 'search', search)
    argv = ['exact','--input',str(source),'--budget-percent','20','--method','exhaustive',
            '--run-kind','main','--manifest',str(path),'--output',str(tmp_path/'record.json')]
    assert main(argv) == 1
    assert search.call_args.kwargs['limit_seconds'] is None
    assert search.call_args.kwargs['run_kind'] == 'main'
    assert isinstance(search.call_args.kwargs['manifest'], ExperimentManifest)
    assert json.loads((tmp_path/'record.json').read_text())['status'] == 'failed'
    search.reset_mock()
    argv[-1] = str(tmp_path/'other.json')
    assert main(argv + ['--limit-seconds','1']) == 2
    search.assert_not_called()


def test_main_exact_direct_parser_guard(tmp_path):
    from protection.exact import execution_limit
    d = preparation(tmp_path); d['owners']['common'] = 'TBD'
    path = tmp_path/'manifest.json'; path.write_text(json.dumps(d))
    with pytest.raises(ValueError, match='owner'):
        execution_limit(generate_scenario(6,0),20,'exhaustive',None,'main',path)


def test_experiment_stays_unready():
    assert json.loads((ROOT/'configs/experiment.json').read_text())['ready'] is False


def grading(tmp_path):
    return dict(schema_version=1,kind='grading',run_kind='main',owners={'common':'김대건'},
        bank=[{'path':'case.json','case_id':'a'*64}],output_dir=str(tmp_path/'out'),
        submission=dict(method_id='member_1',file='test_only.py',class_name='TestOnly',
            uses_randomness=True,algorithm_seeds=[0,1,2,3,4],owner='Test Person',
            strategy_name='test only',strategy_version='test'),
        limits=dict(algorithm_seconds=300,algorithm_memory_bytes=4000000000),
        resource_policy=dict(sample_interval_ms=10))


@pytest.mark.parametrize('mutation',[
    lambda d: d['bank'].append(dict(d['bank'][0])),
    lambda d: d['submission'].update(algorithm_seeds=[0,1,2,3]),
    lambda d: d['submission'].update(algorithm_seeds=[0,1,2,3,3]),
    lambda d: d['submission'].update(algorithm_seeds=[0,1,2,3,True]),
    lambda d: d['submission'].update(owner='팀원 1'),
])
def test_main_grading_guard(tmp_path,mutation):
    d=grading(tmp_path); mutation(d)
    with pytest.raises(ValueError):
        ExperimentManifest.parse(d,tmp_path/'m.json')


def test_main_bank_requires_original_reference(tmp_path):
    from protection.models import ScenarioBundle,save_bundle
    from protection.cli import load_bank
    s=generate_scenario(6,0); b=ScenarioBundle(s,20,sum(e.cost for e in s.edges)*20//100)
    save_bundle(b,tmp_path/'case.json')
    d=grading(tmp_path); d['bank'][0]['case_id']=b.case_id
    with pytest.raises(ValueError,match='reference'):
        load_bank(ExperimentManifest.parse(d,tmp_path/'m.json'))


@pytest.mark.parametrize('mutation',[
    lambda d: d.update(sizes=[6,6]),
    lambda d: d.update(seeds_by_size={'6':[]}),
    lambda d: d.update(seeds_by_size={'6':[1,1]}),
    lambda d: d.update(budget_percents=[20]),
])
def test_main_preparation_rejects_duplicate_or_missing_cases(tmp_path,mutation):
    d=preparation(tmp_path); mutation(d)
    with pytest.raises(ValueError):
        ExperimentManifest.parse(d,tmp_path/'m.json')

