"""CLI v1 integration: real processes, artifacts and failed member states."""
import json
import os
from pathlib import Path
import subprocess
import sys
import pytest

ROOT = Path(__file__).resolve().parents[2]


def cli(*args, expected=0):
    p = subprocess.run([sys.executable, '-m', 'protection.cli', *map(str,args)],
                       cwd=ROOT, text=True, capture_output=True, timeout=180)
    assert p.returncode == expected, p.stdout + p.stderr
    return p


def grading(bank, output):
    source = output.parent / 'test_only_submission.py'
    source.write_text('raise SystemExit(75)\n')
    return dict(schema_version=1,kind='grading',run_kind='smoke',ready=True,
        owners={'common':'김대건'}, bank=bank,
        submission=dict(method_id='member_1',file=str(source),
            owner='시험 전용',strategy_name='미구현',strategy_version='not-submitted'),
        limits=dict(algorithm_seconds=300,algorithm_memory_bytes=6000000000),
        resource_policy=dict(sample_interval_ms=10),output_dir=str(output))


def test_help_is_import_and_side_effect_free(tmp_path):
    script = """import os,sys
before=dict(os.environ)
from protection.cli import main
try: main(['--help'])
except SystemExit as e: assert e.code==0
assert dict(os.environ)==before
assert not any(x in sys.modules for x in ('numpy','scipy','protection.generation','protection.exact','protection.runner'))
"""
    p=subprocess.run([sys.executable,'-c',script],cwd=tmp_path,text=True,capture_output=True)
    assert p.returncode==0,p.stderr
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize('data',[{},[],{'kind':'grading'}, {'ready':False}])
def test_bad_manifest(tmp_path,data):
    path=tmp_path/'bad.json';path.write_text(json.dumps(data))
    cli('grade','--manifest',path,expected=2)
    assert not (tmp_path/'out').exists()


def test_main_is_not_authorized(tmp_path):
    cli('generate','--manifest',ROOT/'configs/experiment.json',expected=2)
    cli('exact','--input','missing','--budget-percent','20','--method','exhaustive',
        '--run-kind','main','--output',tmp_path/'no.json',expected=2)
    assert not (tmp_path/'no.json').exists()


def test_download_and_cli_use_node_row_numbers(tmp_path, monkeypatch):
    pytest.importorskip('flask')
    from protection import web
    from protection.models import load_bundle

    monkeypatch.setenv('PROTECTION_STATE_DIR', str(tmp_path))
    # conftest initializes the numerical runtime before test collection.
    monkeypatch.setattr(web, 'initialize_single_thread', lambda: None)
    bundle_path = web.bank_files()[web.EXAMPLE_CASE]
    bundle = load_bundle(bundle_path, require_reference=True)
    client = web.create_app().test_client()
    with client.session_transaction() as session:
        session['owner'] = 'member1'

    download = client.get(f'/bank/{web.EXAMPLE_CASE}/input')
    assert download.status_code == 200
    assert download.data == cli('input', '--bundle', bundle_path).stdout.encode('ascii')

    header, _, *rows = download.get_data(as_text=True).splitlines()
    node_count, edge_count, demand_count, attack_count = map(int, header.split())
    assert len(rows) == node_count + edge_count + demand_count + attack_count
    assert [tuple(map(float, row.split())) for row in rows[:node_count]] == [
        (node.x, node.y) for node in bundle.scenario.nodes
    ]
    demand_start = node_count + edge_count
    assert [tuple(map(int, row.split()[:2])) for row in rows[node_count:demand_start]] == [
        (edge.u, edge.v) for edge in bundle.scenario.edges
    ]
    assert [tuple(map(int, row.split()[:2])) for row in rows[demand_start:demand_start + demand_count]] == [
        (demand.source, demand.target) for demand in bundle.scenario.demands
    ]
    assert b'<code>x y</code>' in client.get('/').data


