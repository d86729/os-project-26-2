"""Reproduce the registered web experiment with an interactive private login.

Credentials/cookies are never written into this artifact directory. Running
this script deliberately creates two real submissions; the notebook does not.
"""
import argparse
import csv
import getpass
import hashlib
import io
import json
import os
from pathlib import Path
import platform
import re
import subprocess
import sys
import tempfile
import time
from urllib.parse import urlencode

BASE = 'https://algorithm.586729.xyz'
HERE = Path(__file__).resolve().parent


def run():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--protocol', type=Path, default=HERE / 'protocol.json')
    parser.add_argument('--output', type=Path, default=HERE)
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    account, password = json.loads(getpass.getpass('Private login JSON: '))
    protocol = json.loads(args.protocol.read_text())
    with tempfile.TemporaryDirectory(prefix='agent3-web-') as temporary:
        jar = Path(temporary) / 'cookies'
        headers = Path(temporary) / 'headers'

        def request(path, fields=None):
            command = ['curl', '-sS', '--max-time', '30', '-b', str(jar), '-c', str(jar),
                       '-D', str(headers), '-w', '\n%{http_code}']
            data = None
            if fields is not None:
                command += ['--data-binary', '@-']
                data = urlencode(fields).encode()
            response = subprocess.run(command + [BASE + path], input=data, capture_output=True, check=True)
            content, code = response.stdout.rsplit(b'\n', 1)
            return int(code), content, headers.read_text()

        def csrf(body):
            return re.search(rb'name="csrf" value="([^"]+)"', body).group(1).decode()

        code, body, _ = request('/login')
        assert code == 200
        code, _, _ = request('/login', [('account', account), ('password', password), ('csrf', csrf(body))])
        del password
        assert code == 302, 'Login failed'
        inputs = output / 'inputs'
        inputs.mkdir(exist_ok=True)
        for case in protocol['cases']:
            code, body, _ = request(f'/bank/{case}/input')
            assert code == 200, case
            (inputs / (case + '.txt')).write_bytes(body)
        print('Downloaded', len(protocol['cases']), 'registered inputs', flush=True)

        local = []
        for variant in protocol['variants']:
            for case in protocol['cases']:
                data = (inputs / (case + '.txt')).read_bytes()
                start = time.monotonic()
                proc = subprocess.run([sys.executable, str(HERE / (variant + '.py'))],
                                      input=data, capture_output=True, check=True, timeout=10)
                values = list(map(int, proc.stdout.split()))
                assert values[0] == len(values) - 1
                assert values[1:] == sorted(set(values[1:]))
                rows = data.decode().splitlines()
                n, m, _, _ = map(int, rows[0].split())
                budget = int(rows[1].split()[0])
                costs = {int(r.split()[0]): int(r.split()[4]) for r in rows[2+n:2+n+m]}
                used = sum(costs[e] for e in values[1:])
                assert used <= budget
                local.append({'variant': variant, 'case': case, 'chosen_edges': values[1:],
                              'cost': used, 'budget': budget, 'seconds': time.monotonic()-start})
        (output / 'local_validation.json').write_text(json.dumps(local, indent=2)+'\n')
        print('Local stdout/budget checks passed:', len(local), flush=True)
        metadata = {'base_url': BASE, 'account': account, 'protocol': protocol,
                    'python': sys.version, 'platform': platform.platform(),
                    'created_utc': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
                    'jobs': []}
        for variant in protocol['variants']:
            source = (HERE / (variant + '.py')).read_bytes()
            code, body, _ = request('/')
            assert code == 200
            fields = [('csrf', csrf(body)), ('source', source.decode()), ('seconds', '10'),
                      ('memory', '512'), ('selection', 'direct')]
            fields += [('case', case) for case in protocol['cases']]
            code, _, header = request('/submit', fields)
            assert code == 302, f'Submission failed: {code}'
            job = int(re.search(r'(?im)^location: /jobs/(\d+)', header).group(1))
            entry = {'variant': variant, 'job_id': job, 'url': f'{BASE}/jobs/{job}',
                     'source_sha256': hashlib.sha256(source).hexdigest()}
            metadata['jobs'].append(entry)
            (output / 'web_runs.json').write_text(json.dumps(metadata, indent=2)+'\n')
            print('Submitted', variant, 'job', job, flush=True)
            deadline = time.monotonic() + 1800
            previous = -1
            while time.monotonic() < deadline:
                code, body, _ = request(f'/jobs/{job}/csv')
                assert code == 200
                rows = list(csv.DictReader(io.StringIO(body.decode('utf-8-sig'))))
                if len(rows) != previous:
                    print('Job', job, 'rows', len(rows), flush=True)
                    previous = len(rows)
                if len(rows) == len(protocol['cases']):
                    (output / (variant + '.csv')).write_bytes(body)
                    break
                time.sleep(2)
            else:
                raise TimeoutError(f'Job {job} did not finish within 30 minutes')
            # CSV may acquire its final row just before the worker marks finished.
            while True:
                code, body, _ = request(f'/jobs/{job}')
                if '채점 종료'.encode() in body or '중단'.encode() in body:
                    break
                time.sleep(1)
            print('Finished', variant, 'job', job, flush=True)
        print('Both registered variants completed', flush=True)


if __name__ == '__main__':
    run()
