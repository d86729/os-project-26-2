"""Real small-bank acceptance; larger-failure branches use explicit doubles."""
import json
from pathlib import Path

import pytest

from protection.models import ExperimentManifest, ExperimentCondition, RunRecord, load_bundle
from protection.problem_bank import build_bank

ROOT = Path(__file__).resolve().parents[2]


def manifest(tmp_path, sizes=(6,)):
    d = json.loads((ROOT/'configs/smoke.json').read_text())
    d.update(run_kind='scale_probe', sizes=list(sizes),
             size_groups={str(n): 'probe' for n in sizes},
             seeds_by_size={str(n): [0] for n in sizes}, output_dir=str(tmp_path/'bank'))
    return ExperimentManifest.parse(d, tmp_path/'manifest.json')


def test_real_small_bank_has_two_verified_references(tmp_path, monkeypatch):
    bank = build_bank(manifest(tmp_path))
    assert bank['status'] == 'ready' and bank['accepted_sizes'] == [6]
    assert len(bank['bank']) == 2
    for entry in bank['bank']:
        path = Path(entry['path'])
        assert path.parent == Path('bundles')
        b = load_bundle(tmp_path / 'bank' / path, require_reference=True)
        assert b.case_id == entry['case_id']
        assert b.optimal_reference.limit_seconds == 10800
    with pytest.raises(FileExistsError):
        build_bank(manifest(tmp_path))

    moved = tmp_path / 'moved'
    moved.mkdir()
    (tmp_path / 'bank').rename(moved / 'bank')

    def unexpected_search(*args, **kwargs):
        pytest.fail('published cases should resume from stored records')

    monkeypatch.setattr('protection.exact.search', unexpected_search)
    assert build_bank(manifest(moved), resume=True) == bank


def test_timeout_keeps_both_records_and_continues_without_publishing(tmp_path, monkeypatch):
    from protection import exact
    calls = []
    def timeout(s, p, **kwargs):
        calls.append((len(s.nodes), p))
        return RunRecord('timeout-test', ExperimentCondition(s.scenario_id, p,
            sum(e.cost for e in s.edges)*p//100, 'exhaustive', 10800),
            status='timeout', run_kind='scale_probe', termination_reason='timeout')
    monkeypatch.setattr(exact, 'search', timeout)
    bank = build_bank(manifest(tmp_path, (6, 8)))
    assert calls == [(6, 20), (6, 40), (8, 20), (8, 40)]
    assert bank['bank'] == [] and bank['excluded_graphs'] == ['n6-seed0', 'n8-seed0']
    assert (tmp_path/'bank/records/n6-seed0-p20.json').exists()
    assert (tmp_path/'bank/inputs/n8-seed0.json').exists()


def test_old_twelve_hour_manifest_rejected(tmp_path):
    d = manifest(tmp_path).to_dict()
    d['limits']['large_exact_seconds'] = 43200
    with pytest.raises(ValueError, match='fixed exact limits'):
        ExperimentManifest.parse(d, tmp_path/'old.json')
