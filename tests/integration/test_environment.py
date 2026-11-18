"""Run scientific initialization in a fresh process, never the pytest process."""
import json
import os
from pathlib import Path
import subprocess
import sys


def test_environment_in_fresh_process():
    root = Path(__file__).resolve().parents[2]
    env = dict(os.environ, OMP_NUM_THREADS='7', OPENBLAS_NUM_THREADS='7', MKL_NUM_THREADS='7')
    result = subprocess.run(
        [sys.executable, '-m', 'protection.runner', '--validate-environment',
         str(root / 'results/validation/environment.json')],
        env=env, capture_output=True, text=True, timeout=60, cwd=root)
    (root / 'results/validation/environment-process.log').write_text(result.stdout + result.stderr)
    assert result.returncode == 0, result.stdout + result.stderr
    report = json.loads((root / 'results/validation/environment.json').read_text())
    assert set(report['thread_environment'].values()) == {'1'}
    assert report['initialized_before_scientific_imports']
    assert report['lp']['success'] and report['lp']['objective'] == -10.0
    assert report['highs_threads_option'] == 1
    assert report['process_threads_before'] == report['process_threads_after'] == 1
    assert report['ram_bytes'] > 0 and report['cpu']
    assert 'threads' in result.stderr  # the real SciPy forwarding warning stays visible
    assert set(('numpy', 'scipy', 'networkx', 'pytest', 'nbformat', 'nbclient', 'ipykernel')) <= report['packages'].keys()
