"""방향별 용량과 수요를 희소 선형계획으로 풀고 전달 점수를 인증한다."""
from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
import math
from time import monotonic

import numpy as np
from scipy.optimize import linprog
from scipy.sparse import coo_matrix, csr_matrix

from protection.errors import DeadlineExceeded, EvaluationError, InvalidScenarioError
from protection.models import EvaluationPolicy, Scenario, SolverDiagnostics, certify_interval


@dataclass(frozen=True)
class DeliveryResult:
    delivered_mbps: float
    delivery_ratio: float
    delivery_units: int
    diagnostics: SolverDiagnostics


@dataclass(frozen=True)
class LinearProgram:
    """정수 계수로 min c*x를 푼다. G는 용량 제약, A는 흐름 보존 행렬이다.

    처음 demand_count개 변수는 수요별 실제 전달량이다. 목적함수의 해당 계수를
    -1로 두어 합계를 최대화한다. 쌍대 인증을 위해 변수별 상한도 명시한다.
    """
    c: np.ndarray
    G: csr_matrix
    b: np.ndarray
    A: csr_matrix
    upper: np.ndarray
    demand_count: int
    total: int


def _remaining(deadline):
    if deadline is None:
        return None
    remaining = deadline - monotonic()
    if remaining <= 0:
        raise DeadlineExceeded('Delivery evaluation deadline expired')
    return remaining


def _build_lp(scenario, surviving_ids, deadline):
    # 동일 간선의 양방향 용량을 각각 제약하고, 같은 방향의 모든 수요 흐름을 합산한다.
    n, h = len(scenario.nodes), len(scenario.demands)
    arcs = [(u, v, e.capacity_mbps) for i in surviving_ids
            for e in (scenario.edges[i],) for u, v in ((e.u, e.v), (e.v, e.u))]
    m = len(arcs)
    size = h + h*m
    rows, cols, values = [], [], []
    grows, gcols = [], []
    upper = [d.amount_mbps for d in scenario.demands]
    for k, d in enumerate(scenario.demands):
        _remaining(deadline)
        rows.extend((k*n+d.source, k*n+d.target))
        cols.extend((k, k)); values.extend((-1, 1))
        for a, (u, v, capacity) in enumerate(arcs):
            j = h + k*m + a
            rows.extend((k*n+u, k*n+v)); cols.extend((j, j)); values.extend((1, -1))
            grows.append(a); gcols.append(j); upper.append(capacity)
    A = coo_matrix((values, (rows, cols)), shape=(h*n, size), dtype=np.int64).tocsr()
    G = coo_matrix((np.ones(len(grows), dtype=np.int64), (grows, gcols)),
                   shape=(m, size), dtype=np.int64).tocsr()
    return LinearProgram(np.r_[-np.ones(h, dtype=np.int64), np.zeros(h*m, dtype=np.int64)],
                         G, np.array([a[2] for a in arcs], dtype=np.int64), A,
                         np.array(upper, dtype=np.int64), h,
                         sum(d.amount_mbps for d in scenario.demands))


def _failure(message, reason='certificate_failed'):
    raise EvaluationError(message, reason=reason)


def _vectors(lp, result):
    """Check shapes/finite objective and every primal and marginal component."""
    try:
        x, y, z, p, q = (np.asarray(v, dtype=float) for v in
                         (result.x, result.ineqlin.marginals, result.eqlin.marginals,
                          result.lower.marginals, result.upper.marginals))
        expected = (len(lp.c), lp.G.shape[0], lp.A.shape[0], len(lp.c), len(lp.c))
        if any(v.shape != (s,) for v, s in zip((x, y, z, p, q), expected)):
            _failure('Malformed solver vector shape', 'invalid_result')
        if not math.isfinite(float(result.fun)) or any(not np.isfinite(v).all() for v in (x, y, z, p, q)):
            _failure('Nonfinite solver primal/objective/marginal', 'nonfinite_result')
        return x, y, z, p, q
    except (AttributeError, TypeError, ValueError) as exc:
        raise EvaluationError('Missing or malformed solver vectors', reason='invalid_result') from exc


