"""Scale operation uses mocks, never real 3-hour searches or selected research sizes."""
import json
from pathlib import Path
import pytest
from protection.models import ExperimentManifest, ExperimentCondition, RunRecord, save_scenario
from protection.generation import generate_scenario

ROOT = Path(__file__).resolve().parents[2]


def manifest(tmp_path, sizes=(3,4,5)):
    d = json.loads((ROOT/'configs/smoke.json').read_text())
    d.update(run_kind='scale_probe', sizes=list(sizes), size_groups={str(n):'probe' for n in sizes},
             seeds_by_size={str(n):[0] for n in sizes},output_dir=str(tmp_path/'out'))
    return d


@pytest.mark.parametrize('kind', ['scale_probe','main'])
def test_multiple_predeclared_graphs_per_medium_size(tmp_path,kind):
    d = manifest(tmp_path); d['run_kind'] = kind
    if kind == 'main': d['size_groups'] = {str(n):'medium_large' for n in d['sizes']}
    d['seeds_by_size']['3'] = [0,1]
    m = ExperimentManifest.parse(d,tmp_path/'manifest.json')
    assert m.to_dict()['seeds_by_size']['3'] == [0, 1]


def test_main_medium_requires_three_sizes(tmp_path):
    d = manifest(tmp_path,(3,4)); d['run_kind']='main'
    d['size_groups']={str(n):'medium_large' for n in d['sizes']}
    with pytest.raises(ValueError, match='three'):
        ExperimentManifest.parse(d,tmp_path/'manifest.json')


def test_scale_preserves_failed_seed_and_all_budgets(tmp_path,monkeypatch):
    from protection.operations import run_scale_probe
    from protection import exact
    d=manifest(tmp_path); m=ExperimentManifest.parse(d,tmp_path/'manifest.json')
    for n in d['sizes']:
        save_scenario(generate_scenario(n,0),tmp_path/f'out/inputs/n{n}-seed0.json')
    calls=[]
    def search(s,p,**kw):
        calls.append((len(s.nodes),s.seed,p,kw))
        return RunRecord(str(len(calls)),ExperimentCondition(s.scenario_id,p,sum(e.cost for e in s.edges)*p//100,'exhaustive',10800),
                         status='timeout',run_kind='scale_probe',termination_reason='timeout')
    monkeypatch.setattr(exact,'search',search)
    summary=run_scale_probe(m)
    assert len(calls)==6 and all(c[3]['manifest'] is m for c in calls)
    assert summary['complete'] is False
    assert summary['qualified_sizes']==[]
    rows=[json.loads(x) for x in (tmp_path/'out/scale_probe.jsonl').read_text().splitlines()]
    assert len(rows)==6 and all(r['status']=='timeout' for r in rows)
    assert summary['cases'][0]['seed']==0
    with pytest.raises(ValueError,match='exists'):
        run_scale_probe(m)


def test_scale_missing_input_starts_nothing(tmp_path,monkeypatch):
    from protection.operations import run_scale_probe
    from protection import exact
    def forbidden(*a,**k): raise AssertionError('must validate every input first')
    monkeypatch.setattr(exact,'search',forbidden)
    with pytest.raises(OSError):
        run_scale_probe(ExperimentManifest.parse(manifest(tmp_path),tmp_path/'m.json'))
    assert not (tmp_path/'out/scale_probe.jsonl').exists()


@pytest.mark.parametrize('sizes,complete', [((3,4),False), ((3,4,5),True)])
def test_scale_completeness_requires_three_distinct_sizes(tmp_path,sizes,complete):
    from types import SimpleNamespace
    from protection.operations import scale_summary
    m=ExperimentManifest.parse(manifest(tmp_path,sizes),tmp_path/'m.json')
    scenarios=[generate_scenario(n,0) for n in sizes]
    # Pure summary doubles, not measured records or research results.
    records=[SimpleNamespace(condition=SimpleNamespace(scenario_id=s.scenario_id,
        budget_percent=p, method='exhaustive',limit_seconds=10800), run_kind='scale_probe',
        status='completed', optimality_proven=True,search_seconds=1)
        for s in scenarios for p in (20,40)]
    assert scale_summary(m,scenarios,records)['complete'] is complete
    assert scale_summary(m,scenarios,records[:-1])['complete'] is False
    with pytest.raises(ValueError,match='duplicate'):
        scale_summary(m,scenarios,records+[records[0]])


def test_scale_environment_failure_blocks_remaining_and_preserves_rows(tmp_path,monkeypatch):
    from protection.operations import run_scale_probe
    from protection import exact
    d=manifest(tmp_path); m=ExperimentManifest.parse(d,tmp_path/'m.json')
    for n in d['sizes']:
        save_scenario(generate_scenario(n,0),tmp_path/f'out/inputs/n{n}-seed0.json')
    calls=[]
    def blocked(*args,**kwargs):
        calls.append(args)
        raise RuntimeError('worker remains alive')
    monkeypatch.setattr(exact,'search',blocked)
    summary=run_scale_probe(m)
    assert len(calls)==1 and not summary['complete']
    rows=[json.loads(x) for x in (tmp_path/'out/scale_probe.jsonl').read_text().splitlines()]
    assert len(rows)==6
    assert all(r['termination_reason']=='environment_blocked' for r in rows)

