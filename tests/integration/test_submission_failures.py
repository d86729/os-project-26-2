import pytest
from test_worker_timing import run
from protection.runner import run_submission
from protection.models import ScenarioBundle


@pytest.mark.parametrize('statement', ['return None','return [True]','return [0,0]',
    'return [1,0]','return [999]','return [1]','raise RuntimeError("test")',
    'raise MemoryError("not observed RSS")','s.seed=10','return (0,)',
    'import os; os._exit(9)'])
def test_invalid_failures(path_scenario,tmp_path,statement):
    r=run(path_scenario,tmp_path,'class Submission:\n def solve(self,s,b,c):\n  '+statement)
    assert r.status == 'failed', r
    assert r.submitted_evaluation is None


def test_checkpoint_timeout(path_scenario,tmp_path):
    r=run(path_scenario,tmp_path,'import time\nclass Submission:\n def solve(self,s,b,c):\n  c.evaluate([])\n  time.sleep(3)',limit_seconds=.4)
    assert r.status=='timeout'
    # No per-evaluation IPC/checkpoints: killed-worker local state is lost.
    assert r.recovered_protected_ids is None
    assert r.submitted_evaluation is None


@pytest.mark.parametrize('source', ['this is not python!', 'import missing_package_xyz', 'class Other: pass'])
def test_load_error(path_scenario,tmp_path,source):
    r=run(path_scenario,tmp_path,source)
    assert r.status=='failed'
    assert r.termination_reason=='submission_load_error'
    assert r.launch_status=='started'


def test_missing(path_scenario,tmp_path):
    r=run_submission(ScenarioBundle(path_scenario,40,4),tmp_path/'missing.py','Submission')
    assert r.launch_status=='not_started'
    assert r.search_seconds is None


@pytest.mark.parametrize('mode', ['error','exit'])
def test_evaluation_failure(path_scenario,tmp_path,mode):
    r=run(path_scenario,tmp_path,'class Submission:\n def solve(self,s,b,c):\n  c.evaluate([])\n  return []',_evaluation_failure=mode)
    assert r.status=='failed'
    assert r.submitted_evaluation is None


def test_final_evaluation_failure(path_scenario,tmp_path):
    r=run(path_scenario,tmp_path,'class Submission:\n def solve(self,s,b,c): return []',_evaluation_failure='error')
    assert r.status=='failed'
    assert r.submitted_protected_ids==()
    assert r.submitted_evaluation is None


def test_arbitrary_return_never_unpickled(path_scenario,tmp_path):
    marker=tmp_path/'unsafe'
    r=run(path_scenario,tmp_path,
        'class Bad:\n def __reduce__(self):\n  open('+repr(str(marker))+',"w").write("bad")\n  return (list,())\n'
        'class Submission:\n def solve(self,s,b,c): return Bad()')
    assert r.status=='failed'
    assert not marker.exists()


def test_not_implemented(path_scenario,tmp_path):
    r=run(path_scenario,tmp_path,'class Submission:\n def solve(self,s,b,c): raise NotImplementedError("pending")')
    assert r.status=='not_implemented'
    assert r.submitted_evaluation is None
