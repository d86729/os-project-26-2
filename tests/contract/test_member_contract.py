import importlib.util
import inspect
from pathlib import Path
import pytest
from protection.models import ScenarioBundle
from protection.runner import run_submission


@pytest.mark.parametrize('i',[1,2,3])
def test_independent_skeleton(i,path_scenario):
    path=Path(f'algorithms/member_{i}.py')
    spec=importlib.util.spec_from_file_location(f'only_{i}',path)
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    cls=getattr(module,f'Member{i}Protector')
    assert list(inspect.signature(cls.solve).parameters)==['self','scenario','budget','context']
    for word in ['algorithm_seed','repeat_count','4,000,000,000','EvaluationError']:
        assert word in cls.__doc__
    with pytest.raises(NotImplementedError): cls().solve(None,None,None)
    r=run_submission(ScenarioBundle(path_scenario,40,4),path,cls.__name__,limit_seconds=2)
    assert r.status=='not_implemented'
    assert r.submitted_evaluation is None


def test_reference_excluded_and_readonly(path_scenario,tmp_path):
    path=tmp_path/'one.py'
    path.write_text('class Submission:\n def solve(self,s,b,c):\n  assert not hasattr(s,"optimal_reference")\n  assert not hasattr(c,"optimal_reference")\n  assert c.algorithm_seed is None\n  assert c.repeat_index==0 and c.repeat_count==1\n  assert c.remaining_seconds()<=c.limit_seconds\n  try: c.algorithm_seed=3\n  except (AttributeError,TypeError): pass\n  else: raise AssertionError("mutable")\n  return []')
    r=run_submission(ScenarioBundle(path_scenario,40,4),path,'Submission',limit_seconds=2)
    assert r.status=='completed',(r.termination_reason,r.error_type,r.error_message,r.events)