def _check_residuals(lp, result, policy):
    x, *_ = _vectors(lp, result)
    # Absolute residual is recorded; each check uses its own original RHS.
    groups = [(np.abs(lp.A @ x), np.ones(lp.A.shape[0])),
              (np.maximum(lp.G @ x - lp.b, 0), np.maximum(1, np.abs(lp.b))),
              (np.maximum(-x, 0), np.ones(len(x))),
              (np.maximum(x-lp.upper, 0), np.maximum(1, np.abs(lp.upper))),
              (np.array([abs(float(lp.c @ x)-float(result.fun))]),
               np.array([max(1, abs(float(result.fun)))]))]
    maximum = max((float(np.max(r, initial=0)) for r, _ in groups), default=0.)
    if any(np.any(r > policy.residual_relative_tolerance*scale) for r, scale in groups):
        _failure(f'Primal residual exceeds policy tolerance: {maximum}', 'residual_failed')
    return maximum


def _exact_matvec(matrix, vector, deadline):
    matrix = matrix.tocsr()
    result = []
    for row in range(matrix.shape[0]):
        _remaining(deadline)
        result.append(sum((int(matrix.data[j])*vector[matrix.indices[j]]
                           for j in range(matrix.indptr[row], matrix.indptr[row+1])), Fraction(0)))
    return result


def _certify(lp, result, policy, deadline):
    """수치 해를 유리수로 복원하고 원문제와 쌍대의 제약을 정확히 검사한다.

    실행 가능한 원문제 해의 전달량 합은 하한이다. 쌍대 목적값의 부호를
    바꾸면 전달량의 상한이 된다. 두 값 사이에 실제 최적 전달량이 있다.
    """
    def rational_vector(values):
        converted = []
        for value in values:
            _remaining(deadline)
            converted.append(Fraction(str(float(value))).limit_denominator(policy.certificate_denominator_limit))
        return converted
    x, y, z, p, q = (rational_vector(v) for v in _vectors(lp, result))
    if any(v < 0 or v > int(u) for v, u in zip(x, lp.upper)):
        _failure('Exact primal variable bound failed')
    if any(_exact_matvec(lp.A, x, deadline)):
        _failure('Exact primal conservation failed')
    if any(v > int(b) for v, b in zip(_exact_matvec(lp.G, x, deadline), lp.b)):
        _failure('Exact primal capacity failed')
    if any(v > 0 for v in y) or any(v < 0 for v in p) or any(v > 0 for v in q):
        _failure('Exact dual marginal sign failed')
    gy = _exact_matvec(lp.G.T, y, deadline)
    az = _exact_matvec(lp.A.T, z, deadline)
    if any(int(c) != a+b+lo+hi for c, a, b, lo, hi in zip(lp.c, gy, az, p, q)):
        _failure('Exact dual stationarity failed: c != G.T*y + A.T*z + p + q')
    lower = sum(x[:lp.demand_count], Fraction(0))
    upper = -sum((int(b)*v for b, v in zip(lp.b, y)), Fraction(0))
    upper -= sum((int(u)*v for u, v in zip(lp.upper, q)), Fraction(0))
    if not 0 <= lower <= upper <= lp.total:
        _failure('Exact primal/dual interval invalid')
    _remaining(deadline)
    return lower, upper


