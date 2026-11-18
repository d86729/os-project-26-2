from test_worker_timing import run
import protection.runner as runner


def test_baseline_counts(path_scenario, tmp_path):
    r = run(path_scenario, tmp_path, 'class Submission:\n def solve(self,s,b,c): return []',
            memory_limit_bytes=1)
    assert r.status == 'memory_limit'
    assert r.algorithm_peak_rss_bytes > 1
    assert r.submitted_evaluation is None


def test_native_allocation_and_diagnostic(path_scenario, tmp_path):
    r = run(path_scenario, tmp_path,
        'import time\nclass Submission:\n def solve(self,s,b,c):\n'
        '  c.evaluate([])\n  x=bytearray(100_000_000)\n  time.sleep(2)\n  return []',
        memory_limit_bytes=80_000_000)
    assert r.status == 'memory_limit', r
    assert r.algorithm_peak_rss_bytes > 80_000_000
    assert r.recovered_protected_ids is None
    assert r.submitted_evaluation is None
    assert r.observed_max_sample_gap_ms > 0


def test_evaluator_rss_is_charged(path_scenario, tmp_path):
    r = run(path_scenario, tmp_path,
        'class Submission:\n def solve(self,s,b,c):\n  c.evaluate([])\n  return []',
        memory_limit_bytes=80_000_000, _evaluation_allocation_bytes=100_000_000)
    assert r.status == 'memory_limit', r
    assert r.algorithm_peak_rss_bytes > 80_000_000
    assert r.evaluation_peak_rss_bytes is None
    assert r.submitted_evaluation is None


def test_final_rss_and_cleanup(path_scenario, tmp_path):
    import multiprocessing
    previous = {p.pid for p in multiprocessing.active_children()}
    r = run(path_scenario, tmp_path,
        'class Submission:\n def solve(self,s,b,c):\n  self.x=bytearray(100_000_000)\n  return []',
        memory_limit_bytes=80_000_000)
    assert r.status == 'memory_limit'
    assert r.submitted_evaluation is None
    assert {p.pid for p in multiprocessing.active_children()} == previous


def test_monitor_unavailable(path_scenario, tmp_path, monkeypatch):
    def broken(pid): raise OSError('test /proc unavailable')
    monkeypatch.setattr(runner, '_read_rss', broken)
    r = run(path_scenario, tmp_path, 'class Submission:\n def solve(self,s,b,c): return []')
    assert r.status == 'failed'
    assert r.termination_reason == 'resource_monitor_unavailable'
    assert not r.resource_monitor_supported
