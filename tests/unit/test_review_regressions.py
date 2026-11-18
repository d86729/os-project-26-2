from dataclasses import replace
from fractions import Fraction
import os
import pytest
from protection.models import (ExperimentCondition, RunRecord, SolverDiagnostics,
    strict_json_loads, atomic_json)
from protection.errors import InvalidScenarioError


@pytest.mark.parametrize('changes',[{'environment':[]},{'events':[]},
    {'upper_bound':{}},{'solver_diagnostics':{}},{'case_id':'bad'},
    {'submission_sha256':'bad'},{'environment':(('a','x'),('a','y'))}])
def test_record_rejects_mutable_invalid_nested_values(changes):
    c=ExperimentCondition('a'*64,20,2,'exhaustive',1)
    with pytest.raises(InvalidScenarioError): RunRecord('r',c,**changes)


def test_condition_hash_and_diagnostic_strings():
    with pytest.raises(InvalidScenarioError): ExperimentCondition('bad',20,2,'exhaustive',1)
    with pytest.raises(InvalidScenarioError):
        SolverDiagnostics(True,0,[],1,0.,0.,Fraction(0),Fraction(0),'certified',0.)
    with pytest.raises(InvalidScenarioError):
        strict_json_loads('{"overflow":1e999}')


def test_new_atomic_file_never_publishes_empty(tmp_path,monkeypatch):
    # Observe the destination at publication: old O_EXCL reservation exposes ''.
    path=tmp_path/'new.json'
    real_replace=os.replace
    def checked_replace(source,destination):
        assert not path.exists(), 'empty placeholder exposed before atomic publication'
        return real_replace(source,destination)
    monkeypatch.setattr(os,'replace',checked_replace)
    atomic_json(path,{'complete':True})
    assert strict_json_loads(path.read_text())=={'complete':True}
