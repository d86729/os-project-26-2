"""Reproduce initial validation; never runs main or team implementations."""
from pathlib import Path
import json
import subprocess
import sys
import xml.etree.ElementTree as ET


def main():
    from protection.runner import initialize_single_thread, collect_environment
    initialize_single_thread()
    directory = Path('results/validation')
    command = [sys.executable, '-m', 'pytest', '-q', '--tb=short',
               '--junitxml=results/validation/regression.xml']
    result = subprocess.run(command, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    (directory/'regression.txt').write_text(result.stdout)
    print(result.stdout, flush=True)
    root = ET.parse(directory/'regression.xml').getroot()
    suites = list(root) if root.tag == 'testsuites' else [root]
    counts = {key: sum(int(s.get(key, 0)) for s in suites)
              for key in ('tests', 'failures', 'errors', 'skipped')}
    report = dict(command=command, exit_code=result.returncode, counts=counts,
                  environment=collect_environment(), policy='evaluation-v2',
                  worker_architecture='direct evaluation, one worker, total RSS',
                  scope='initial common-system smoke validation; no main experiments')
    (directory/'regression.json').write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n')
    if result.returncode or counts['failures'] or counts['errors'] or counts['skipped']:
        return 1
    runner = subprocess.run([sys.executable, str(directory/'run_runner_validation.py')])
    if runner.returncode:
        return runner.returncode
    notebook = json.loads((directory/'notebook.json').read_text())
    exact = json.loads((directory/'exact.json').read_text())
    acceptance = dict(status='passed', scope='initial common implementation only',
        regression=report, exact_records=len(exact['records']), notebook=notebook,
        evidence=['results/validation/regression.json','results/validation/exact.json',
                  'results/validation/runner.json','results/validation/common.json',
                  'results/validation/notebook.json','results/validation/submission-executed.ipynb'],
        quickstart_reproduction='Real CLI pipeline on fresh temporary paths and clean-kernel notebook via pytest',
        external_gates={'T054':'Operational inputs and long-run approval not supplied',
                        'T055':'Main bank not prepared', 'T056':'Actual three submissions absent',
                        'T060':'Final research acceptance requires T054-T056'})
    (directory/'initial_acceptance.json').write_text(json.dumps(acceptance,ensure_ascii=False,indent=2)+'\n')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
