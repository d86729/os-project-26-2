"""Exercise the deployed stdin/stdout grader in a delegated cgroup service."""
import pytest

from protection.models import ScenarioBundle
from protection.program import grade_program, protected_ids


@pytest.mark.parametrize('output', [b'', b'1', b'0 1', b'2 0 0', b'2 1 0',
                                   b'1 -1', b'1 9', b'1 1', b'0.0', b'\xff'])
def test_invalid_output(path_scenario, output):
    with pytest.raises((ValueError, UnicodeError)):
        protected_ids(output, ScenarioBundle(path_scenario, 40, 4))


@pytest.mark.parametrize(('source', 'status', 'reason'), [
    (b'print(0)', 'completed', 'returned'),
    (b'raise SystemExit(75)', 'not_implemented', 'not_implemented'),
    (b'raise RuntimeError("test failure")', 'failed', 'nonzero_exit'),
    (b'print("1 9")', 'failed', 'invalid_output'),
    (b'while True: pass', 'timeout', 'deadline'),
    (b'import os\nos.write(1, b"x" * 70000)', 'failed', 'output_limit'),
    (b'a = bytearray(400_000_000)', 'memory_limit', 'memory_limit'),
])
def test_submission_status(path_scenario, source, status, reason):
    record = grade_program(ScenarioBundle(path_scenario, 40, 4), source,
                           seconds=1, memory_bytes=256_000_000)
    assert (record.status, record.termination_reason) == (status, reason), record.error_message
    assert (record.submitted_evaluation is not None) == (status == 'completed')
    assert record.algorithm_vcpu_limit == 1


def test_cancelled_submission_never_executes(path_scenario, monkeypatch):
    def unexpected(*args, **kwargs):
        pytest.fail('cancelled submission was executed')

    monkeypatch.setattr('protection.program.execute_program', unexpected)
    record = grade_program(ScenarioBundle(path_scenario, 40, 4), b'print(0)', cancelled=lambda: True)
    assert record.termination_reason == 'cancelled'
    assert record.submitted_evaluation is None