def maximum_delivery(scenario: Scenario, surviving_ids: tuple[int, ...], *,
                     deadline=None, require_certificate=False) -> DeliveryResult:
    """Return certified delivery on the surviving edge IDs, or an explicit error.

    deadline is an absolute time.monotonic() timestamp, or None (no solver
    time_limit). At most two solves are attempted, first with presolve then
    without. Failed attempts have diagnostic dictionaries, never fake L/U.
    Native hard cancellation still requires the caller's process supervisor.
    """
    start = monotonic()
    if deadline is not None and (type(deadline) not in (int, float) or not math.isfinite(deadline)):
        raise ValueError('deadline must be a finite monotonic timestamp or None')
    _remaining(deadline)
    if (type(surviving_ids) is not tuple or
        any(type(i) is not int or not 0 <= i < len(scenario.edges) for i in surviving_ids) or
        surviving_ids != tuple(sorted(set(surviving_ids)))):
        raise InvalidScenarioError('surviving_ids must be sorted unique valid integer edge IDs')
    lp = _build_lp(scenario, surviving_ids, deadline)
    policy = scenario.evaluation_policy
    history = []
    for attempt in range(1, policy.max_solver_attempts+1):
        options = dict(presolve=attempt == 1, threads=policy.threads,
                       primal_feasibility_tolerance=policy.primal_tolerance,
                       dual_feasibility_tolerance=policy.dual_tolerance,
                       ipm_optimality_tolerance=policy.ipm_tolerance)
        remaining = _remaining(deadline)
        if remaining is not None:
            options['time_limit'] = remaining
        detail = {'attempt': attempt, 'presolve': options['presolve']}
        try:
            try:
                result = linprog(lp.c, A_ub=lp.G, b_ub=lp.b,
                                 A_eq=lp.A, b_eq=np.zeros(lp.A.shape[0]),
                                 bounds=list(zip(np.zeros(len(lp.upper)), lp.upper)),
                                 method='highs', options=options)
            except Exception as exc:
                _remaining(deadline)
                raise EvaluationError(f'Solver raised {type(exc).__name__}: {exc}', reason='solver_failed') from exc
            _remaining(deadline)
            detail.update(status=int(result.status), message=str(result.message))
            if not result.success or result.status != 0:
                _failure(f'LP solver failed: {result.message}', 'solver_failed')
            residual = _check_residuals(lp, result, policy)
            detail.update(raw_delivered_mbps=-float(result.fun), maximum_residual=residual)
            certificate_status = 'certified'
            message = str(result.message)
            try:
                lower, upper = _certify(lp, result, policy, deadline)
                detail.update(certified_lower=lower, certified_upper=upper)
                units = certify_interval(lower, upper, lp.total)
            except EvaluationError as exc:
                if require_certificate or exc.reason not in ('certificate_failed', 'numeric_ambiguity'):
                    raise
                # 일반 제출의 근사 경로도 쌍대 조건과 목적값 잔차가 작을 때만 허용한다.
                x, y, z, p, q = _vectors(lp, result)
                stationarity = lp.G.T @ y + lp.A.T @ z + p + q - lp.c
                dual_objective = float(lp.b @ y + lp.upper @ q)
                residual = max(residual, float(np.max(np.abs(stationarity), initial=0)),
                    float(np.max(y, initial=0)), float(np.max(-p, initial=0)),
                    float(np.max(q, initial=0)), abs(float(result.fun)-dual_objective))
                if residual > 1e-7:
                    raise
                from protection.models import rounded_fraction_units
                units = rounded_fraction_units(Fraction(str(-float(result.fun))) / lp.total)
                lower = upper = None
                certificate_status = 'highs_residual_fallback'
                message += '; rational certificate unavailable: ' + str(exc)
            _remaining(deadline)
            raw = -float(result.fun)
            if raw < 0 or raw > lp.total:
                _failure('Raw delivery outside [0,total]; no clipping allowed')
            diagnostics = SolverDiagnostics(True, int(result.status), message, attempt,
                raw, residual, lower, upper, certificate_status, monotonic()-start)
            _remaining(deadline)
            return DeliveryResult(raw, raw/lp.total, units, diagnostics)
        except EvaluationError as exc:
            detail.update(reason=exc.reason, error=str(exc))
            history.append(detail)
            _remaining(deadline)
            if attempt == policy.max_solver_attempts:
                raise EvaluationError(str(exc), reason=exc.reason,
                                      diagnostics={'attempts': history, 'elapsed_seconds': monotonic()-start}) from exc
    raise AssertionError('Unreachable: fixed policy has two attempts')
