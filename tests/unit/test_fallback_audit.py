"""Audit counters describe real LP solves, not cache reads or exact certificates."""
from protection.models import SolverDiagnostics
from fractions import Fraction


def test_fallback_count_survives_later_exact_solve_and_cache_hit(path_scenario, monkeypatch):
    from protection.attacks import prepare_attacks
    from protection.evaluation import Evaluator
    import importlib
    flow = importlib.import_module('protection.flow')
    details = dict(status=0, success=True, message='test double', attempts=1,
                   raw_delivered_mbps=0., maximum_residual=0., elapsed_seconds=0.)
    fallback = SolverDiagnostics(**details, certificate_status='highs_residual_fallback',
                                 certified_lower=None, certified_upper=None)
    certified = SolverDiagnostics(**details, certificate_status='certified',
                                  certified_lower=Fraction(0), certified_upper=Fraction(0))
    calls = []

    def solve(*args, **kwargs):
        diagnostic = fallback if not calls else certified
        calls.append(diagnostic)
        return flow.DeliveryResult(0., 0., 0, diagnostic)

    monkeypatch.setattr('protection.evaluation.maximum_delivery', solve)
    evaluator = Evaluator(path_scenario, prepare_attacks(path_scenario))
    evaluator.evaluate([], 4)
    evaluator.evaluate([0], 4)
    assert evaluator.fallback_solves == 1
    assert len(calls) > 1
    before = len(calls)
    evaluator.evaluate([], 4)
    assert len(calls) == before
    assert evaluator.fallback_solves == 1
