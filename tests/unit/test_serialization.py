from dataclasses import replace
import json
import pytest
from protection.models import (ScenarioBundle, OptimalReference, Evaluation, save_scenario, load_scenario,
                               save_bundle, load_bundle, canonical_json, strict_json_loads, to_data, atomic_json)
from protection.errors import InvalidScenarioError


def test_roundtrip_and_overwrite_refusal(path_scenario,tmp_path):
    p=tmp_path/'input.json'; save_scenario(path_scenario,p)
    assert load_scenario(p) == path_scenario
    assert json.loads(p.read_text())['artifact_kind']=='scenario_input'
    with pytest.raises(FileExistsError): save_scenario(path_scenario,p)
    save_scenario(path_scenario,p,overwrite=True)
    assert not list(tmp_path.glob('*.tmp'))
    with pytest.raises(InvalidScenarioError): load_bundle(p)


@pytest.mark.parametrize('mutation', [
    lambda d: d.update(extra=1), lambda d: d.pop('schema_version'),
    lambda d: d['scenario'].update(scenario_id='0'*64),
    lambda d: d['scenario']['nodes'][0].update(x=.2),
    lambda d: d['scenario']['nodes'][0].update(id=True),
    lambda d: d['scenario']['generation'].update(alpha=2),
    lambda d: d['scenario'].pop('environment')])
def test_corrupt_input_rejected(path_scenario,tmp_path,mutation):
    p=tmp_path/'input.json'; save_scenario(path_scenario,p)
    d=json.loads(p.read_text()); mutation(d); p.write_text(json.dumps(d))
    with pytest.raises(InvalidScenarioError): load_scenario(p)


@pytest.mark.parametrize('text', ['{"x":1,"x":2}', '{"x":NaN}', '{"x":Infinity}', '{"x":1'])
def test_strict_json(text):
    with pytest.raises(InvalidScenarioError): strict_json_loads(text)


def test_case_hash_and_reference_deletion(path_scenario,tmp_path):
    s=path_scenario
    a=ScenarioBundle(s,20,2); b=ScenarioBundle(s,40,4)
    assert a.case_id != b.case_id
    assert replace(s,environment=(('test','changed'),)).scenario_id == s.scenario_id
    # Structural test-only reference, never published as a verified distribution.
    ev=Evaluation((),0,0,0.,0.,0.,0,(0.,0.))
    ref=OptimalReference((),0,ev,'test-only',(),600.,1.)
    original=replace(a,optimal_reference=ref)
    assert original.case_id == a.case_id
    p=tmp_path/'copy.json'; save_bundle(original,p)
    d=json.loads(p.read_text()); d.pop('optimal_reference'); p.write_text(json.dumps(d))
    copy=load_bundle(p)
    assert copy==a and copy.algorithm_input()==original.algorithm_input()
    with pytest.raises(InvalidScenarioError): load_bundle(p,require_reference=True)
    d['budget_percent']=40; d['budget']=4; p.write_text(json.dumps(d))
    with pytest.raises(InvalidScenarioError): load_bundle(p)


def test_canonical_and_nonfinite():
    assert canonical_json({'z':1,'a':'한'}) == '{"a":"한","z":1}'
    with pytest.raises(InvalidScenarioError): canonical_json({'x':float('nan')})


def test_atomic_failure_does_not_damage_previous(tmp_path,monkeypatch):
    import os
    p=tmp_path/'safe.json'; atomic_json(p,{'v':1})
    def fail(*args): raise OSError('injected replace failure')
    monkeypatch.setattr(os,'replace',fail)
    with pytest.raises(OSError): atomic_json(p,{'v':2},overwrite=True)
    assert json.loads(p.read_text())=={'v':1}
    assert not list(tmp_path.glob('*.tmp'))
