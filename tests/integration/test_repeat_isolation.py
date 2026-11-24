"""같은 문제를 재제출해도 매번 새로운 실행이 된다."""
from protection.models import ExperimentManifest, ScenarioBundle, save_bundle
from protection.runner import grade_manifest


def manifest(tmp_path, scenario):
    bundle = ScenarioBundle(scenario, 40, 4)
    save_bundle(bundle, tmp_path / 'case.json')
    (tmp_path / 'one.py').write_text(
        'from pathlib import Path\n'
        'with Path("/tmp/repeat-marker").open("x"): pass\n'
        'print(0)\n'
    )
    data = dict(
        schema_version=1, kind='grading', run_kind='smoke', owners={'common': 'test'},
        output_dir='out', bank=[dict(path='case.json', case_id=bundle.case_id)],
        submission=dict(method_id='member_1', file='one.py', owner='test',
                        strategy_name='test', strategy_version='0'),
        limits=dict(algorithm_seconds=300, algorithm_memory_bytes=6000000000),
        resource_policy=dict(sample_interval_ms=10))
    return ExperimentManifest.parse(data, tmp_path / 'manifest.json')


def test_repeated_submissions_use_fresh_processes(path_scenario, tmp_path, monkeypatch):
    plan = manifest(tmp_path, path_scenario)
    import protection.generation as generation
    def forbidden(*args, **kwargs):
        raise AssertionError('저장된 문제를 다시 생성하면 안 됩니다')
    monkeypatch.setattr(generation, 'generate_scenario', forbidden)
    first = grade_manifest(plan)
    second = grade_manifest(plan)
    assert len(first) == len(second) == 1
    assert first[0].status == second[0].status == 'completed'
    assert first[0].run_id != second[0].run_id
    assert first[0].case_id == second[0].case_id
    assert first[0].algorithm_vcpu_limit == second[0].algorithm_vcpu_limit == 1