def test_cli_pipeline(tmp_path):
    prep=json.loads((ROOT/'configs/smoke.json').read_text());prep['output_dir']=str(tmp_path/'bank')
    manifest=tmp_path/'prepare.json';manifest.write_text(json.dumps(prep))
    cli('generate','--manifest',manifest)
    source=tmp_path/'bank/inputs/n6-seed0.json'
    bank=[]
    for percent in (20,40):
        record=tmp_path/f'exact-{percent}.json'; bundle=tmp_path/f'case-{percent}.json'
        cli('exact','--input',source,'--budget-percent',percent,'--method','exhaustive',
            '--run-kind','smoke','--limit-seconds','120','--output',record)
        cli('bundle','--input',source,'--exact-record',record,'--output',bundle)
        result=json.loads(cli('validate','--bundle',bundle,'--require-reference').stdout)
        bank.append(dict(path=str(bundle),case_id=result['case_id']))
    assert len({x['case_id'] for x in bank})==2
    gm=tmp_path/'grade.json';gm.write_text(json.dumps(grading(bank,tmp_path/'out')))
    cli('grade','--manifest',gm,'--budget-percent','20',expected=2)
    cli('grade','--manifest',gm,expected=1)
    records=[json.loads(x) for x in (tmp_path/'out/runs.jsonl').read_text().splitlines()]
    assert len(records)==2
    assert {r['case_id'] for r in records}=={x['case_id'] for x in bank}
    assert all(r['status']=='not_implemented' and r['submitted_evaluation'] is None for r in records)
    cli('report','--records',tmp_path/'out/runs.jsonl','--bank-manifest',gm,'--output-dir',tmp_path/'report')
    report=json.loads((tmp_path/'report/report.json').read_text())
    assert all(r['connected_pairs'] is None for r in report['runs'])
    d=grading(bank,tmp_path/'bad-out');d['bank'][0]['case_id']='0'*64
    gm.write_text(json.dumps(d));cli('grade','--manifest',gm,expected=2)


def test_grade_imports_no_preparation_code(tmp_path):
    # Reference-free saved input exercises grading without reference re-score imports.
    from protection.models import ScenarioBundle,save_bundle
    from protection.generation import generate_scenario
    s=generate_scenario(6,0); b=ScenarioBundle(s,20,sum(e.cost for e in s.edges)*20//100)
    save_bundle(b,tmp_path/'case.json')
    gm=tmp_path/'grade.json';gm.write_text(json.dumps(grading([dict(path=str(tmp_path/'case.json'),case_id=b.case_id)],tmp_path/'out')))
    script="""import sys
class Block:
 def find_spec(self,fullname,*args):
  if fullname in ('protection.generation','protection.exact'): raise AssertionError('preparation imported during grading')
sys.meta_path.insert(0,Block())
from protection.cli import main
raise SystemExit(main(['grade','--manifest',sys.argv[1]]))
"""
    p=subprocess.run([sys.executable,'-c',script,str(gm)],text=True,capture_output=True,timeout=60)
    assert p.returncode==1,p.stderr
    assert json.loads((tmp_path/'out/runs.jsonl').read_text())['status']=='not_implemented'
    # Test-only successful submission: never attributed to a team strategy.
    fixture=tmp_path/'test_only.py'
    fixture.write_text(
        'node_count, _, _, _ = map(int, input().split())\n'
        'input()\n'
        'for _ in range(node_count):\n'
        '    x, y = map(float, input().split())\n'
        'print(0)\n'
    )
    d=json.loads(gm.read_text());d['submission']['file']=str(fixture)
    d['output_dir']=str(tmp_path/'success')
    gm.write_text(json.dumps(d))
    cli('grade','--manifest',gm)
    assert json.loads((tmp_path/'success/runs.jsonl').read_text())['status']=='completed'


def test_timeout_is_recorded_and_cannot_be_distributed(tmp_path):
    from protection.generation import generate_scenario
    from protection.models import save_scenario
    source=tmp_path/'input.json';save_scenario(generate_scenario(6,0),source)
    record=tmp_path/'timeout.json'
    cli('exact','--input',source,'--budget-percent','40','--method','exhaustive',
        '--run-kind','smoke','--limit-seconds','0.001','--output',record,expected=1)
    assert json.loads(record.read_text())['status']=='timeout'
    cli('bundle','--input',source,'--exact-record',record,'--output',tmp_path/'invalid.json',expected=2)
    assert not (tmp_path/'invalid.json').exists()
