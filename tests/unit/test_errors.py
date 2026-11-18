import pytest
from protection.errors import (InvalidScenarioError, InvalidProtectionError,
                               EvaluationError, DeadlineExceeded)


@pytest.mark.parametrize('cls', [InvalidScenarioError, InvalidProtectionError, EvaluationError, DeadlineExceeded])
def test_errors_are_not_scores(cls):
    with pytest.raises(cls):
        raise cls('explicit failure')
    assert not issubclass(cls, (int, float))


def test_evaluation_reason_and_diagnostics():
    error = EvaluationError('certificate failed', reason='certificate_failed', diagnostics={'attempts': 2})
    assert error.reason == 'certificate_failed'
    assert error.diagnostics == {'attempts': 2}
    assert not isinstance(DeadlineExceeded('deadline'), EvaluationError)
