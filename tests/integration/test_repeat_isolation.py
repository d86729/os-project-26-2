from protection.models import ScenarioBundle, save_bundle, ExperimentManifest
from protection.runner import grade_manifest


def manifest(tmp_path,path_scenario,random=True):
    bundle=ScenarioBundle(path_scenario,40,4)
    save_bundle(bundle,tmp_path/'case.json')
    file=tmp_path/'one.py'
    file.write_text('counter=0\nclass Submission:\n def solve(self,s,b,c):\n  global counter\n  assert counter==0\n  counter+=1\n  assert c.repeat_count in (1,5)\n  if c.repeat_count==5: assert c.algorithm_seed==[11,22,33,44,55][c.repeat_index]\n  c.evaluate([])\n  return []')
    d=dict(schema_version=1,kind='grading',run_kind='smoke',owners={'common':'test'},output_dir='out',
        bank=[dict(path='case.json',case_id=bundle.case_id)],
        submission=dict(method_id='member_1',file='one.py',class_name='Submission',uses_randomness=random,
            algorithm_seeds=[11,22,33,44,55] if random else [],owner='test',strategy_name='test',strategy_version='0'),
        limits=dict(algorithm_seconds=300,algorithm_memory_bytes=4000000000),resource_policy=dict(sample_interval_ms=10))
    return ExperimentManifest.parse(d,tmp_path/'manifest.json')


def test_five_fresh_runs(path_scenario,tmp_path,monkeypatch):
    m=manifest(tmp_path,path_scenario)
    import protection.generation as generation
    def forbidden(*a,**k): raise AssertionError('must not generate')
    monkeypatch.setattr(generation,'generate_scenario',forbidden)
    records=grade_manifest(m)
    assert len(records)==5
    assert [r.algorithm_seed for r in records]==[11,22,33,44,55]
    assert all(r.status=='completed' for r in records)
    assert len({r.run_id for r in records})==5
    assert len({next(e for e in r.events if e.startswith('algorithm_pid=')) for r in records})==5
    assert all('evaluation_initial_cache_size=0' in r.events for r in records)


def test_deterministic_and_continue(path_scenario,tmp_path):
    m=manifest(tmp_path,path_scenario,False)
    records=grade_manifest(m)
    assert len(records)==1 and records[0].algorithm_seed is None
    assert records[0].status=='completed'
    d=m.to_dict();d['submission']['uses_randomness']=True;d['submission']['algorithm_seeds']=[11,22,33,44,55]
    (tmp_path/'one.py').write_text('class Submission:\n def solve(self,s,b,c):\n  if c.repeat_index==1: raise ValueError("one failure")\n  return []')
    records=grade_manifest(ExperimentManifest.parse(d,tmp_path/'manifest.json'))
    assert [r.status for r in records]==['completed','failed','completed','completed','completed']
