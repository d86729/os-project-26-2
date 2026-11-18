"""D-003 certificates: real HiGHS solves, explicitly labelled fault injection."""
from fractions import Fraction
import time

import numpy as np
import pytest
from scipy.sparse import csr_matrix, issparse

from protection.errors import DeadlineExceeded, EvaluationError
from protection.models import EvaluationPolicy, certify_interval


def flow():
    from protection import flow
    return flow


def test_real_solver_sparse_options_and_exact_certificate(path_scenario, monkeypatch):
    f = flow()
    real = f.linprog
    captured = []
    def observe(*args, **kwargs):
        assert issparse(kwargs['A_eq']) and issparse(kwargs['A_ub'])
        assert kwargs['method'] == 'highs'
        assert kwargs['options'] == dict(presolve=True, threads=1,
            primal_feasibility_tolerance=1e-9, dual_feasibility_tolerance=1e-9,
            ipm_optimality_tolerance=1e-10)
        r = real(*args, **kwargs)
        captured.append(r)
        return r
    monkeypatch.setattr(f, 'linprog', observe)
    r = f.maximum_delivery(path_scenario, (0, 1))
    assert len(captured) == 1
    assert r.diagnostics.certified_lower == r.diagnostics.certified_upper == Fraction(20)
    assert r.diagnostics.maximum_residual == 0
    assert r.diagnostics.attempts == 1
    assert r.delivered_mbps == -captured[0].fun
    assert r.delivery_units == 666667


@pytest.mark.parametrize('n', [3, 6, 8])
def test_real_generated_certificates(n):
    from protection.generation import generate_scenario
    f = flow()
    s = generate_scenario(n, 0)
    ids = tuple(range(len(s.edges)))
    for surviving in ((), ids, ids[::2], ids[1::2]):
        r = f.maximum_delivery(s, surviving)
        assert 0 <= r.diagnostics.certified_lower <= r.diagnostics.certified_upper <= sum(d.amount_mbps for d in s.demands)
        assert r.delivery_units == certify_interval(r.diagnostics.certified_lower,
            r.diagnostics.certified_upper, sum(d.amount_mbps for d in s.demands))


def test_real_fractional_midpoints_and_sign_equation():
    # Integer LPs: max t, k*t<=numerator. Their exact optima are
    # 0.0000005 and 0.0000015; no invented solver output.
    f = flow()
    for numerator, units in ((1, 0), (3, 2)):
        lp = f.LinearProgram(c=np.array([-1]), G=csr_matrix([[2000000]]),
            b=np.array([numerator]), A=csr_matrix((0, 1), dtype=int),
            upper=np.array([1]), demand_count=1, total=1)
        result = f.linprog(lp.c, A_ub=lp.G, b_ub=lp.b, bounds=[(0, 1)],
                           method='highs', options={'threads': 1})
        assert result.success
        lower, upper = f._certify(lp, result, EvaluationPolicy(), None)
        assert lower == upper == Fraction(numerator, 2000000)
        assert certify_interval(lower, upper, 1) == units


@pytest.mark.parametrize('part', ['ineqlin', 'eqlin', 'lower', 'upper'])
def test_corrupt_marginal_rejected_exactly(path_scenario, monkeypatch, part):
    f = flow(); real = f.linprog
    def corrupt(*a, **kw):
        r = real(*a, **kw)
        # Explicit fault injection: tiny enough for floating tolerances,
        # but not zero under denominator-limited rational reconstruction.
        r[part].marginals[0] += 1e-8
        return r
    monkeypatch.setattr(f, 'linprog', corrupt)
    if part in ('eqlin', 'lower'):
        result = f.maximum_delivery(path_scenario, (0, 1))
        assert result.diagnostics.certificate_status == 'highs_residual_fallback'
        assert result.diagnostics.certified_lower is None
        assert result.delivery_units == 666667
    else:
        # Perturbed capacity/bound multipliers produce a gap > 1e-7.
        with pytest.raises(EvaluationError):
            f.maximum_delivery(path_scenario, (0, 1))


