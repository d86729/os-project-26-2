"""Explicit local research operations; no automatic size/seed selection.

Scale probes consume already saved inputs from ``generate``. A fresh output
is required for each attempt so failed seeds/history cannot be overwritten.
The caller is responsible for obtaining approval before long experiments.
"""
from pathlib import Path
import os
import re

from protection.models import require


def validate_operational_data(d):
    """Additional pure guards, called after structural manifest validation."""
    if d['run_kind'] == 'main':
        owners = list(d['owners'].values())
        if d['kind'] == 'grading':
            owners.append(d['submission']['owner'])
        for owner in owners:
            text = owner.strip().casefold()
            placeholder = (text in {'tbd', 'todo', 'unknown', 'none', 'null', 'name',
                                   'common', 'owner', '담당자', '미정', '미확정'}
                           or any(token in text for token in ('미제출', '실명', '팀원', '<', '>'))
                           or re.match(r'^(member|team|owner|담당자)[ _\d-]*$', text))
            require(not placeholder, 'main owner must be a real name, not a placeholder')
    require(d['kind'] != 'grading' or d['run_kind'] != 'scale_probe',
            'scale_probe requires a preparation manifest')
    if d['kind'] != 'preparation' or d['run_kind'] == 'smoke':
        return
    medium = []
    for n in d['sizes']:
        group = d['size_groups'][str(n)]
        if group == 'medium_large':
            medium.append(n)
    if d['run_kind'] == 'main' and medium:
        require(len(medium) == 3, 'main medium-large requires exactly three sizes')


def scale_summary(manifest, scenarios, records):
    """Check both budgets for each saved graph, never select a winning seed."""
    d = manifest.to_dict()
    expected = {(s.scenario_id, p) for s in scenarios for p in d['budget_percents']}
    observed = {}
    for record in records:
        key = (record.condition.scenario_id, record.condition.budget_percent)
        require(key in expected and key not in observed, 'unexpected or duplicate scale case')
        require(record.run_kind == 'scale_probe' and record.condition.method == 'exhaustive'
                and record.condition.limit_seconds == d['limits']['large_exact_seconds'],
                'scale record condition mismatch')
        observed[key] = record
    cases = []
    for s in scenarios:
        rows = [observed.get((s.scenario_id, p)) for p in d['budget_percents']]
        complete = all(r is not None and r.status == 'completed' and r.optimality_proven
                       and r.search_seconds is not None
                       and r.search_seconds < r.condition.limit_seconds for r in rows)
        cases.append({'size': len(s.nodes), 'seed': s.seed, 'scenario_id': s.scenario_id,
                      'complete': complete,
                      'budgets': {str(p): 'missing' if r is None else r.status
                                  for p, r in zip(d['budget_percents'], rows)}})
    qualified = [c['size'] for c in cases if c['complete']]
    return {'schema_version': 1, 'run_kind': 'scale_probe',
            'complete': len(set(qualified)) >= 3, 'qualified_sizes': qualified,
            'required_size_count': 3, 'cases': cases,
            'selection': None, 'manifest': d}


def run_scale_probe(manifest):
    """Sequential exhaustive probes, with durable records and fail-closed abort.

    Ordinary failed/timeout RunRecords do not stop the next budget. Exceptions
    escaping the exact supervisor stop the batch (possibly a residual worker);
    earlier records survive and remaining conditions are recorded not_started.
    """
    from protection.models import (ExperimentManifest, load_scenario, atomic_json,
        canonical_json, RunRecord, ExperimentCondition, ScenarioBundle)
    from protection.exact import search
    from protection.runner import collect_environment
    import uuid

    # Reparse even caller-created objects rather than trusting the dataclass shell.
    parsed = ExperimentManifest.parse(manifest.to_dict(), manifest.source_path)
    d = parsed.to_dict()
    require(d['kind'] == 'preparation' and d['run_kind'] == 'scale_probe',
            'scale_probe preparation manifest required')
    output = Path(d['output_dir'])
    names = ('scale_probe.jsonl', 'scale_probe-summary.json', 'scale_probe-environment.json')
    require(not any((output/name).exists() for name in names), 'scale output already exists')
    # 모든 입력의 크기와 시드를 먼저 확인한다. 검증이 끝나야 첫 탐색을 시작한다.
    scenarios = []
    for n in d['sizes']:
        for seed in d['seeds_by_size'][str(n)]:
            s = load_scenario(output/'inputs'/f'n{n}-seed{seed}.json')
            require(len(s.nodes) == n and s.seed == seed, 'saved scale input does not match manifest')
            scenarios.append(s)
    atomic_json(output/'scale_probe-environment.json', collect_environment())
    records = []
    blocked = None
    with (output/'scale_probe.jsonl').open('x', encoding='utf-8') as handle:
        for s in scenarios:
            for percent in d['budget_percents']:
                if blocked is None:
                    try:
                        record = search(s, percent, method='exhaustive',
                                        run_kind='scale_probe', manifest=manifest)
                    except Exception as exc:
                        blocked = f'{type(exc).__name__}: {exc}'
                if blocked is not None:
                    budget = sum(e.cost for e in s.edges)*percent//100
                    record = RunRecord(uuid.uuid4().hex,
                        ExperimentCondition(s.scenario_id, percent, budget, 'exhaustive',
                                            d['limits']['large_exact_seconds']),
                        case_id=ScenarioBundle(s, percent, budget).case_id,
                        status='failed', run_kind='scale_probe',
                        termination_reason='environment_blocked', error_message=blocked)
                records.append(record)
                handle.write(canonical_json(record)+'\n')
                handle.flush()
                os.fsync(handle.fileno())
    summary = scale_summary(manifest, scenarios, records)
    atomic_json(output/'scale_probe-summary.json', summary)
    return summary
