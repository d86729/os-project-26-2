"""Bootstrap failure branches with fake native APIs; no scientific workload."""
import json
import sys
from types import ModuleType, SimpleNamespace
from pathlib import Path
import pytest
import protection.runner as runner


@pytest.mark.parametrize('case', ['set_failure', 'get_failure', 'wrong_option',
                                  'threads_before', 'threads_after', 'failed_lp', 'success'])
def test_environment_fail_closed(case, tmp_path, monkeypatch):
    monkeypatch.setattr(runner, 'initialize_single_thread', lambda: None)
    monkeypatch.setattr(runner, 'collect_environment', lambda: {})
    class Highs:
        def setOptionValue(self, key, value):
            return -1 if case == 'set_failure' else 0
        def getOptionValue(self, key):
            return (-1 if case == 'get_failure' else 0, 2 if case == 'wrong_option' else 1)
    optimize = ModuleType('scipy.optimize')
    optimize.linprog = lambda *a, **k: SimpleNamespace(
        success=case != 'failed_lp', status=2 if case == 'failed_lp' else 0,
        fun=None if case == 'failed_lp' else -10., message='infeasible' if case == 'failed_lp' else 'OK')
    core = ModuleType('scipy.optimize._highspy._core')
    core._Highs = Highs
    core.HighsStatus = SimpleNamespace(kOk=0)
    for name, module in [('scipy', ModuleType('scipy')), ('scipy.optimize', optimize),
                         ('scipy.optimize._highspy', ModuleType('scipy.optimize._highspy')),
                         ('scipy.optimize._highspy._core', core)]:
        monkeypatch.setitem(sys.modules, name, module)
    calls = []
    real_iterdir = Path.iterdir
    def tasks(path):
        if str(path) != '/proc/self/task':
            return real_iterdir(path)
        calls.append(1)
        n = 2 if (case == 'threads_before' or case == 'threads_after' and len(calls) == 2) else 1
        return iter(range(n))
    monkeypatch.setattr(Path, 'iterdir', tasks)
    output = tmp_path/'environment.json'
    if case == 'success':
        assert runner.validate_environment(str(output))['lp']['objective'] == -10.
    else:
        with pytest.raises(RuntimeError):
            runner.validate_environment(str(output))
    report = json.loads(output.read_text())
    if case == 'failed_lp':
        assert report['lp']['objective'] is None
        assert report['lp']['success'] is False
        assert report['validation_error'] == 'infeasible'
    elif case != 'success':
        assert report['validation_error']
