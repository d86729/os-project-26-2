from decimal import Decimal
from fractions import Fraction
import pytest
from protection.models import EvaluationPolicy, coordinate_units, rounded_fraction_units, certify_interval
from protection.errors import EvaluationError, InvalidScenarioError


def test_policy_is_versioned_and_fixed():
    p = EvaluationPolicy()
    assert p.version == 'evaluation-v2'
    assert p.residual_relative_tolerance == 1e-7
    assert p.certificate_denominator_limit == 10**9
    with pytest.raises(InvalidScenarioError):
        EvaluationPolicy(threads=2)
    with pytest.raises(InvalidScenarioError):
        EvaluationPolicy(version='evaluation-v1')


@pytest.mark.parametrize('value,expected', [('0.0000000005', 0), ('0.0000000015', 2), ('-0.0', 0), ('1.0', 10**9)])
def test_coordinate_half_even(value, expected):
    assert coordinate_units(Decimal(value)) == expected


def test_exact_midpoints_and_interval():
    assert rounded_fraction_units(Fraction(1, 2000000)) == 0
    assert rounded_fraction_units(Fraction(3, 2000000)) == 2
    assert certify_interval(Fraction(1), Fraction(1), 3) == 333333
    with pytest.raises(EvaluationError, match='rounding'):
        certify_interval(Fraction(499999, 1000000), Fraction(500001, 1000000), 1)
    with pytest.raises(EvaluationError):
        certify_interval(Fraction(-1, 10**12), Fraction(0), 1)
