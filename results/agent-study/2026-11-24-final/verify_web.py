"""Exercise public-list and download routes against an isolated local test session."""
from hashlib import sha256
import json
import os
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from protection.runner import initialize_single_thread


def main():
    initialize_single_thread()
    from protection.models import load_bundle
    from protection.program import grading_lock, scenario_input
    from protection.web import bank_case, bank_files, create_app
    if len(sys.argv) != 2:
        raise ValueError('usage: verify_web.py n12-seed123')
    graph = sys.argv[1]
    with grading_lock(), tempfile.TemporaryDirectory(prefix='protection-web-test-') as state:
        os.environ['PROTECTION_STATE_DIR'] = state
        app = create_app()
        app.config.update(TESTING=True)
        client = app.test_client()
        with client.session_transaction() as session:
            session['owner'] = 'member1'
        files = bank_files()
        page = client.get('/')
        assert page.status_code == 200
        for percent in (20, 40):
            name = f'{graph}-p{percent}'
            assert name in files and name.encode() in page.data
            bundle = load_bundle(files[name], require_reference=True)
            assert bank_case(files[name]).case_id == bundle.case_id
            input_reply = client.get(f'/bank/{name}/input')
            reference_reply = client.get(f'/bank/{name}/reference')
            assert input_reply.status_code == reference_reply.status_code == 200
            assert input_reply.data == scenario_input(bundle)
            assert json.loads(reference_reply.data)['case_id'] == bundle.case_id
            print(name, 'listed and downloaded', 'case_id', bundle.case_id,
                  'stdin_sha256', sha256(input_reply.data).hexdigest())
    print('PASS: isolated Flask test client; no claim about a deployed live service')


if __name__ == '__main__':
    main()
