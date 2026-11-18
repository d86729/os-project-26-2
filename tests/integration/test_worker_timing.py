"""Real spawned test submissions; limits are smoke-only, not research results."""
import time
import pytest
from protection.models import ScenarioBundle
from protection.runner import run_submission


def run(path_scenario, tmp_path, body, **kwargs):
    file = tmp_path / 'submission.py'
    file.write_text(body)
    return run_submission(ScenarioBundle(path_scenario, 40, 4), file, 'Submission',
                          limit_seconds=kwargs.pop('limit_seconds', 2), **kwargs)


@pytest.mark.parametrize('body', [
    'import time; time.sleep(2)\nclass Submission: pass',
    'import time\nclass Submission:\n def __init__(self): time.sleep(2)',
    'class Submission:\n def solve(self,s,b,c):\n  while True: pass',
])
def test_import_constructor_loop_deadline(path_scenario, tmp_path, body):
    r = run(path_scenario, tmp_path, body, limit_seconds=.15)
    assert r.status == 'timeout'
    assert r.submitted_evaluation is None
    assert .15 <= r.search_seconds < 1
    assert r.shutdown_seconds < 2.5


def test_actual_return_not_intermediate(path_scenario, tmp_path):
    r = run(path_scenario, tmp_path,
            'class Submission:\n def solve(self,s,b,c):\n  c.evaluate([0])\n  return []')
    assert r.status == 'completed', r
    assert r.submitted_protected_ids == ()
    assert r.recovered_protected_ids == (0,)
    assert r.final_received_monotonic_ns < r.deadline_monotonic_ns
    assert r.final_scoring_seconds > 0
    assert r.evaluation_peak_rss_bytes is None
    assert r.algorithm_peak_rss_bytes > 0
    assert not any(e.startswith('evaluation_pid=') for e in r.events)


def test_direct_evaluator_same_process(path_scenario, tmp_path):
    r = run(path_scenario, tmp_path,
        'import os\nclass Submission:\n def solve(self,s,b,c):\n'
        '  assert not hasattr(c,"_channel")\n'
        '  assert c._evaluator.cache_size==0\n'
        '  c.evaluate([])\n  assert c._evaluator.evaluation_calls==1\n'
        '  assert c._evaluator.cache_size>0\n  return []')
    assert r.status == 'completed', r
    assert r.evaluation_calls == 2
    assert r.cache_hits > 0


def test_forced_kill_cleanup(path_scenario,tmp_path):
    import multiprocessing
    previous={p.pid for p in multiprocessing.active_children()}
    r=run(path_scenario,tmp_path,
        'import signal\nclass Submission:\n def solve(self,s,b,c):\n  signal.signal(signal.SIGTERM,signal.SIG_IGN)\n  while True: pass',
        limit_seconds=.2)
    assert r.status=='timeout'
    assert .19 <= r.shutdown_seconds < 2
    assert {p.pid for p in multiprocessing.active_children()}==previous


def test_evaluate_wait_in_deadline(path_scenario, tmp_path):
    r = run(path_scenario, tmp_path,
        'class Submission:\n def solve(self,s,b,c):\n  c.evaluate([])\n  return []',
        limit_seconds=.15, _evaluation_delay_seconds=.5)
    assert r.status == 'timeout'
    assert r.recovered_evaluation is None


def test_final_scoring_outside_deadline(path_scenario, tmp_path):
    r = run(path_scenario, tmp_path,
        'class Submission:\n def solve(self,s,b,c): return []',
        limit_seconds=.2, _evaluation_delay_seconds=.3)
    assert r.status == 'completed', r
    assert r.search_seconds < .2
    assert r.final_scoring_seconds >= .3
