from dataclasses import FrozenInstanceError
import json
from pathlib import Path
import pytest


def test_immutable_hand_fixture_and_test_submission(hand_example, submission_file):
    assert hand_example.expected_delivered == 20
    with pytest.raises(FrozenInstanceError):
        hand_example.expected_delivered = 0
    assert submission_file.read_text() == 'print(0)\n'


def test_smoke_is_not_main():
    root = Path(__file__).resolve().parents[2]
    d = json.loads((root / 'configs/smoke.json').read_text())
    assert d['run_kind'] == 'smoke'
    assert d['sizes'] == [6] and d['seeds_by_size'] == {'6': [0]}
    assert d['size_groups'] == {'6': 'small'}
    assert d['budget_percents'] == [20, 40]
    assert {'owners', 'limits', 'exact_methods', 'output_dir', 'schema_version', 'kind'} <= d.keys()
