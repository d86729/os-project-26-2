"""Reproducible T006/T012/T017/T018 evidence, not a main experiment.
Run from project root: .venv/bin/python results/validation/run_numeric_policy.py
"""
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from protection.runner import initialize_single_thread, collect_environment
initialize_single_thread()
from protection.flow import maximum_delivery
from protection.generation import generate_scenario
from protection.models import to_data

OUT = ROOT / 'results/validation'
report = {'scope': 'T006/T012/T017/T018 numeric validation only; not main research',
          'environment': collect_environment(), 'real_solver_cases': [], 'test_runs': [],
          'excluded_implementation': ['Evaluator', 'cache', 'T019+'],
          'limitations': ['Small deterministic validation only; not general certification success-rate evidence',
                          'No hard process supervisor implemented here; cooperative checks and native solver time_limit',
                          'Explicit mocks in numeric tests only test rejection/retry; not performance evidence']}
for n in (3, 6, 8):
    scenario = generate_scenario(n, 0)
    ids = tuple(range(len(scenario.edges)))
    for label, surviving in (('empty', ()), ('all', ids), ('even', ids[::2]), ('odd', ids[1::2])):
        result = maximum_delivery(scenario, surviving)
        report['real_solver_cases'].append({'n': n, 'seed': 0, 'surviving': label,
            'scenario_id': scenario.scenario_id, 'surviving_ids': surviving, 'result': to_data(result)})
commands = [
    ('numeric-focused', ['tests/unit/test_flow.py', 'tests/unit/test_policy.py', 'tests/unit/test_numeric_policy.py']),
    ('numeric-regression', []),
]
for label, args in commands:
    command = [str(ROOT / '.venv/bin/python'), '-m', 'pytest', *args, '-q']
    run = subprocess.run(command, cwd=ROOT, text=True, capture_output=True)
    log = OUT / (label + '.txt')
    log.write_text(run.stdout + run.stderr)
    report['test_runs'].append({'command': command, 'exit_code': run.returncode,
        'log': str(log.relative_to(ROOT)), 'stdout': run.stdout, 'stderr': run.stderr,
        'exclusions': []})
    print(label, 'exit_code=', run.returncode, run.stdout.splitlines()[-1])
report['real_solver_case_count'] = len(report['real_solver_cases'])
report['certificate_attempt_counts'] = [c['result']['diagnostics']['attempts'] for c in report['real_solver_cases']]
(OUT / 'numeric-policy.json').write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False)+'\n')
print('Evidence:', OUT / 'numeric-policy.json')
