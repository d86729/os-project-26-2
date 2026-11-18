"""Real small smoke, never main-experiment results."""
from protection.exact import search
from protection.generation import generate_scenario
from protection.models import atomic_json, bundle_from_record, save_bundle
from protection.runner import collect_environment


def test_smoke_two_budgets(tmp_path):
    scenario = generate_scenario(6, 0)
    records = []
    for percent in (20, 40):
        exhaustive = search(scenario, percent, method='exhaustive', limit_seconds=60)
        branch_bound = search(scenario, percent, method='branch_bound', limit_seconds=60)
        assert exhaustive.status == branch_bound.status == 'completed'
        assert exhaustive.best_evaluation == branch_bound.best_evaluation
        bundle = bundle_from_record(scenario, exhaustive)
        save_bundle(bundle, tmp_path / f'case-{percent}.json')
        records.extend([exhaustive, branch_bound])
    atomic_json('results/validation/exact.json', {'run_kind':'smoke',
        'environment':collect_environment(), 'records':records,
        'scope':'n=6 seed=0 two budgets, not main experiment'}, overwrite=True)