def test_small_certificate_failure_falls_back_without_second_solve(path_scenario, monkeypatch):
    f = flow(); real = f.linprog; options = []
    def first_corrupt(*a, **kw):
        options.append(kw['options'].copy())
        r = real(*a, **kw)
        if len(options) == 1:
            r.lower.marginals[0] += 1e-8
        return r
    monkeypatch.setattr(f, 'linprog', first_corrupt)
    r = f.maximum_delivery(path_scenario, (0, 1), deadline=time.monotonic()+10)
    assert [o['presolve'] for o in options] == [True]
    assert 0 < options[0]['time_limit'] <= 10
    assert r.diagnostics.attempts == 1 and r.delivery_units == 666667
    assert r.diagnostics.certificate_status == 'highs_residual_fallback'
    from protection.models import SolverDiagnostics, to_data, from_data
    assert from_data(SolverDiagnostics, to_data(r.diagnostics)) == r.diagnostics


def test_feasible_but_ambiguous_interval_retried(path_scenario, monkeypatch):
    f = flow(); real = f.linprog; calls = []
    def suboptimal_primal(*a, **kw):
        # Explicit mock of a solver claiming optimality: all-zero primal is
        # feasible, actual solver dual still certifies U=20; [0,20] is ambiguous.
        r = real(*a, **kw); calls.append(kw['options']['presolve'])
        r.x[:] = 0; r.fun = 0.
        return r
    monkeypatch.setattr(f, 'linprog', suboptimal_primal)
    with pytest.raises(EvaluationError) as exc:
        f.maximum_delivery(path_scenario, (0, 1))
    assert exc.value.reason == 'numeric_ambiguity'
    assert calls == [True, False]


@pytest.mark.parametrize('delta,reason', [(1e-8, 'certificate_failed'), (2e-7, 'residual_failed')])
def test_residual_threshold_controls_fallback(path_scenario, monkeypatch, delta, reason):
    f = flow(); real = f.linprog
    def perturb(*a, **kw):
        r = real(*a, **kw); r.x[0] += delta; r.fun -= delta
        return r
    monkeypatch.setattr(f, 'linprog', perturb)
    if delta < 1e-7:
        result = f.maximum_delivery(path_scenario, (0, 1))
        assert result.delivery_units == 666667
        assert result.diagnostics.certificate_status == 'highs_residual_fallback'
    else:
        with pytest.raises(EvaluationError) as exc:
            f.maximum_delivery(path_scenario, (0, 1))
        assert exc.value.reason == reason


@pytest.mark.parametrize('field', ['fun', 'dual'])
def test_nonfinite_objective_or_dual(path_scenario, monkeypatch, field):
    f = flow(); real = f.linprog
    def corrupt(*a, **kw):
        r = real(*a, **kw)
        if field == 'fun': r.fun = float('inf')
        else: r.eqlin.marginals[0] = float('nan')
        return r
    monkeypatch.setattr(f, 'linprog', corrupt)
    with pytest.raises(EvaluationError) as exc:
        f.maximum_delivery(path_scenario, (0, 1))
    assert exc.value.reason == 'nonfinite_result'


def test_deadline_expiring_in_solver_rejects_result(path_scenario, monkeypatch):
    f = flow(); real = f.linprog
    clock = [0.]
    monkeypatch.setattr(f, 'monotonic', lambda: clock[0])
    def expire(*a, **kw):
        r = real(*a, **kw); clock[0] = 2.; return r
    monkeypatch.setattr(f, 'linprog', expire)
    with pytest.raises(DeadlineExceeded):
        f.maximum_delivery(path_scenario, (0, 1), deadline=1.)


def test_deadline_expiring_in_certificate_rejects_result(path_scenario, monkeypatch):
    f = flow(); real = f._certify
    clock = [0.]
    monkeypatch.setattr(f, 'monotonic', lambda: clock[0])
    def expire(*a, **kw):
        result = real(*a, **kw); clock[0] = 2.; return result
    monkeypatch.setattr(f, '_certify', expire)
    with pytest.raises(DeadlineExceeded):
        f.maximum_delivery(path_scenario, (0, 1), deadline=1.)
