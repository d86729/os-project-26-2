"""Explicitly run web experiments; credentials are prompted, never persisted.

Run from repository root with .venv/bin/python PATH/web_experiment.py.
Both preregistered sources are submitted sequentially. This creates real jobs.
The reproduction notebook does not invoke this script.
"""
import argparse
import csv
import getpass
import hashlib
import io
import json
from pathlib import Path
import re
import subprocess
import tempfile
import time
from urllib.parse import urlencode

BASE = 'https://algorithm.586729.xyz'
HERE = Path(__file__).resolve().parent
CASES = [f'n{n}-seed{s}-p{p}' for n in (6,8,10,12,14) for s in (0,1) for p in (20,40)]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cases-file', type=Path, help='JSON list of fixed case names; default is the 20 development cases')
    parser.add_argument('--output-dir', type=Path, default=HERE)
    parser.add_argument('--sources', nargs='+', default=['ablation_single.py','submission.py'])
    args = parser.parse_args()
    cases = json.loads(args.cases_file.read_text()) if args.cases_file else CASES
    assert isinstance(cases,list) and cases and len(cases)==len(set(cases))
    assert all(re.fullmatch(r'n[0-9]+-seed[0-9]+-p(20|40)',c) for c in cases)
    sources = [HERE/name for name in args.sources]
    assert all(p.parent == HERE and p.suffix == '.py' and p.is_file() for p in sources)
    output = args.output_dir.resolve()
    output.mkdir(parents=True,exist_ok=True)
    assert not (output/'web-metadata.json').exists(), 'output already contains a run; choose a new directory to avoid duplicate submission'
    account, password = json.loads(getpass.getpass('Credential JSON (hidden): '))
    assert account == 'member2'
    metadata = {'created_utc': time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),
                'base_url': BASE, 'account': account, 'cases': cases,
                'seconds_limit': 10, 'memory_limit_mb': 512,
                'deterministic': True, 'runs': []}
    with tempfile.TemporaryDirectory(prefix='agent2-http-') as temp:
        jar = str(Path(temp)/'cookies')
        headers = str(Path(temp)/'headers')
        def request(path, data=None):
            command = ['curl','--silent','--show-error','--max-time','30',
                       '-b',jar,'-c',jar,'-D',headers,'-w','\n%{http_code}',BASE+path]
            if data is not None:
                command += ['--data-binary','@-','-H','Content-Type: application/x-www-form-urlencoded']
            run = subprocess.run(command,input=urlencode(data).encode() if data is not None else None,
                                 capture_output=True,check=True)
            body, code = run.stdout.rsplit(b'\n',1)
            return int(code),body,Path(headers).read_text()
        def csrf(body):
            return re.search(rb'name="csrf" value="([^"]+)"',body).group(1).decode()
        code, body, _ = request('/login')
        assert code == 200
        code, _, _ = request('/login',[('csrf',csrf(body)),('account',account),('password',password)])
        del password
        assert code == 302, 'authentication failed'
        code, body, _ = request('/')
        assert code == 200
        input_hashes = {}
        for case in cases:
            code, data, _ = request('/bank/'+case+'/input')
            assert code == 200
            input_hashes[case] = hashlib.sha256(data).hexdigest()
            if not args.cases_file:
                known = next(row for row in json.loads((HERE/'local-validation.json').read_text()) if row['case']==case)
                assert input_hashes[case] == known['stdin_sha256'], 'web/local input mismatch'
        metadata['downloaded_stdin_sha256'] = input_hashes
        print('Downloaded and hashed',len(cases),'web inputs.',flush=True)
        for source_path in sources:
            source = source_path.name
            code, body, _ = request('/')
            payload = [('csrf',csrf(body)),('source',(HERE/source).read_text()),
                       ('seconds','10'),('memory','512'),('selection','direct')]+[('case',c) for c in cases]
            code, _, head = request('/submit',payload)
            assert code == 302, f'submission failed: HTTP {code}'
            location = re.search(r'^location:\s*(\S+)',head,re.I|re.M).group(1)
            job_id = int(location.rsplit('/',1)[1])
            record = {'source':source,'sha256':hashlib.sha256((HERE/source).read_bytes()).hexdigest(),
                      'job_id':job_id,'job_url':BASE+location}
            metadata['runs'].append(record)
            (output/'web-metadata.json').write_text(json.dumps(metadata,indent=2)+'\n')
            print(source,'submitted job',job_id,flush=True)
            last = None
            end = time.monotonic()+1800
            while True:
                code, body, _ = request(location)
                assert code == 200
                state = re.search(r'<p><strong>(.*?)</strong>',body.decode()).group(1)
                if state != last:
                    print('job',job_id,state,flush=True); last=state
                if state not in ('대기','채점 중'):
                    break
                if time.monotonic()>end:
                    raise TimeoutError(f'job {job_id} still active; resume observation without resubmit')
                time.sleep(2)
            code, content, _ = request(location+'/csv')
            assert code == 200
            (output/(source.removesuffix('.py')+'-web.csv')).write_bytes(content)
            rows=list(csv.DictReader(io.StringIO(content.decode('utf-8-sig'))))
            record['job_state']=state
            record['row_count']=len(rows)
            record['completed_count']=sum(r['status']=='completed' for r in rows)
            (output/'web-metadata.json').write_text(json.dumps(metadata,indent=2)+'\n')
            print('job',job_id,'rows',len(rows),'completed',record['completed_count'],flush=True)


if __name__=='__main__':
    main()
