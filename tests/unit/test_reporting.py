from dataclasses import replace
import csv
import pytest
from protection.models import (ExperimentCondition, RunRecord, ScenarioBundle, Evaluation,
                               OptimalReference)
from protection.errors import EvaluationError


def record(scenario, *, status='completed', units=500000, pairs=1, run_id='a'):
    bundle = ScenarioBundle(scenario,40,4)
    ev = Evaluation((0,),4,pairs,pairs/3,units*30/1000000,units/1000000,units,(.1,.1))
    return RunRecord(run_id,ExperimentCondition(scenario.scenario_id,40,4,'member_1',300),
        case_id=bundle.case_id,status=status,launch_status='started',search_seconds=1.,
        submitted_protected_ids=(0,) if status=='completed' else None,
        submitted_evaluation=ev if status=='completed' else None,
        recovered_protected_ids=(0,) if status!='completed' else None,
        recovered_evaluation=ev if status!='completed' else None,
        submission_sha256='a'*64)


def test_failures_preserved_and_no_fake_zero(path_scenario,tmp_path):
    from protection.reporting import write_report
    records=[record(path_scenario), record(path_scenario,status='timeout',run_id='b')]
    report=write_report(records,{},tmp_path)
    assert report['runs'][1]['delivery_units'] is None
    assert report['runs'][1]['gap_delivery_units'] is None
    summary=report['summaries'][0]
    assert summary['total_count']==2 and summary['success_count']==1
    assert summary['delivery_ratio_median']==.5
    assert summary['status_counts']=={'completed':1,'timeout':1}
    rows=list(csv.DictReader((tmp_path/'runs.csv').open()))
    assert len(rows)==2 and rows[1]['delivery_units']==''
    assert rows[1]['recovered_protected_ids']=='[0]'


def test_independent_statistics_zero_success_and_separation(path_scenario,tmp_path):
    from protection.reporting import write_report
    records=[record(path_scenario,units=u,run_id=str(i)) for i,u in enumerate((200000,800000,500000))]
    report=write_report(records,{},tmp_path)
    s=report['summaries'][0]
    assert (s['delivery_ratio_min'],s['delivery_ratio_median'],s['delivery_ratio_max'])==(.2,.5,.8)
    fail=record(path_scenario,status='failed')
    result=write_report([fail],{},tmp_path)
    assert result['summaries'][0]['delivery_ratio_median'] is None
    assert result['summaries'][0]['search_seconds']==[1.]
    changed=replace(records[0],policy_version='different')
    assert len(write_report([records[0],changed],{},tmp_path)['summaries'])==2
    changed_limit=replace(records[0],condition=replace(records[0].condition,limit_seconds=10))
    assert len(write_report([records[0],changed_limit],{},tmp_path)['summaries'])==2
    main=replace(records[0],run_kind='main')
    assert len(write_report([records[0],main],{},tmp_path)['summaries'])==2


def test_lexicographic_gap(path_scenario,tmp_path):
    from protection.reporting import write_report
    r=record(path_scenario)
    ref_ev=replace(r.submitted_evaluation,delivery_units=600000,delivery_ratio=.6,delivered_mbps=18.)
    ref=OptimalReference((0,),4,ref_ev,'trusted-test',(('test','yes'),),600,1.)
    bundle=ScenarioBundle(path_scenario,40,4,optimal_reference=ref)
    banks={bundle.case_id:bundle}
    row=write_report([r],banks,tmp_path)['runs'][0]
    assert row['gap_connected_pairs']==0 and row['gap_delivery_units']==100000
    fewer=replace(r,submitted_evaluation=replace(r.submitted_evaluation,connected_pairs=0,connected_ratio=0.))
    row=write_report([fewer],banks,tmp_path)['runs'][0]
    assert row['gap_connected_pairs']==1 and row['gap_delivery_units'] is None
    better=replace(r,submitted_evaluation=replace(r.submitted_evaluation,delivery_units=700000))
    with pytest.raises(EvaluationError): write_report([better],banks,tmp_path)
